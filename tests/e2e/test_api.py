"""
End-to-end API tests — exercise the full FastAPI stack.

These tests stub no dependencies. They require:
  - Running PostgreSQL (make docker-up)
  - Running Redis      (make docker-up)
  - Internet access for DDG search

Run with: pytest tests/e2e/ -v -m e2e
"""

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "redis" in data["components"]
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_search_validation_too_short(client):
    response = await client.post("/api/v1/search", json={"query": "hi"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_validation_max_results_exceeded(client):
    response = await client.post(
        "/api/v1/search",
        json={"query": "test query", "max_results": 99},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.skip(reason="Makes real network calls — enable in full E2E runs only")
async def test_full_search_pipeline(client):
    response = await client.post(
        "/api/v1/search",
        json={"query": "Python FastAPI tutorial", "max_results": 2},
    )
    assert response.status_code in [200, 503]
    if response.status_code == 200:
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        if data["results"]:
            r = data["results"][0]
            assert r["rank"] == 1
            assert 0.0 <= r["score"] <= 1.0
