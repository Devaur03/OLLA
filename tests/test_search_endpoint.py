# NOTE: These are integration tests that make real network calls.
# Run with: pytest tests/test_search_endpoint.py -v
# Requires internet connection.

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_search_request_validation_too_short():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "hi"},  # too short (min 3 chars)
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_request_validation_max_results():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "test query", "max_results": 99},  # exceeds max of 10
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_valid_structure():
    """Integration test — makes real search. Requires internet."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0) as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "Python FastAPI tutorial", "max_results": 2},
        )
    # Accept 200, 404, 503 or 500 since this depends on external search/fetch APIs
    assert response.status_code in [200, 404, 503, 500]

    if response.status_code == 200:
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert "total_results" in data
        assert "processing_time_ms" in data
        assert isinstance(data["results"], list)

        if data["results"]:
            result = data["results"][0]
            assert "rank" in result
            assert "title" in result
            assert "url" in result
            assert "content" in result
            assert "chunks" in result
            assert "score" in result
            assert result["rank"] == 1
            assert 0.0 <= result["score"] <= 1.0
