"""
Root conftest — pure-Python fixtures shared across the unit test suite.

No FastAPI / SQLAlchemy / Redis imports here. Infrastructure-dependent
fixtures live in the conftest of the layer that needs them:
  tests/e2e/conftest.py          — HTTPX client wired to the FastAPI app
  tests/integration/conftest.py  — real AsyncSession (needs Postgres)
"""
import pytest


@pytest.fixture
def sample_query() -> str:
    """A representative search query used across service-level tests."""
    return "how does pgvector work for semantic search"
