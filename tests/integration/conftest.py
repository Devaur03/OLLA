"""
Integration conftest — real database session per test.

Requires: DATABASE_URL pointing to a migrated test Postgres instance.
Run with: pytest tests/integration/ -m integration
"""

import pytest


@pytest.fixture
async def db_session():
    """Real AsyncSession wrapped in a rolled-back transaction."""
    from app.db.session import AsyncSessionLocal  # deferred import

    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
            await session.rollback()
