from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Hybrid Search for Agents"
    app_version: str = "0.1.0"
    debug: bool = False

    # Search
    max_search_results: int = 5
    max_chars_per_page: int = 8000
    fetch_timeout_seconds: int = 15
    max_concurrent_fetches: int = 5

    # Chunking
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    # Fetch API
    fetch_base_url: str = "https://r.jina.ai"

    # PostgreSQL
    database_url: str = "postgresql+psycopg://postgres:password@localhost:5433/hybriddb"
    database_echo: bool = False

    # Redis (Phase 2B)
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600  # 1 hour

    # Embeddings (Phase 3)
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    use_local_embeddings: bool = False  # True = use BGE instead of OpenAI

    # Auth (Phase 5)
    api_keys: str = ""  # Comma-separated list of valid API keys
    require_auth: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_api_keys(self) -> set[str]:
        """Parse comma-separated API keys into a set."""
        if not self.api_keys:
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
