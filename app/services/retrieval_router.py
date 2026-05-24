"""
PURPOSE: The hybrid retrieval router (Phase 5) — the system's "brain".

Plain `/search` always crawls the web. That is wasteful for evergreen questions
already sitting in local memory, and it cannot tell a definition ("what is a
vector database") from a news query ("AI models released this week").

`RetrievalRouter` makes retrieval a *decision* instead of a fixed pipeline:

    cache  →  local vector memory  →  web crawl

It classifies the query, scores how confident local memory is (top similarity,
coverage, source trust, freshness, usefulness), and only refreshes from the web
when confidence is low, the content is stale, or the query is recency-sensitive.

Retrieval modes:
    FAST   — cache + memory only, never crawl
    FRESH  — always crawl (news / recency / force_refresh)
    HYBRID — memory first, web fallback on low confidence   (the default)
    DEEP   — wide web crawl for deep-research queries

Every decision is appended to `routing_trace` so the dashboard and the caller
can see exactly why the router went where it went.
"""

import asyncio
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.request import HybridSearchRequest, RetrievalMode, SearchRequest
from app.models.response import (
    ContentChunk,
    HybridSearchResponse,
    RetrievedSource,
    SearchResult,
)
from app.services.answer_service import AnswerService
from app.services.cache_service import CacheService
from app.services.citation_service import CitationService
from app.services.citation_verifier_service import CitationVerifierService
from app.services.diversity_service import DiversityService
from app.services.embed_service import EmbedService
from app.services.freshness_service import FreshnessService
from app.services.pipeline import PipelineError, SearchPipeline
from app.services.query_classifier_service import QueryClass, QueryClassifier
from app.services.query_expansion_service import QueryExpansionService
from app.services.rerank_service import RerankService
from app.services.scoring_service import ScoringService
from app.services.source_trust_service import SourceTrustService
from app.services.store_service import StoreService

logger = logging.getLogger(__name__)

# A chunk must clear this similarity to count toward memory "coverage".
_RELEVANT_SIM = 0.55
# Confidence component weights (sum = 1.0).
_CONF_W = {
    "top_sim": 0.40,
    "coverage": 0.15,
    "trust": 0.15,
    "freshness": 0.15,
    "usefulness": 0.15,
}


