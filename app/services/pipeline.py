"""
PURPOSE: The staged search pipeline orchestrator.

Before this refactor the entire pipeline lived inline in the route handler —
one failing step took down the whole request with no traceability
(COMPARISON_README §2, §7). `SearchPipeline` replaces that with explicit,
isolated stages:

    search → fetch → clean → chunk → rank → store → graph

Each stage runs inside a trace span that records its status (success / failed /
fallback / skipped) and duration. Critical stages (search, fetch) raise on
failure; enrichment stages (store, graph, entities) are non-fatal — a failure
there marks the response `degraded` but still returns results.

Trace spans are returned on the response AND persisted to `agent_traces` so the
dashboard can see exactly where any query slowed down or fell back.
"""

import logging
import time
import uuid
from contextlib import contextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db.agent_trace import AgentTrace
from app.models.request import SearchRequest
from app.models.response import (
    ProcessedResult, SearchResponse, SearchResult, StageTrace,
)
from app.services.cache_service import CacheService
from app.services.chunk_service import ChunkService
from app.services.citation_service import CitationService
from app.services.clean_service import CleanService
from app.services.credibility_service import CredibilityService
from app.services.entity_service import EntityService
from app.services.fetch_service import FetchService
from app.services.graph_service import GraphService
from app.services.rank_service import RankService
from app.services.sanitize_service import SanitizeService
from app.services.search_service import SearchService
from app.services.store_service import StoreService

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised by a critical stage. Carries an HTTP status for the route."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class SearchPipeline:
    """Runs a search request through isolated, traced stages."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.traces: list[StageTrace] = []
        self.degraded = False

    # ----------------------------------------------------------- tracing

    @contextmanager
    def _stage(self, name: str, critical: bool = False):
        """
        Context manager wrapping one pipeline stage.

        Yields a mutable dict the stage fills in (`status`, `detail`). On an
        unhandled exception: critical stages re-raise as PipelineError, others
        are swallowed and the response is marked degraded.
        """
        start = time.monotonic()
        span: dict = {"status": "success", "detail": ""}
        try:
            yield span
        except PipelineError:
            raise
        except Exception as e:  # noqa: BLE001
            span["status"] = "failed"
            span["detail"] = str(e)
            logger.error("Pipeline stage %r failed: %s", name, e, exc_info=True)
            if critical:
                duration = int((time.monotonic() - start) * 1000)
                self._record(name, "failed", duration, str(e))
                raise PipelineError(503, f"Search stage '{name}' failed: {e}") from e
            self.degraded = True
        finally:
            duration = int((time.monotonic() - start) * 1000)
            # Critical-failure path already recorded above.
            if not (span["status"] == "failed" and critical):
                self._record(name, span["status"], duration, span["detail"])

    def _record(self, stage: str, status: str, duration_ms: int, detail: str) -> None:
        self.traces.append(
            StageTrace(stage=stage, status=status, duration_ms=duration_ms, detail=detail)
        )

    # --------------------------------------------------------------- run

    async def run(self, request: SearchRequest) -> SearchResponse:
        start = time.monotonic()
        search_params = {
            "max_results": request.max_results,
            "max_chars_per_page": request.max_chars_per_page,
            "chunk_size": request.chunk_size,
            "chunk_overlap": request.chunk_overlap,
            "safesearch": request.safesearch.value,
            "timelimit": request.timelimit.value if request.timelimit else None,
            "region": request.region,
        }

        # --- CACHE ---------------------------------------------------------
        cache_service = CacheService()
        cache_key = cache_service.make_key(request.query, search_params)
        cached = await cache_service.get(cache_key)
        if cached:
            logger.info("Cache HIT for %r", request.query)
            cached["cache_hit"] = True
            return SearchResponse(**cached)
        logger.info("Cache MISS for %r — running pipeline", request.query)

        # --- STAGE: search -------------------------------------------------
        candidates = []
        with self._stage("search", critical=True) as span:
            search_service = SearchService(max_results=request.max_results)
            candidates = await search_service.search(
                request.query,
                safesearch=request.safesearch,
                timelimit=request.timelimit,
                region=request.region,
            )
            span["detail"] = f"{len(candidates)} candidates"
        if not candidates:
            self._record("search", "failed", 0, "no candidates")
            raise PipelineError(404, f"No results found for query: '{request.query}'")

        # --- STAGE: fetch --------------------------------------------------
        fetched_pages = []
        with self._stage("fetch", critical=True) as span:
            fetched_pages = await FetchService().fetch_all(
                candidates=candidates, max_chars=request.max_chars_per_page,
            )
            methods = {}
            for p in fetched_pages:
                methods[p.fetch_method] = methods.get(p.fetch_method, 0) + 1
            span["detail"] = f"{len(fetched_pages)} pages ({methods})"
            if any(m != "jina" for m in methods):
                span["status"] = "fallback"
        if not fetched_pages:
            self._record("fetch", "failed", 0, "no pages fetched")
            raise PipelineError(503, "Failed to fetch content from any result URL")

        # --- STAGE: clean + sanitize + chunk -------------------------------
        processed_results: list[ProcessedResult] = []
        with self._stage("clean") as span:
            clean_service = CleanService()
            sanitize_service = SanitizeService()
            chunk_service = ChunkService(
                chunk_size=request.chunk_size, overlap=request.chunk_overlap,
            )
            entity_service = EntityService()
            redactions = 0
            for page in fetched_pages:
                cleaned = clean_service.clean(page.raw_content)
                if not cleaned:
                    continue
                if settings.enable_sanitization:
                    cleaned, n = sanitize_service.sanitize(cleaned)
                    redactions += n
                chunks = chunk_service.chunk(cleaned)
                for ch in chunks:
                    ch.entities = entity_service.extract(ch.text)
                processed_results.append(
                    ProcessedResult(
                        title=page.title, url=page.url,
                        content=cleaned, chunks=chunks, score=0.0,
                    )
                )
            span["detail"] = (
                f"{len(processed_results)} pages, {redactions} injection redaction(s)"
            )
            if redactions:
                span["status"] = "fallback"
        if not processed_results:
            self._record("clean", "failed", 0, "empty after cleaning")
            raise PipelineError(503, "All pages had empty content after cleaning")

        # --- STAGE: rank ---------------------------------------------------
        final_results: list[SearchResult] = []
        with self._stage("rank") as span:
            ranked = RankService().rank(request.query, processed_results)
            credibility = CredibilityService()
            for r in ranked:
                cred = credibility.score(r.url)
                # final = relevance * 0.7 + credibility * 0.3
                r.score = round((r.score * 0.7) + (cred * 0.3), 4)
            ranked.sort(key=lambda r: r.score, reverse=True)
            for pos, r in enumerate(
                (x for x in ranked if x.score >= request.min_score), start=1
            ):
                final_results.append(
                    SearchResult(
                        rank=pos, title=r.title, url=r.url, content=r.content,
                        chunks=r.chunks, score=r.score,
                        char_count=len(r.content), chunk_count=len(r.chunks),
                    )
                )
            span["detail"] = f"{len(final_results)} results above min_score"

        # --- citations -----------------------------------------------------
        citation_service = CitationService()
        citations_md = citation_service.generate_citations_block(final_results)
        citations_json = citation_service.generate_json_citations(final_results)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        response = SearchResponse(
            query=request.query,
            total_results=len(final_results),
            processing_time_ms=elapsed_ms,
            results=final_results,
            citations_markdown=citations_md,
            citations_json=citations_json,
            degraded=self.degraded,
            trace=self.traces,
        )

        # --- STAGE: store (non-fatal) -------------------------------------
        query_id: str | None = None
        with self._stage("store") as span:
            store_service = StoreService(self.db)
            query_id = await store_service.save(
                query=request.query, params=search_params,
                results=final_results, processing_ms=elapsed_ms,
            )
            span["detail"] = f"query_id={query_id}"

        # --- STAGE: graph (non-fatal, optional) ---------------------------
        with self._stage("graph") as span:
            if settings.enable_knowledge_graph and query_id:
                created = await GraphService(self.db).build_edges()
                span["detail"] = f"{created} edge(s)"
                if not created:
                    span["status"] = "skipped"
                    span["detail"] = "no embeddings yet — run /search/embed-and-store"
            else:
                span["status"] = "skipped"
                span["detail"] = "knowledge graph disabled or query not stored"

        # --- persist traces + cache --------------------------------------
        await self._persist_traces(query_id)
        response.degraded = self.degraded
        response.trace = self.traces
        await cache_service.set(cache_key, response.model_dump())

        logger.info(
            "Search complete: %r → %d results in %dms%s",
            request.query, len(final_results), elapsed_ms,
            " (degraded)" if self.degraded else "",
        )
        return response

    # ------------------------------------------------------------ traces

    async def _persist_traces(self, query_id: str | None) -> None:
        """Write the stage traces to agent_traces. Best-effort / non-fatal."""
        try:
            for t in self.traces:
                self.db.add(
                    AgentTrace(
                        id=str(uuid.uuid4()),
                        query_id=query_id,
                        stage=t.stage,
                        status=t.status,
                        duration_ms=t.duration_ms,
                        trace_metadata={"detail": t.detail} if t.detail else None,
                    )
                )
            await self.db.flush()
        except Exception as e:  # noqa: BLE001
            logger.warning("Pipeline: failed to persist agent_traces: %s", e)
