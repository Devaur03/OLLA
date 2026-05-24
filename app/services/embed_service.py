import logging
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)

# The local embedding model is expensive to construct. Cache it process-wide
# so it loads once — not on every EmbedService() instance / every search.
_LOCAL_MODEL = None


def _load_local_model():
    """Load (once) and return the cached local sentence-transformers model."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            ) from e
        _LOCAL_MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
        logger.info("EmbedService: loaded local BGE model (cached process-wide)")
    return _LOCAL_MODEL


class EmbedService:
    """
    Generates text embeddings for semantic search.
    Supports OpenAI API and local sentence-transformers (BGE).
    """

    def __init__(self):
        self.use_local = settings.use_local_embeddings
        self._local_model = None

        if not self.use_local and not settings.openai_api_key:
            logger.warning(
                "EmbedService: OPENAI_API_KEY not set and use_local_embeddings=False. "
                "Semantic search will not work. Set OPENAI_API_KEY or USE_LOCAL_EMBEDDINGS=true."
            )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).
            Returns empty list on failure.
        """
        if not texts:
            return []

        try:
            if self.use_local:
                return await self._embed_local(texts)
            else:
                return await self._embed_openai(texts)
        except Exception as e:
            logger.error(f"EmbedService: embedding failed: {e}")
            return []

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a single query string.
        Returns empty list on failure.
        """
        results = await self.embed_texts([query])
        return results[0] if results else []

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed using OpenAI text-embedding-3-small API."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        # OpenAI supports batching — send all texts in one request
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Embed using the cached local BGE model via sentence-transformers."""
        model = _load_local_model()
        # Run in executor to avoid blocking the async event loop.
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(texts, normalize_embeddings=True).tolist(),
        )
        return embeddings