class RetrievalRouter:
    """Routes a query across cache, local vector memory, and the web."""

    def __init__(self, db: AsyncSession, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id
        self.classifier = QueryClassifier()
        self.freshness = FreshnessService()
        self.scoring = ScoringService()
        self.trust = SourceTrustService(db, workspace_id)
        self.cache = CacheService()

    # ------------------------------------------------------------- run

    async def run(self, request: HybridSearchRequest) -> HybridSearchResponse:
        start = time.monotonic()
        trace: list[str] = []

        # --- classify ------------------------------------------------------
        cls = self.classifier.classify(request.query)
        trace.append(
            f"classified as {cls.query_class.value} "
            f"(web_required={cls.web_required}); signals: {', '.join(cls.signals)}"
        )

        # --- pick the effective mode --------------------------------------
        mode = self._resolve_mode(request, cls, trace)

        # --- cache (FAST / HYBRID only, never on force_refresh) -----------
        cache_key = self.cache.make_key(
            request.query, {"hybrid": True, "mode": mode.value, "top_k": request.top_k}
        )
        if mode in (RetrievalMode.FAST, RetrievalMode.HYBRID) and not request.force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                trace.append("cache HIT — returning cached hybrid response")
                cached["cache_hit"] = True
                cached["routing_trace"] = cached.get("routing_trace", []) + trace
                return HybridSearchResponse(**cached)
            trace.append("cache MISS")

        # --- FRESH / DEEP: straight to the web ----------------------------
        if mode in (RetrievalMode.FRESH, RetrievalMode.DEEP):
            trace.append(f"{mode.value.upper()} mode → crawling the web")
            return await self._web(request, cls, mode, trace, start, cache_key)

        # --- search local vector memory -----------------------------------
        memory = await self._memory_search(request)
        if not memory["results"]:
            trace.append("local memory empty for this query")
            if mode == RetrievalMode.FAST:
                trace.append("FAST mode → no web fallback; returning empty result")
                return self._empty(request, cls, mode, trace, start)
            trace.append("HYBRID mode → falling back to the web")
            return await self._web(request, cls, mode, trace, start, cache_key)

        confidence = memory["confidence"]
        trace.append(
            f"memory confidence {confidence:.3f} "
            f"(top_sim={memory['top_sim']:.3f}, results={len(memory['results'])})"
        )

        # --- decide: answer from memory or refresh from the web -----------
        stale = memory["avg_freshness"] < 0.4
        sufficient = confidence >= request.min_confidence and not stale

        if mode == RetrievalMode.FAST:
            trace.append("FAST mode → answering from memory regardless of confidence")
            return await self._answer_from_memory(
                request, cls, mode, memory, trace, start, cache_key
            )

        if sufficient:
            trace.append(
                f"confidence ≥ {request.min_confidence} and content fresh → answering from memory"
            )
            return await self._answer_from_memory(
                request, cls, mode, memory, trace, start, cache_key
            )

        reason = "content is stale" if stale else f"confidence < {request.min_confidence}"
        trace.append(f"{reason} → refreshing from the web")
        return await self._web(request, cls, mode, trace, start, cache_key)

    # --------------------------------------------------------- mode logic

    def _resolve_mode(self, request, cls, trace: list[str]) -> RetrievalMode:
        """Turn an AUTO request + classification into a concrete mode."""
        if request.force_refresh:
            chosen = (
                RetrievalMode.DEEP if request.mode == RetrievalMode.DEEP else RetrievalMode.FRESH
            )
            trace.append(f"force_refresh set → {chosen.value.upper()} mode")
            return chosen
        if request.mode != RetrievalMode.AUTO:
            trace.append(f"explicit {request.mode.value.upper()} mode requested")
            return request.mode
        # AUTO routing
        if cls.web_required:
            trace.append("AUTO → FRESH (recency-sensitive query)")
            return RetrievalMode.FRESH
        if cls.query_class == QueryClass.RESEARCH:
            trace.append("AUTO → DEEP (research-intent query)")
            return RetrievalMode.DEEP
        trace.append("AUTO → HYBRID (memory first, web fallback)")
        return RetrievalMode.HYBRID

    # ------------------------------------------------------ memory search

    async def _memory_search(self, request: HybridSearchRequest) -> dict:
        """Vector search over stored chunks; returns grouped results + confidence."""
        empty = {"results": [], "confidence": 0.0, "top_sim": 0.0, "avg_freshness": 0.0}

        query_vec = await EmbedService().embed_query(request.query)
        if not query_vec:
            logger.warning("RetrievalRouter: query embedding failed -- memory skipped")
            return empty

        vector_str = "[" + ",".join(map(str, query_vec)) + "]"
        sql = text(
            """
            SELECT
                c.id   AS chunk_uuid,
                c.chunk_id AS chunk_index,
                c.text,
                c.char_count,
                c.usefulness_score,
                c.positive_feedback_count,
                c.negative_feedback_count,
                r.id   AS result_id,
                r.title,
                r.url,
                r.content AS result_content,
                r.score   AS result_score,
                r.last_refreshed_at,
                1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c
            JOIN results r ON c.result_id = r.id
            WHERE c.embedding IS NOT NULL
              AND c.workspace_id = :ws
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :lim
            """
        )
        try:
            rows = (
                await self.db.execute(
                    sql,
                    {"embedding": vector_str, "lim": request.top_k * 3, "ws": self.workspace_id},
                )
            ).fetchall()
        except Exception as e:  # noqa: BLE001
            logger.warning("RetrievalRouter: memory vector search failed: %s", e)
            return empty

        if not rows:
            return empty

        # Group chunks under their parent result.
        grouped: dict[str, dict] = {}
        for row in rows:
            g = grouped.setdefault(
                row.result_id,
                {
                    "title": row.title or "",
                    "url": row.url,
                    "content": row.result_content or "",
                    "result_score": float(row.result_score or 0.0),
                    "last_refreshed_at": row.last_refreshed_at,
                    "chunks": [],
                    "sims": [],
                    "usefulness": [],
                },
            )
            g["chunks"].append(
                ContentChunk(
                    chunk_id=int(row.chunk_index),
                    text=row.text,
                    char_count=int(row.char_count or len(row.text)),
                )
            )
            g["sims"].append(float(row.similarity))
            g["usefulness"].append(
                self.scoring.feedback_score(
                    int(row.positive_feedback_count or 0),
                    int(row.negative_feedback_count or 0),
                )
            )

        cls = self.classifier.classify(request.query)
        all_sims = [s for g in grouped.values() for s in g["sims"]]
        top_sim = max(all_sims) if all_sims else 0.0
        relevant = sum(1 for s in all_sims if s >= _RELEVANT_SIM)
        coverage = min(1.0, relevant / max(1, request.top_k))

        # Score every grouped source with the feedback-aware formula (Phase 7),
        # then rank by that final score rather than raw similarity alone.
        scored: list[dict] = []
        for g in grouped.values():
            src_sim = max(g["sims"])
            src_trust = await self.trust.get_trust(g["url"])
            src_fresh = self.freshness.score(g["last_refreshed_at"], cls.query_class)
            src_useful = sum(g["usefulness"]) / len(g["usefulness"])
            content = g["content"] or "\n\n".join(c.text for c in g["chunks"])
            breakdown = self.scoring.score(
                semantic=src_sim,
                keyword=src_sim,  # no separate keyword signal on stored chunks
                source_trust=src_trust,
                freshness=src_fresh,
                feedback=src_useful,
                density=self.scoring.density_score(len(content)),
            )
            scored.append(
                {
                    "g": g,
                    "url": g["url"],
                    "content": content,
                    "sim": src_sim,
                    "trust": src_trust,
                    "fresh": src_fresh,
                    "useful": src_useful,
                    "final": breakdown.final,
                }
            )

        scored.sort(key=lambda s: s["final"], reverse=True)

        # --- Phase 10: optional cross-encoder rerank over the candidates ---
        rerank = RerankService()
        if rerank.available:
            scored = await rerank.rerank(request.query, scored, text_of=lambda s: s["content"])

        # --- Phase 10: spread domains so no single site dominates ----------
        scored = DiversityService().diversify(
            scored, max_per_domain=settings.diversity_max_per_domain
        )
        scored = scored[: request.top_k]

        results: list[SearchResult] = []
        sources: list[RetrievedSource] = []
        for pos, s in enumerate(scored, start=1):
            g = s["g"]
            results.append(
                SearchResult(
                    rank=pos,
                    title=g["title"],
                    url=g["url"],
                    content=s["content"],
                    chunks=g["chunks"],
                    score=s["final"],
                    char_count=len(s["content"]),
                    chunk_count=len(g["chunks"]),
                )
            )
            sources.append(
                RetrievedSource(
                    title=g["title"],
                    url=g["url"],
                    trust=round(s["trust"], 4),
                    freshness=round(s["fresh"], 4),
                    similarity=round(s["sim"], 4),
                    from_memory=True,
                )
            )

        avg_trust = sum(s["trust"] for s in scored) / len(scored) if scored else 0.5
        avg_fresh = sum(s["fresh"] for s in scored) / len(scored) if scored else 0.0
        avg_useful = sum(s["useful"] for s in scored) / len(scored) if scored else 0.5

        confidence = round(
            top_sim * _CONF_W["top_sim"]
            + coverage * _CONF_W["coverage"]
            + avg_trust * _CONF_W["trust"]
            + avg_fresh * _CONF_W["freshness"]
            + avg_useful * _CONF_W["usefulness"],
            4,
        )
        return {
            "results": results,
            "sources": sources,
            "confidence": confidence,
            "top_sim": top_sim,
            "avg_freshness": avg_fresh,
        }

    # ------------------------------------------------------ answer paths

    async def _answer_from_memory(
        self, request, cls, mode, memory, trace, start, cache_key
    ) -> HybridSearchResponse:
        results: list[SearchResult] = memory["results"]
        citation_service = CitationService()
        citations_md = citation_service.generate_citations_block(results)
        citations_json = citation_service.generate_json_citations(results)

        answer_text, answer_model, degraded = "", "", False
        try:
            answer = await AnswerService(model=request.llm_model).synthesize(request.query, results)
            if answer.ok:
                answer_text, answer_model = answer.answer, answer.model
                trace.append(f"synthesized answer from memory via {answer_model}")
            else:
                degraded = True
                trace.append(f"answer synthesis skipped: {answer.error or 'no answer'}")
        except Exception as e:  # noqa: BLE001
            degraded = True
            trace.append(f"answer synthesis failed: {e}")

        cite_support, unsupported = self._verify_citations(answer_text, results, trace)

        response = HybridSearchResponse(
            query=request.query,
            retrieval_mode=mode.value,
            query_class=cls.query_class.value,
            web_required=cls.web_required,
            from_memory=True,
            confidence=memory["confidence"],
            processing_time_ms=int((time.monotonic() - start) * 1000),
            answer=answer_text,
            answer_model=answer_model,
            citations_markdown=citations_md,
            citations_json=citations_json,
            results=results,
            sources=memory["sources"],
            citation_support=cite_support,
            unsupported_citations=unsupported,
            routing_trace=trace,
            degraded=degraded,
        )
        await self.cache.set(cache_key, response.model_dump())
        return response

    def _verify_citations(self, answer: str, results, trace: list[str]) -> tuple[float, list[int]]:
        """Phase 10: check the answer's [n] citations point at on-topic sources."""
        if not settings.enable_citation_verification or not answer:
            return 0.0, []
        v = CitationVerifierService().verify(answer, results)
        if v.total_citations:
            trace.append(
                f"citation check: {v.supported_citations}/{v.total_citations} "
                f"supported (rate {v.support_rate})"
            )
            if v.unsupported_markers:
                trace.append(f"unsupported citations: {v.unsupported_markers}")
        return v.support_rate, v.unsupported_markers

    async def _web(self, request, cls, mode, trace, start, cache_key) -> HybridSearchResponse:
        """Run the full web pipeline and adapt its response to the hybrid shape."""
        is_deep = mode == RetrievalMode.DEEP
        queries_to_run = [request.query]
        max_results = request.max_results

        if is_deep:
            max_results = min(10, max(request.max_results, request.max_results * 2))
            trace.append(f"DEEP mode → widening crawl to {max_results} results")
            if settings.enable_query_expansion:
                variants = QueryExpansionService().expand(request.query, n=3)
                if variants:
                    queries_to_run.extend(variants)
                    trace.append(f"DEEP mode → multi-crawl expanded queries: {variants}")

        # --- Phase 10: query rewriting for non-DEEP mode ------------------
        elif settings.enable_query_expansion:
            rewritten = QueryExpansionService().rewrite(request.query)
            if rewritten != request.query and len(rewritten) >= 3:
                queries_to_run = [rewritten]
                trace.append(f"query rewritten for crawl: {rewritten!r}")

        # --- Concurrent execution of pipelines ----------------------------
        tasks = []
        for q in queries_to_run:
            search_req = SearchRequest(
                query=q, max_results=max_results, llm_model=request.llm_model
            )
            tasks.append(
                SearchPipeline(self.db, self.workspace_id).run(
                    search_req, skip_answer=is_deep, skip_store=is_deep
                )
            )

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        if not is_deep:
            web = responses[0]
            if isinstance(web, Exception):
                if isinstance(web, PipelineError):
                    trace.append(f"web pipeline failed ({web.detail}) — returning empty result")
                else:
                    trace.append(f"web pipeline failed ({web}) — returning empty result")
                return self._empty(request, cls, mode, trace, start)
            trace.extend(f"web stage {t.stage}: {t.status}" for t in web.trace)
        else:
            # --- Phase 10: Pool, Dedup, Rerank, Answer, Store --------------
            pooled_results = []
            seen_urls = set()
            degraded = False
            for i, r in enumerate(responses):
                q = queries_to_run[i]
                if isinstance(r, Exception):
                    degraded = True
                    trace.append(f"crawl failed for {q!r}: {r}")
                    continue
                if r.degraded:
                    degraded = True
                trace.extend(f"crawl stage {t.stage}: {t.status} ({q!r})" for t in r.trace)
                for res in r.results:
                    if res.url not in seen_urls:
                        seen_urls.add(res.url)
                        pooled_results.append(res)

            trace.append(
                f"DEEP mode → pooled {len(pooled_results)} unique results across {len(queries_to_run)} crawls"
            )
            if not pooled_results:
                trace.append("all deep crawls failed or returned empty")
                return self._empty(request, cls, mode, trace, start)

            # Rerank
            if RerankService().available:
                pooled_results = await RerankService().rerank(
                    request.query, pooled_results, text_of=lambda x: x.content
                )

            # Truncate and recompute ranks
            pooled_results = pooled_results[: request.max_results]
            for i, res in enumerate(pooled_results):
                res.rank = i + 1

            # Synthesize Answer
            answer_text, answer_model = "", ""
            answer = await AnswerService(model=request.llm_model).synthesize(
                request.query, pooled_results
            )
            if answer.ok:
                answer_text, answer_model = answer.answer, answer.model
            else:
                degraded = True
                trace.append(f"answer synthesis failed: {answer.error}")

            # Store final result
            elapsed_ms = int((time.monotonic() - start) * 1000)
            from app.services.graph_service import GraphService

            query_id = await StoreService(self.db, self.workspace_id).save(
                query=request.query,
                params={"mode": "DEEP"},
                results=pooled_results,
                processing_ms=elapsed_ms,
            )
            if settings.enable_knowledge_graph and query_id:
                await GraphService(self.db).build_edges()

            # Create mock SearchResponse for standard downstream processing
            citations_md = CitationService().generate_citations_block(pooled_results)
            citations_json = CitationService().generate_json_citations(pooled_results)

            from app.models.response import SearchResponse

            web = SearchResponse(
                query=request.query,
                total_results=len(pooled_results),
                processing_time_ms=elapsed_ms,
                results=pooled_results,
                citations_markdown=citations_md,
                citations_json=citations_json,
                degraded=degraded,
                trace=[],
                answer=answer_text,
                answer_model=answer_model,
            )

        sources = [
            RetrievedSource(
                title=r.title,
                url=r.url,
                trust=round(r.score, 4),
                freshness=1.0,
                from_memory=False,
            )
            for r in web.results
        ]
        trace.append(f"web crawl returned {len(web.results)} results")

        cite_support, unsupported = self._verify_citations(web.answer, web.results, trace)

        response = HybridSearchResponse(
            query=request.query,
            retrieval_mode=mode.value,
            query_class=cls.query_class.value,
            web_required=cls.web_required,
            from_memory=False,
            confidence=1.0 if web.results else 0.0,
            processing_time_ms=int((time.monotonic() - start) * 1000),
            answer=web.answer,
            answer_model=web.answer_model,
            citations_markdown=web.citations_markdown,
            citations_json=web.citations_json,
            results=web.results,
            sources=sources,
            citation_support=cite_support,
            unsupported_citations=unsupported,
            routing_trace=trace,
            degraded=web.degraded,
        )
        if mode in (RetrievalMode.FAST, RetrievalMode.HYBRID):
            await self.cache.set(cache_key, response.model_dump())
        return response

    def _empty(self, request, cls, mode, trace, start) -> HybridSearchResponse:
        return HybridSearchResponse(
            query=request.query,
            retrieval_mode=mode.value,
            query_class=cls.query_class.value,
            web_required=cls.web_required,
            from_memory=False,
            confidence=0.0,
            processing_time_ms=int((time.monotonic() - start) * 1000),
            routing_trace=trace,
            degraded=True,
        )
