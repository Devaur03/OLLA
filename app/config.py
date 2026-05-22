from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Hybrid Search for Agents"
    app_version: str = "0.1.0"
    debug: bool = False
    log_json: bool = False

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
    jina_api_key: str = ""                 # optional — higher Jina rate limits

    # Search providers
    brave_api_key: str = ""
    ddg_backends: str = "auto,html,lite"   # ordered DDG backend fallback chain
    default_safesearch: str = "moderate"   # on | moderate | off
    default_region: str = "wt-wt"
    proxy_pool: str = ""                   # comma-separated http(s) proxy URLs

    # Pipeline behaviour
    enable_sanitization: bool = True       # strip prompt-injection from scraped text
    enable_entity_extraction: bool = False  # spaCy NER on chunks (needs en_core_web_sm)
    enable_knowledge_graph: bool = True    # build chunk_edges after embedding

    # Memory tiers / confidence
    confidence_default: float = 0.5
    ltm_confidence_threshold: float = 0.7  # promote STM -> LTM at/above this
    ltm_retrieval_threshold: int = 3       # ...and at/above this retrieval count
    stm_prune_confidence: float = 0.3      # prune STM below this confidence
    stm_prune_age_days: int = 30

    # Knowledge graph
    graph_similarity_threshold: float = 0.85  # min cosine sim to draw a chunk edge
    graph_max_edges_per_chunk: int = 10

    # RAG answer synthesis (local LLM via Ollama)
    enable_answer_synthesis: bool = True
    ollama_base_url: str = "http://localhost:11434"
    # llama3.2:1b — small + fast on CPU (the 3B model times out on modest
    # hardware). Override with OLLAMA_MODEL in .env (e.g. qwen2.5:1.5b).
    ollama_model: str = "llama3.2:1b"
    ollama_timeout: float = 150.0          # read timeout (connect is fixed at 5s)
    ollama_num_predict: int = 512          # cap on answer length (tokens)
    answer_max_context_chars: int = 3000   # total source text fed to the LLM

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5433/hybriddb"
    database_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600

    # Embeddings
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    use_local_embeddings: bool = True

    # Auth
    api_keys: str = ""
    require_auth: bool = False

    # Deployment
    app_base_url: str = "http://localhost:8000"

    # Stripe (set in Railway / Render dashboard — never commit)
    stripe_secret_key:      str = ""
    stripe_webhook_secret:  str = ""
    stripe_publishable_key: str = ""
    stripe_price_starter:   str = ""
    stripe_price_pro:       str = ""
    stripe_price_team:      str = ""
    stripe_price_enterprise: str = ""

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
