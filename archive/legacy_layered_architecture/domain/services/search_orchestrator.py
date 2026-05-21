"""
SearchOrchestrator: the main pipeline coordinator.

Orchestrates the full hybrid-search flow:
  1. Cache lookup  (fast exit if hit)
  2. Web search    (DDG / Brave)
  3. Content fetch (Jina Reader)
  4. Process       (clean + chunk)
  5. Embed chunks
  6. Rank results
  7. Persist to DB
  8. Write cache
  9. Return response payload

All external collaborators are injected via the constructor, making the
orchestrator fully unit-testable with mocks.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.domain.interfaces.cache import Cache
from app.domain.interfaces.content_fetcher import ContentFetcher
from app.domain.interfaces.embedding_model import EmbeddingModel
from app.domain.interfaces.repository import SearchRepository, StoredSearchResult
from app.domain.interfaces.search_provider import SearchProvider, SearchCandidate
from app.domain.models.citation import Citation
from app.domain.models.search import Chunk, RankedResult, SearchQuery
from app.domain.services.content_processor import ContentProcessor
from app.domain.services.ranking_engine import RankingEngine

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """
    Coordinates the full hybrid-search pipeline.

    Args:
        primary_provider: First-choice search provider (DuckDuckGo).
        fallback_provider: Optional secondary provider (Brave Search).
        fetcher: Content fetcher (JinaReader).
        embedder: Embedding model for chunk vectorisation.
        cache: Cache backend (Redis in prod, InMemory in tests).
        repository: Persistence layer (Postgres in prod).
        processor: Content cleaner and chunker.
        ranker: TF-IDF + credibility ranker.
        cache_ttl: Cache TTL in seconds (default 3600).
    """

    def __init__(
        self,
        primary_provider: SearchProvider,
        fetcher: ContentFetcher,
        embedder: EmbeddingModel,
        cache: Cache,
        repository: SearchRepository,
        processor: Optional[ContentProcessor] = None,
        ranker: Optional[RankingEngine] = None,
        fallback_provider: Optional[SearchProvider] = None,
        cache_ttl: int = 3600,
    ) -> None:
        self._primary = primary_provider
        self._fallback = fallback_provider
        self._fetcher = fetcher
        self._embedder = embedder
        self._cache = cache
        self._repository = repository
        self._processor = processor or ContentProcessor()
        self._ranker = ranker or RankingEngine()
        self._cache_ttl = cache_ttl

    async def search(
        self,
        query: str,
        max_results: int = 5,
        min_score: float = 0.0,
    ) -> dict[str, Any]:
        """
        Run the full pipeline and return a JSON-serialisable result dict.

        Returns:
            Dict with keys: query, results, total_results, processing_time_ms,
                           cache_hit, citations_markdown.
        """
        t0 = time.monotonic()

        cache_key = self._cache.make_key(query, str(max_results))
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.info("SearchOrchestrator: cache hit for %r", query)
            # Shallow-copy so callers cannot mutate the cached object
            return {**cached, "cache_hit": True}

        # 1. Web search
        candidates = await self._primary.search(query, max_results=max_results * 3)
        if not candidates and self._fallback:
            logger.warning("SearchOrchestrator: primary provider empty, trying fallback")
            candidates = await self._fallback.search(query, max_results=max_results * 3)

        if not candidates:
            return self._empty_response(query, t0)

        # 2. Fetch content
        urls = [c.url for c in candidates]
        fetched_pages = await self._fetcher.fetch_all(urls)
        content_map = {
            p.url: p.content for p in fetched_pages if p.success and p.content
        }

        # 3. Process + chunk, build chunks_by_url and items for ranking
        chunks_by_url: dict[str, list[Chunk]] = {}
        rank_items: list[tuple[str, str, str, list[Chunk]]] = []

        for candidate in candidates:
            raw = content_map.get(candidate.url) or candidate.snippet
            if not raw:
                rank_items.append((candidate.title, candidate.url, "", []))
                continue
            cleaned, chunks = self._processor.process(raw)
            chunks_by_url[candidate.url] = chunks
            rank_items.append((candidate.title, candidate.url, cleaned, chunks))

        # 4. Embed chunks (best-effort)
        chunks_by_url = await self._embed_chunks(chunks_by_url)
        # Refresh rank_items with embedded chunks
        rank_items = [
            (title, url, content, chunks_by_url.get(url, chunks))
            for title, url, content, chunks in rank_items
        ]

        # 5. Rank
        ranked: list[RankedResult] = self._ranker.rank(query, rank_items)
        filtered = [r for r in ranked if r.score >= min_score][:max_results]

        # 6. Persist (non-fatal)
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        try:
            payload_save = StoredSearchResult(
                query=query,
                params={"max_results": max_results, "min_score": min_score},
                results=[self._serialise_result(r) for r in filtered],
                processing_ms=elapsed_ms,
            )
            await self._repository.save(payload_save)
        except Exception as exc:
            logger.warning("SearchOrchestrator: persistence failed (non-fatal): %s", exc)

        # 7. Build response
        citations = [
            Citation(rank=r.rank, title=r.title, url=r.url, score=r.score)
            for r in filtered
        ]
        citations_md = "\n".join(c.to_markdown_link() for c in citations)

        # Store to cache WITHOUT cache_hit so callers each get a fresh copy
        cacheable: dict[str, Any] = {
            "query": query,
            "total_results": len(filtered),
            "processing_time_ms": elapsed_ms,
            "results": [self._serialise_result(r) for r in filtered],
            "citations_markdown": citations_md,
        }

        # 8. Cache (non-fatal)
        try:
            await self._cache.set(cache_key, cacheable, ttl=self._cache_ttl)
        except Exception as exc:
            logger.warning("SearchOrchestrator: cache write failed (non-fatal): %s", exc)

        # Return a NEW dict so the cached object is never aliased by callers
        return dict(cacheable, cache_hit=False)

    async def _embed_chunks(
        self, chunks_by_url: dict[str, list[Chunk]]
    ) -> dict[str, list[Chunk]]:
        """Embed all chunks across all URLs in a single batched call."""
        all_refs: list[tuple[str, int]] = []
        texts: list[str] = []

        for url, chunks in chunks_by_url.items():
            for idx, chunk in enumerate(chunks):
                all_refs.append((url, idx))
                texts.append(chunk.text)

        if not texts:
            return chunks_by_url

        try:
            embeddings = await self._embedder.embed_texts(texts)
            for (url, idx), embedding in zip(all_refs, embeddings):
                old = chunks_by_url[url][idx]
                chunks_by_url[url][idx] = Chunk(
                    chunk_id=old.chunk_id,
                    text=old.text,
                    char_count=old.char_count,
                    embedding=embedding,
                )
        except Exception as exc:
            logger.warning(
                "SearchOrchestrator: embedding skipped (non-fatal): %s", exc
            )

        return chunks_by_url

    def _serialise_result(self, r: RankedResult) -> dict[str, Any]:
        return {
            "rank": r.rank,
            "title": r.title,
            "url": r.url,
            "score": round(r.score, 4),
            "char_count": r.char_count,
            "chunk_count": r.chunk_count,
            "content": r.content,
        }

    def _empty_response(self, query: str, t0: float) -> dict[str, Any]:
        return {
            "query": query,
            "total_results": 0,
            "processing_time_ms": round((time.monotonic() - t0) * 1000),
            "cache_hit": False,
            "results": [],
            "citations_markdown": "",
        }
