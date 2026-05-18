"""
BAAI/bge-small-en-v1.5 implementation of EmbeddingModel.

Runs inference in a thread-pool executor so the async event loop
is never blocked by the CPU-bound encode() call.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.domain.interfaces.embedding_model import EmbeddingModel
from app.core.errors.exceptions import EmbeddingError

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class BGELocalEmbeddings(EmbeddingModel):
    """
    Local embedding model using sentence-transformers.
    No API key required; first call downloads the model (~130 MB).

    Attributes:
        model_name: HuggingFace model ID (default: BAAI/bge-small-en-v1.5).
        device: Torch device string ("cpu", "cuda", "mps").
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model: SentenceTransformer | None = None

    # ------------------------------------------------------------------
    # EmbeddingModel interface
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> int:
        return 384  # bge-small-en-v1.5 output size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            model = await self._get_model()
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: model.encode(texts, normalize_embeddings=True).tolist(),
            )
            return embeddings
        except Exception as exc:
            raise EmbeddingError("BGE encode failed: " + str(exc)) from exc

    async def embed_query(self, text: str) -> list[float]:
        prefixed = _QUERY_PREFIX + text
        results = await self.embed_texts([prefixed])
        return results[0]

    async def health_check(self) -> bool:
        try:
            await self.embed_texts(["health check"])
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_model(self) -> "SentenceTransformer":
        if self._model is None:
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(None, self._load_model)
        return self._model

    def _load_model(self) -> "SentenceTransformer":
        from sentence_transformers import SentenceTransformer
        logger.info("BGELocalEmbeddings: loading model %s on %s", self.model_name, self.device)
        model = SentenceTransformer(self.model_name, device=self.device)
        logger.info("BGELocalEmbeddings: model loaded (dim=%d)", self.dimensions)
        return model
