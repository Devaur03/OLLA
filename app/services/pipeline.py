"""
PURPOSE: The staged search pipeline orchestrator.

Before this refactor the entire pipeline lived inline in the route handler —
one failing step took down the whole request with no traceability
(COMPARISON_README §2, §7). `SearchPipeline` replaces that with explicit,
isolated stages:

    search → fetch → clean → chunk → rank → store → embed → graph

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
from app.services.answer_service import AnswerService
from app.services.cache_service import CacheService
from app.services.chunk_service import ChunkService
from app.services.citation_service import CitationService
from app.services.clean_service import CleanService
from app.services.entity_service import EntityService
from app.services.fetch_service import FetchService
from app.services.graph_service import GraphService
from app.services.rank_service import RankService
from app.services.sanitize_service import SanitizeService
from app.services.search_service import SearchService
from app.services.source_trust_service import SourceTrustService
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

    def __init__(self, db: AsyncSession, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id
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

    async def run(
        self, request: SearchRequest, skip_answer: bool = False, skip_store: bool = False
    ) -> SearchResponse:
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
        logger.info("Cache MISS for %r -- running pipeline", request.query)

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
            # Blended source trust = static credibility + learned feedback
            # signal (Phase 7). With no feedback yet it equals the old static
            # credibility, so existing behaviour is preserved.
            trust_service = SourceTrustService(self.db, self.workspace_id)
            for r in ranked:
                trust = await trust_service.get_trust(r.url)
                # final = relevance * 0.7 + source_trust * 0.3
                r.score = round((r.score * 0.7) + (trust * 0.3), 4)
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

        # --- STAGE: answer (RAG synthesis, non-fatal) ----------------------
        answer_text = ""
        answer_model = ""
        with self._stage("answer") as span:
            if skip_answer:
                span["status"] = "skipped"
                span["detail"] = "skipped by request"
            else:
                answer_result = await AnswerService(
                    model=request.llm_model
                ).synthesize(request.query, final_results)
                if answer_result.ok:
                    answer_text = answer_result.answer
                    answer_model = answer_result.model
                    span["detail"] = f"{len(answer_text)} chars via {answer_model}"
                else:
                    span["status"] = "skipped"
                    span["detail"] = answer_result.error or "no answer produced"

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
            answer=answer_text,
            answer_model=answer_model,
        )

        # --- STAGE: store (non-fatal) -------------------------------------
        query_id: str | None = None
        with self._stage("store") as span:
            if skip_store:
                span["status"] = "skipped"
                span["detail"] = "skipped by request"
            else:
                store_service = StoreService(self.db, self.workspace_id)
                query_id = await store_service.save(
                    query=request.query, params=search_params,
                    results=final_results, processing_ms=elapsed_ms,
                )
                span["detail"] = f"query_id={query_id}"
        # Expose the stored query id so clients can attach answer-level feedback.
        response.query_id = query_id

        # --- STAGE: embed (non-fatal) -------------------------------------
        # Vectorise the chunks we just stored. Doing this inline (instead of
        # waiting for a manual /search/embed-and-store backfill) is what lets
        # the knowledge graph grow on every single search.
        embedded = 0
        with self._stage("embed") as span:
            if skip_store or not query_id:
                span["status"] = "skipped"
                span["detail"] = "nothing stored to embed"
            elif not settings.enable_knowledge_graph:
                span["status"] = "skipped"
                span["detail"] = "knowledge graph disabled"
            else:
                embedded = await self._embed_query_chunks(query_id)
                span["detail"] = f"{embedded} new chunk(s) vectorised"
                if not embedded:
                    span["status"] = "skipped"
                    span["detail"] = (
                        "no embeddings produced — install sentence-transformers "
                        "or set OPENAI_API_KEY"
                    )

        # Persist everything stored + embedded so far. The graph step below
        # commits independently and could otherwise roll this work back.
        try:
            await self.db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("Pipeline: pre-graph commit failed: %s", e)

        # --- STAGE: graph (non-fatal) -------------------------------------
        # Build semantic-similarity edges between chunks. Runs on every search
        # so the graph continuously expands and links new content to old.
        with self._stage("graph") as span:
            if skip_store or not query_id:
                span["status"] = "skipped"
                span["detail"] = "nothing stored to link"
            elif not settings.enable_knowledge_graph:
                span["status"] = "skipped"
                span["detail"] = "knowledge graph disabled"
            else:
                created = await GraphService(self.db).build_edges()
                total = await self._graph_edge_count()
                span["detail"] = f"+{created} edge(s), {total} total"
                if total == 0 and not embedded:
                    span["status"] = "skipped"
                    span["detail"] = "no chunk embeddings available yet"

        # --- persist traces + cache --------------------------------------
        await self._persist_traces(query_id)
        response.degraded = self.degraded
        response.trace = self.traces
        await cache_service.set(cache_key, response.model_dump())

        logger.info(
            "Search complete: %r -> %d results in %dms%s",
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

    # ----------------------------------------------------- graph helpers

    async def _embed_query_chunks(self, query_id: str) -> int:
        """
        Generate and persist embeddings for every chunk of `query_id` that
        does not have one yet. Best-effort — returns the count embedded.
        """
        from sqlalchemy import text as _text
        from app.services.embed_service import EmbedService

        rows = (
            await self.db.execute(
                _text(
                    """
                    SELECT c.id, c.text
                    FROM chunks c
                    JOIN results r ON c.result_id = r.id
                    WHERE r.query_id = :qid AND c.embedding IS NULL
                    LIMIT 500
                    """
                ),
                {"qid": query_id},
            )
        ).fetchall()
        if not rows:
            return 0

        embed_service = EmbedService()
        processed = 0
        batch = 50
        for i in range(0, len(rows), batch):
            window = rows[i:i + batch]
            embeddings = await embed_service.embed_texts([r.text for r in window])
            if not embeddings:
                continue
            for row, emb in zip(window, embeddings):
                vec = "[" + ",".join(map(str, emb)) + "]"
                await self.db.execute(
                    _text(
                        "UPDATE chunks SET embedding = CAST(:emb AS vector) "
                        "WHERE id = :id"
                    ),
                    {"emb": vec, "id": row.id},
                )
                processed += 1
        await self.db.flush()
        return processed

    async def _graph_edge_count(self) -> int:
        """Total chunk_edges currently in the knowledge graph (best-effort)."""
        try:
            from sqlalchemy import text as _text
            row = (
                await self.db.execute(
                    _text("SELECT COUNT(*) AS n FROM chunk_edges")
                )
            ).first()
            return int(row.n) if row else 0
        except Exception:  # noqa: BLE001
            return 0
