from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Hybrid Search for Agents"
    app_version: str = "0.1.0"
    debug: bool = False
    log_json: bool = False   # Set LOG_JSON=true in production for structured JSON logs

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

    # Search providers
    brave_api_key: str = ""   # Optional fallback — https://brave.com/search/api/

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5433/hybriddb"
    database_echo: bool = False
    db_pool_size: int = 10       # See .env.example for sizing guidance
    db_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600  # 1 hour

    # Embeddings
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    use_local_embeddings: bool = True  # default: local BGE model, no API key needed

    # Auth
    api_keys: str = ""
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
