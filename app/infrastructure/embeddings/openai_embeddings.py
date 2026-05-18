"""
OpenAI text-embedding-3-small implementation of EmbeddingModel.

Used when USE_LOCAL_EMBEDDINGS=false and OPENAI_API_KEY is set.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.domain.interfaces.embedding_model import EmbeddingModel
from app.core.errors.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

_OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"
_DEFAULT_MODEL = "text-embedding-3-small"
_DIMENSIONS = 1536


class OpenAIEmbeddings(EmbeddingModel):
    """
    OpenAI embedding model via direct REST call (no openai SDK dependency).

    Attributes:
        api_key: OpenAI API key (required).
        model: Embedding model name (default: text-embedding-3-small).
    """

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("OpenAIEmbeddings requires a non-empty api_key")
        self._api_key = api_key
        self._model = model

    # ------------------------------------------------------------------
    # EmbeddingModel interface
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self._model, "input": texts}
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(_OPENAI_EMBED_URL, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise EmbeddingError(
                        "OpenAI 401 Unauthorized. Check OPENAI_API_KEY in .env."
                    )
                if resp.status_code == 429:
                    raise EmbeddingError(
                        "OpenAI rate limit exceeded. Slow down or upgrade your plan."
                    )
                resp.raise_for_status()
                data = resp.json()
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("OpenAI embedding call failed: " + str(exc)) from exc

    async def health_check(self) -> bool:
        try:
            await self.embed_texts(["ping"])
            return True
        except Exception:
            return False
