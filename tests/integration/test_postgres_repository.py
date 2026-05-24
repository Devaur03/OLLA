"""
Integration tests — require a real PostgreSQL instance.

Run with:  pytest tests/integration/ -m integration

(File kept under its original path; it now exercises the live persistence
stack instead of the archived PostgresSearchRepository.)
"""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_database_is_reachable(db_session):
    """The configured database accepts a connection and a trivial query."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_core_tables_exist(db_session):
    """Migrations have created the core tables the pipeline writes to."""
    rows = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    tables = {r[0] for r in rows}
    assert {"queries", "results", "chunks"}.issubset(tables)
