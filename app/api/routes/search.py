import time
import logging
from fastapi import APIRouter, HTTPException

from app.models.request import SearchRequest
from app.models.response import SearchResponse, SearchResult, ProcessedResult
from app.services.search_service import SearchService
from app.services.fetch_service import FetchService
from app.services.clean_service import CleanService
from app.services.chunk_service import ChunkService
from app.services.rank_service import RankService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Main search endpoint.

    Pipeline:
    1. DuckDuckGo search → candidate URLs
    2. Concurrent Jina Reader fetch → raw markdown
    3. Clean → remove noise
    4. Chunk → RAG-ready segments
    5. Rank → sort by relevance score
    6. Return structured JSON

    Returns 404 if no results found, 503 if pipeline fails.
    """
    start_time = time.monotonic()

    logger.info(f"Search request: '{request.query}' (max_results={request.max_results})")

    try:
        # --- STEP 1: Search ---
        search_service = SearchService(max_results=request.max_results)
        candidates = await search_service.search(request.query)

        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for query: '{request.query}'"
            )

        logger.info(f"Found {len(candidates)} candidates")

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

        logger.info(f"Fetched {len(fetched_pages)} pages")

        # --- STEP 3: Clean + Chunk ---
        clean_service = CleanService()
        chunk_service = ChunkService(
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        processed_results: list[ProcessedResult] = []

        for page in fetched_pages:
            cleaned_content = clean_service.clean(page.raw_content)

            # Skip pages that become empty after cleaning
            if not cleaned_content:
                logger.debug(f"Skipping {page.url} — empty after cleaning")
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
            raise HTTPException(
                status_code=503,
                detail="All fetched pages had empty content after cleaning"
            )

        # --- STEP 4: Rank ---
        rank_service = RankService()
        ranked_results = rank_service.rank(request.query, processed_results)

        # --- STEP 5: Filter and Build Response ---
        final_results: list[SearchResult] = []

        for rank_position, result in enumerate(ranked_results, start=1):
            # Apply minimum score filter
            if result.score < request.min_score:
                continue

            final_results.append(
                SearchResult(
                    rank=rank_position,
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    chunks=result.chunks,
                    score=result.score,
                    char_count=len(result.content),
                    chunk_count=len(result.chunks),
                )
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            f"Search complete: '{request.query}' → {len(final_results)} results "
            f"in {elapsed_ms}ms"
        )

        return SearchResponse(
            query=request.query,
            total_results=len(final_results),
            processing_time_ms=elapsed_ms,
            results=final_results,
        )

    except HTTPException:
        # Re-raise FastAPI HTTP exceptions as-is
        raise

    except Exception as e:
        logger.error(f"Unexpected error during search: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Search pipeline failed: {str(e)}"
        )
