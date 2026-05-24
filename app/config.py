from pydantic_settings import BaseSettings
from pydantic import model_validator
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

    # Retrieval quality (Phase 10)
    enable_reranking: bool = False             # cross-encoder rerank (needs model)
    reranker_model: str = "BAAI/bge-reranker-base"
    enable_query_expansion: bool = True        # multi-query expansion in DEEP mode
    enable_citation_verification: bool = True  # verify answer [n] citations
    diversity_max_per_domain: int = 2          # soft per-domain cap in result sets
    enable_parent_child_chunking: bool = False  # hierarchical child/parent chunks
    parent_chunk_size: int = 2000              # char size of a parent context chunk
    deep_research_max_queries: int = 3         # query variants crawled in DEEP mode

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

    # Privacy (Phase 3)
    # local_only: hard privacy mode — no data may leave the machine via an
    #   external AI API. Forces local embeddings and clears the OpenAI key.
    # disable_external_llm: block the external embedding API specifically.
    # Note: web search/fetch are the product's core function and are NOT
    #   disabled by these flags; they govern external *AI* providers only.
    local_only: bool = False
    disable_external_llm: bool = False

    # Data retention (Phase 12)
    # retention_days: purge queries/results/chunks/traces/feedback older than
    #   this many days. 0 disables retention purging entirely.
    retention_days: int = 0

    # Rate limiting (Phase 12) — max requests per client per rolling minute.
    # 0 disables the limiter. Client = X-API-Key header, else peer IP.
    rate_limit_per_minute: int = 0

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

    @model_validator(mode="after")
    def _enforce_privacy_mode(self) -> "Settings":
        """
        Privacy mode (Phase 3): when `local_only` is set, guarantee that no
        request can reach an external AI provider — force local embeddings and
        clear the OpenAI key. `disable_external_llm` does the same for the
        embedding provider without the rest of local-only mode.
        """
        if self.local_only or self.disable_external_llm:
            self.use_local_embeddings = True
            self.openai_api_key = None
        if self.local_only:
            # No external web-search provider key either.
            self.brave_api_key = ""
        return self

    @property
    def privacy_mode(self) -> bool:
        """True when any external AI provider is blocked."""
        return self.local_only or self.disable_external_llm

    def get_api_keys(self) -> set[str]:
        """Parse comma-separated API keys into a set."""
        if not self.api_keys:
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
