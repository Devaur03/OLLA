import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import SearchRequest
from app.models.response import SearchResponse, SearchResult, ProcessedResult
from app.services.search_service import SearchService
from app.services.fetch_service import FetchService
from app.services.clean_service import CleanService
from app.services.chunk_service import ChunkService
from app.services.rank_service import RankService
from app.services.cache_service import CacheService
from app.services.store_service import StoreService
from app.services.credibility_service import CredibilityService
from app.services.citation_service import CitationService
from app.db.session import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Main search endpoint with Redis caching and PostgreSQL persistence.

    Pipeline:
    1. Check Redis cache (cache hit → return immediately)
    2. DuckDuckGo search → candidate URLs
    3. Concurrent Jina Reader fetch → raw markdown
    4. Clean → remove noise
    5. Chunk → RAG-ready segments
    6. Rank → sort by relevance score
    7. Store to PostgreSQL (non-blocking, failure safe)
    8. Store to Redis cache
    9. Return structured JSON
    """
    start_time = time.monotonic()

    search_params = {
        "max_results": request.max_results,
        "max_chars_per_page": request.max_chars_per_page,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
    }

    # --- CACHE CHECK ---
    cache_service = CacheService()
    cache_key = cache_service.make_key(request.query, search_params)
    cached = await cache_service.get(cache_key)

    if cached:
        logger.info(f"Cache HIT for '{request.query}' — returning cached response")
        cached["cache_hit"] = True
        return SearchResponse(**cached)

    logger.info(f"Cache MISS for '{request.query}' — running pipeline")

    try:
        # --- STEP 1: Search ---
        search_service = SearchService(max_results=request.max_results)
        candidates = await search_service.search(request.query)

        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for query: '{request.query}'"
            )

        # --- STEP 2: Fetch ---
        fetch_service = FetchService()
        fetched_pages = await fetch_service.fetch_all(
            candidates=candidates,
            max_chars=request.max_chars_per_page,
        )

        if not fetched_pages:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch content from any search result URLs"
            )

        # --- STEP 3: Clean + Chunk ---
        clean_service = CleanService()
        chunk_service = ChunkService(
            chunk_size=request.chunk_size,
            overlap=request.chunk_overlap,
        )

        processed_results: list[ProcessedResult] = []
        for page in fetched_pages:
            cleaned_content = clean_service.clean(page.raw_content)
            if not cleaned_content:
                continue
            chunks = chunk_service.chunk(cleaned_content)
            processed_results.append(
                ProcessedResult(
                    title=page.title,
                    url=page.url,
                    content=cleaned_content,
                    chunks=chunks,
                    score=0.0,
                )
            )

        if not processed_results:
            raise HTTPException(status_code=503, detail="All pages had empty content after cleaning")

        # --- STEP 4: Rank ---
        rank_service = RankService()
        ranked_results = rank_service.rank(request.query, processed_results)

        # --- STEP 4.5: Apply Credibility Scoring ---
        credibility_service = CredibilityService()
        for result in ranked_results:
            cred_score = credibility_service.score(result.url)
            # final_score = (relevance * 0.7) + (credibility * 0.3)
            result.score = round((result.score * 0.7) + (cred_score * 0.3), 4)
            
        # Re-sort after credibility adjustment
        ranked_results = sorted(ranked_results, key=lambda r: r.score, reverse=True)

        # --- STEP 5: Build Final Results ---
        final_results: list[SearchResult] = []
        for rank_pos, result in enumerate(ranked_results, start=1):
            if result.score < request.min_score:
                continue
            final_results.append(
                SearchResult(
                    rank=rank_pos,
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    chunks=result.chunks,
                    score=result.score,
                    char_count=len(result.content),
                    chunk_count=len(result.chunks),
                )
            )

        # --- STEP 5.5: Generate Citations ---
        citation_service = CitationService()
        citations_markdown = citation_service.generate_citations_block(final_results)
        citations_json = citation_service.generate_json_citations(final_results)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        response = SearchResponse(
            query=request.query,
            total_results=len(final_results),
            processing_time_ms=elapsed_ms,
            results=final_results,
            citations_markdown=citations_markdown,
            citations_json=citations_json,
        )

        # --- STEP 6: Store to DB (non-blocking, failure safe) ---
        try:
            store_service = StoreService(db)
            await store_service.save(
                query=request.query,
                params=search_params,
                results=final_results,
                processing_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"DB storage failed (non-fatal): {e}")

        # --- STEP 7: Store to Cache ---
        await cache_service.set(cache_key, response.model_dump())

        logger.info(
            f"Search complete: '{request.query}' → {len(final_results)} results "
            f"in {elapsed_ms}ms (cached)"
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Search pipeline failed: {str(e)}")
