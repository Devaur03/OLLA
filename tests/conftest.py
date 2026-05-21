"""
Root conftest — pure Python fixtures only.

No FastAPI, SQLAlchemy, or Redis imports here.
Infrastructure-dependent fixtures live in the conftest.py of the layer that needs them:
  tests/e2e/conftest.py       — client fixture (imports app)
  tests/integration/conftest.py — db_session fixture (needs real Postgres)

NOTE: the project was unified onto the single `app/services/*` pipeline.
The old layered architecture (`app/domain`, `app/infrastructure`, `container.py`)
was archived to `archive/legacy_layered_architecture/`. The unit tests that only
exercised that archived layer are skipped via `collect_ignore_glob` below.
See OPTIMIZATION_PLAN.md §1.
"""
import pytest

# Tests below only exercised the archived layered architecture. They are
# ignored at collection time so pytest does not fail importing removed modules.
collect_ignore_glob = [
    "unit/domain/*",
    "unit/services/*",
    "integration/test_postgres_repository.py",
]


@pytest.fixture
def sample_query() -> str:
    """A representative search query used across service-level tests."""
    return "how does pgvector work for semantic search"
