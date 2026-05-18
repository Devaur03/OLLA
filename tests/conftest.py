"""
Root conftest — pure Python fixtures only.

No FastAPI, SQLAlchemy, or Redis imports here.
Infrastructure-dependent fixtures live in the conftest.py of the layer that needs them:
  tests/e2e/conftest.py       — client fixture (imports app)
  tests/integration/conftest.py — db_session fixture (needs real Postgres)
"""
import pytest
from unittest.mock import AsyncMock

from app.infrastructure.cache.in_memory_cache import InMemoryCache
from app.domain.interfaces.search_provider import SearchCandidate
from app.domain.interfaces.content_fetcher import FetchedPage


# ── In-memory cache ──────────────────────────────────────────────────────────

@pytest.fixture
def memory_cache():
    cache = InMemoryCache()
    yield cache
    cache.clear()


# ── Mock search provider ──────────────────────────────────────────────────────

@pytest.fixture
def mock_search_candidates():
    return [
        SearchCandidate(
            title="pgvector: vector similarity search for Postgres",
            url="https://github.com/pgvector/pgvector",
            snippet="Open-source vector similarity search with exact and ANN support.",
        ),
        SearchCandidate(
            title="Getting Started with pgvector",
            url="https://www.postgresql.org/about/news/pgvector-released/",
            snippet="pgvector adds HNSW indexing for faster approximate nearest neighbor search.",
        ),
    ]


@pytest.fixture
def mock_search_provider(mock_search_candidates):
    provider = AsyncMock()
    provider.search.return_value = mock_search_candidates
    provider.health_check.return_value = True
    return provider


# ── Mock content fetcher ──────────────────────────────────────────────────────

@pytest.fixture
def mock_fetcher():
    fetcher = AsyncMock()
    fetcher.fetch_all.return_value = [
        FetchedPage(
            url="https://github.com/pgvector/pgvector",
            content=(
                "pgvector is a Postgres extension for vector similarity search. "
                "It supports exact and approximate nearest neighbor search. "
                "Install with CREATE EXTENSION vector. "
                "Supports L2 distance, inner product, and cosine distance operators. "
                "Works with any language that has a Postgres driver."
            ),
            success=True,
        ),
        FetchedPage(
            url="https://www.postgresql.org/about/news/pgvector-released/",
            content=(
                "pgvector introduces HNSW indexing for faster approximate nearest neighbor queries. "
                "The update also improves IVFFlat build times significantly. "
                "Vector dimensions up to 16000 are now supported."
            ),
            success=True,
        ),
    ]
    fetcher.health_check.return_value = True
    return fetcher


# ── Mock embedder ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_embedder():
    embedder = AsyncMock()
    embedder.embed_texts.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
    embedder.embed_query.return_value = [0.1] * 384
    embedder.dimensions = 384
    return embedder


# ── Mock repository ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.save.return_value = "test-query-id-123"
    repo.health_check.return_value = True
    return repo
