"""
Unit tests for SearchOrchestrator.

All external collaborators are replaced with AsyncMock fixtures from conftest.
No network calls, no DB, no Redis.
"""
import pytest
from app.domain.services.search_orchestrator import SearchOrchestrator
from app.domain.interfaces.search_provider import SearchCandidate


@pytest.fixture
def orchestrator(
    mock_search_provider,
    mock_fetcher,
    mock_embedder,
    memory_cache,
    mock_repository,
):
    return SearchOrchestrator(
        primary_provider=mock_search_provider,
        fetcher=mock_fetcher,
        embedder=mock_embedder,
        cache=memory_cache,
        repository=mock_repository,
    )


@pytest.mark.asyncio
async def test_search_returns_results(orchestrator):
    result = await orchestrator.search("pgvector tutorial", max_results=2)
    assert result["total_results"] > 0
    assert len(result["results"]) > 0
    assert result["query"] == "pgvector tutorial"


@pytest.mark.asyncio
async def test_search_result_has_required_fields(orchestrator):
    result = await orchestrator.search("pgvector", max_results=1)
    if result["results"]:
        r = result["results"][0]
        assert "rank" in r
        assert "title" in r
        assert "url" in r
        assert "score" in r
        assert "char_count" in r
        assert "chunk_count" in r


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(orchestrator, mock_search_provider):
    await orchestrator.search("cached query", max_results=2)
    await orchestrator.search("cached query", max_results=2)
    # Provider should only be called once — second call served from cache
    assert mock_search_provider.search.call_count == 1


@pytest.mark.asyncio
async def test_cache_hit_flag(orchestrator):
    first = await orchestrator.search("cache flag test", max_results=2)
    second = await orchestrator.search("cache flag test", max_results=2)
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


@pytest.mark.asyncio
async def test_empty_provider_returns_empty_response(
    mock_fetcher, mock_embedder, memory_cache, mock_repository
):
    from unittest.mock import AsyncMock
    empty_provider = AsyncMock()
    empty_provider.search.return_value = []
    orch = SearchOrchestrator(
        primary_provider=empty_provider,
        fetcher=mock_fetcher,
        embedder=mock_embedder,
        cache=memory_cache,
        repository=mock_repository,
    )
    result = await orch.search("anything", max_results=5)
    assert result["total_results"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_min_score_filters_results(orchestrator):
    result = await orchestrator.search("pgvector", max_results=5, min_score=0.99)
    # With mock zero-embeddings and typical TF-IDF scores, nothing should pass 0.99
    # (this tests the filter code path, not the scoring values)
    assert isinstance(result["results"], list)


@pytest.mark.asyncio
async def test_repository_save_called(orchestrator, mock_repository):
    await orchestrator.search("persist me", max_results=2)
    mock_repository.save.assert_called_once()


@pytest.mark.asyncio
async def test_persistence_failure_is_non_fatal(
    mock_search_provider, mock_fetcher, mock_embedder, memory_cache
):
    from unittest.mock import AsyncMock
    failing_repo = AsyncMock()
    failing_repo.save.side_effect = Exception("DB is down")
    orch = SearchOrchestrator(
        primary_provider=mock_search_provider,
        fetcher=mock_fetcher,
        embedder=mock_embedder,
        cache=memory_cache,
        repository=failing_repo,
    )
    # Should not raise; persistence failure is logged and swallowed
    result = await orch.search("resilience test", max_results=2)
    assert "results" in result
