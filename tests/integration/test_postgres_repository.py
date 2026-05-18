"""
Integration tests for PostgresSearchRepository.

Requires: DATABASE_URL pointing to a running PostgreSQL instance with migrations applied.
Run with: pytest tests/integration/ -v -m integration
"""
import pytest
from app.domain.interfaces.repository import StoredSearchResult

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires live PostgreSQL — run in CI or with make docker-up")
async def test_save_and_health_check(db_session):
    from app.infrastructure.persistence.postgres_repository import PostgresSearchRepository
    repo = PostgresSearchRepository(db_session)

    assert await repo.health_check() is True

    payload = StoredSearchResult(
        query="integration test query",
        params={"max_results": 2},
        results=[
            {
                "rank": 1,
                "title": "Test Result",
                "url": "https://example.com",
                "score": 0.85,
                "char_count": 100,
                "chunk_count": 1,
                "content": "Test content for integration test.",
                "chunks": [],
            }
        ],
        processing_ms=42,
    )
    query_id = await repo.save(payload)
    assert query_id is not None
    assert isinstance(query_id, str)
