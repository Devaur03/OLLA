"""Nested pydantic-settings configuration.

Environment variables use double-underscore as nested delimiter:
    SEARCH__MAX_RESULTS=10
    DB__POOL_SIZE=20
    CACHE__TTL_SECONDS=7200

For convenience, the flat variable names from the old config.py still work
because pydantic-settings also reads them via env_prefix.
"""

from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class SearchSettings(BaseSettings):
    provider: str = "duckduckgo"  # duckduckgo | brave
    max_results: int = 5
    max_chars_per_page: int = 8000
    fetch_timeout_seconds: int = 15
    max_concurrent_fetches: int = 5
    brave_api_key: str = ""
    fetch_base_url: str = "https://r.jina.ai"

    model_config = SettingsConfigDict(env_prefix="SEARCH__", env_file=".env", extra="ignore")


class ChunkSettings(BaseSettings):
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    model_config = SettingsConfigDict(env_prefix="CHUNK__", env_file=".env", extra="ignore")


class CacheSettings(BaseSettings):
    provider: str = "redis"  # redis | memory
    url: str = "redis://localhost:6379"
    ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_prefix="CACHE__", env_file=".env", extra="ignore")


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://postgres:password@localhost:5433/hybriddb"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20

    model_config = SettingsConfigDict(env_prefix="DB__", env_file=".env", extra="ignore")


class EmbeddingSettings(BaseSettings):
    provider: str = "local"  # local | openai
    openai_api_key: str = ""
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    local_model: str = "BAAI/bge-small-en-v1.5"

    model_config = SettingsConfigDict(env_prefix="EMBED__", env_file=".env", extra="ignore")


class AppSettings(BaseSettings):
    """Top-level settings object — compose sub-settings via nested fields."""

    name: str = "OLLA"
    version: str = "0.1.0"
    debug: bool = False
    log_json: bool = False
    log_dir: str = "logs"
    require_auth: bool = False
    api_keys: str = ""

    search: SearchSettings = Field(default_factory=SearchSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    chunk: ChunkSettings = Field(default_factory=ChunkSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_api_keys(self) -> set[str]:
        if not self.api_keys:
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache()
def get_app_settings() -> AppSettings:
    return AppSettings()
