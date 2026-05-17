import logging
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)


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
        """Embed using local BGE model via sentence-transformers."""
        if self._local_model is None:
            # Lazy load to avoid import error if sentence-transformers not installed
            try:
                from sentence_transformers import SentenceTransformer
                self._local_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
                logger.info("EmbedService: loaded local BGE model")
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )

        # Run in executor to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._local_model.encode(
                texts, normalize_embeddings=True
            ).tolist()
        )
        return embeddings
