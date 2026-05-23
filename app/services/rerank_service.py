"""
PURPOSE: Optional cross-encoder reranking (Phase 10).

Bi-encoder vector search (the pgvector path) is fast but approximate — it
embeds the query and each chunk independently. A cross-encoder reads the query
and a candidate *together* and scores their actual relevance, which is more
accurate but too slow to run over a whole corpus. The standard pattern: retrieve
a wide candidate set cheaply, then rerank the top handful with a cross-encoder.

This service follows the project's graceful-degradation convention (cf.
`AnswerService`, `EmbedService`): if `sentence-transformers` or the reranker
model is unavailable, `rerank()` returns the input order unchanged and
`available` is False. Reranking is therefore always safe to call.

Enable with `ENABLE_RERANKING=true`; override the model with `RERANKER_MODEL`.
"""

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class RerankService:
    """Cross-encoder reranker with safe fallback when the model is absent."""

    _model = None             # class-level cache — load the model once
    _load_failed = False

    def __init__(self):
        self.model_name = getattr(settings, "reranker_model", "BAAI/bge-reranker-base")
        self.enabled = getattr(settings, "enable_reranking", False)

    @property
    def available(self) -> bool:
        """True only if reranking is enabled and the model loaded successfully."""
        return self.enabled and not RerankService._load_failed

    def _load(self) -> bool:
        """Lazily load the cross-encoder. Returns False if it cannot be loaded."""
        if RerankService._model is not None:
            return True
        if RerankService._load_failed:
            return False
        try:
            from sentence_transformers import CrossEncoder
            RerankService._model = CrossEncoder(self.model_name)
            logger.info("RerankService: loaded cross-encoder %s", self.model_name)
            return True
        except Exception as e:  # noqa: BLE001
            RerankService._load_failed = True
            logger.warning(
                "RerankService: reranker unavailable (%s) — passthrough mode", e
            )
            return False

    async def rerank(
        self, query: str, items: list, text_of=None, top_k: int | None = None
    ) -> list:
        """
        Reorder `items` by cross-encoder relevance to `query`.

        `text_of` extracts the text to score from each item (defaults to using
        the item's `content`, then `text`, attribute/key). On any failure or
        when the model is unavailable, the original order is returned — so this
        call never breaks a pipeline.
        """
        if not self.enabled or not items:
            return list(items) if top_k is None else list(items)[:top_k]
        if not self._load():
            return list(items) if top_k is None else list(items)[:top_k]

        extract = text_of or _default_text
        pairs = [(query, extract(it) or "") for it in items]
        try:
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None, lambda: RerankService._model.predict(pairs)
            )
            ranked = [it for _, it in sorted(
                zip(scores, items), key=lambda p: p[0], reverse=True
            )]
        except Exception as e:  # noqa: BLE001
            logger.warning("RerankService: predict failed (%s) — passthrough", e)
            ranked = list(items)
        return ranked if top_k is None else ranked[:top_k]


def _default_text(item) -> str:
    """Best-effort text extraction from a dict or object."""
    if isinstance(item, dict):
        return item.get("content") or item.get("text") or ""
    return getattr(item, "content", None) or getattr(item, "text", "") or ""
