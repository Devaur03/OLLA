"""
Dependency-injection container.

Uses dependency-injector (pip install dependency-injector) to wire together
all infrastructure implementations against the domain interfaces.

Usage in FastAPI routes:

    from app.container import Container
    from dependency_injector.wiring import inject, Provide

    @router.post("/search")
    @inject
    async def search(
        body: SearchRequest,
        orchestrator: SearchOrchestrator = Depends(Provide[Container.orchestrator]),
    ):
        ...

The container is initialised once at startup in app/main.py via
    container = Container()
    container.wire(modules=[...])
"""
from __future__ import annotations

from dependency_injector import containers, providers

from app.config import settings as _settings
from app.infrastructure.search.duckduckgo import DuckDuckGoSearch
from app.infrastructure.search.brave import BraveSearch
from app.infrastructure.fetchers.jina_reader import JinaReaderFetcher
from app.infrastructure.embeddings.bge_local import BGELocalEmbeddings
from app.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddings
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.cache.in_memory_cache import InMemoryCache
from app.domain.services.content_processor import ContentProcessor
from app.domain.services.ranking_engine import RankingEngine
from app.domain.services.search_orchestrator import SearchOrchestrator


class Container(containers.DeclarativeContainer):
    """
    Application DI container.

    Providers are singletons unless noted otherwise.  Thread-safety is handled
    by dependency-injector; each provider is initialised at most once.
    """

    # ------------------------------------------------------------------ config
    config = providers.Configuration()

    # ------------------------------------------------------------------ search providers
    duckduckgo_provider = providers.Singleton(
        DuckDuckGoSearch,
        max_results=providers.Callable(lambda: _settings.max_search_results),
    )

    brave_provider = providers.Singleton(
        BraveSearch,
        api_key=providers.Callable(lambda: _settings.brave_api_key),
        max_results=providers.Callable(lambda: _settings.max_search_results),
    )

    # ------------------------------------------------------------------ fetcher
    content_fetcher = providers.Singleton(
        JinaReaderFetcher,
        timeout=providers.Callable(lambda: float(_settings.fetch_timeout_seconds)),
        max_concurrent=providers.Callable(lambda: _settings.max_concurrent_fetches),
    )

    # ------------------------------------------------------------------ embedder (chosen by config)
    _bge_embedder = providers.Singleton(BGELocalEmbeddings)
    _openai_embedder = providers.Singleton(
        OpenAIEmbeddings,
        api_key=providers.Callable(lambda: _settings.openai_api_key or ""),
    )

    embedder = providers.Selector(
        providers.Callable(lambda: "local" if _settings.use_local_embeddings else "openai"),
        local=_bge_embedder,
        openai=_openai_embedder,
    )

    # ------------------------------------------------------------------ cache
    cache = providers.Singleton(
        RedisCache,
        url=providers.Callable(lambda: _settings.redis_url),
        default_ttl=providers.Callable(lambda: _settings.cache_ttl_seconds),
    )

    # ------------------------------------------------------------------ domain services
    processor = providers.Singleton(ContentProcessor)
    ranker = providers.Singleton(RankingEngine)

    # ------------------------------------------------------------------ orchestrator
    # Note: repository is request-scoped (injected per-request via FastAPI Depends)
    # and therefore NOT wired here.  The route handler passes the session-bound
    # repository to orchestrator.search() or uses the convenience factory below.
    orchestrator = providers.Factory(
        SearchOrchestrator,
        primary_provider=duckduckgo_provider,
        fallback_provider=brave_provider,
        fetcher=content_fetcher,
        embedder=embedder,
        cache=cache,
        processor=processor,
        ranker=ranker,
        cache_ttl=providers.Callable(lambda: _settings.cache_ttl_seconds),
    )
