"""
E2E conftest — imports the FastAPI app and provides an HTTPX test client.

These fixtures require all infrastructure drivers (asyncpg, redis-py, etc.)
to be installed, even if the actual services are not running.
"""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """Async test client wired to the full FastAPI app (no real network)."""
    from app.main import app  # deferred: only imported when e2e tests run

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=10.0,
    ) as ac:
        yield ac
