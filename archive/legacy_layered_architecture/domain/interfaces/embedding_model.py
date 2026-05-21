"""Abstract interface for text embedding models."""
from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    """Contract every embedding model must satisfy.

    Implementations: BGELocalEmbeddings, OpenAIEmbeddings.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Number of dimensions produced by this model."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Strings to embed.

        Returns:
            One embedding vector per input text. Returns [] on failure.
        """

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string. Convenience wrapper around embed_texts."""
        results = await self.embed_texts([query])
        return results[0] if results else []
