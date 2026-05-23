"""
PURPOSE: Data-retention purging (Phase 12).

A self-hosted retrieval store grows without bound — every search writes a
query, its results, their chunks, the embeddings, and a stack of agent traces.
For privacy and for disk hygiene, deployments need a way to forget old data.

`RetentionService.purge(days)` deletes everything older than a cutoff:
  - agent_traces  (by created_at)
  - feedback      (by created_at)
  - queries       (by created_at) — results, chunks, chunk_edges follow via
                  ON DELETE CASCADE.

It is safe to run repeatedly and safe to schedule (the `schedule` skill / a
cron / APScheduler). `stats()` reports table sizes and the oldest record so an
operator can see what a purge would affect.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Tables purged directly by an age cutoff. `queries` cascades to results /
# chunks / chunk_edges, so those are not listed separately.
_AGE_TABLES = ("agent_traces", "feedback", "queries")


class RetentionService:
    """Purges stale data and reports on store size."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def purge(self, days: int) -> dict:
        """
        Delete every record older than `days` days.

        Returns a dict of {table: rows_deleted}. Raises ValueError if `days`
        is not a positive integer — purging "older than 0 days" would wipe
        everything and is almost certainly a mistake.
        """
        if days <= 0:
            raise ValueError("retention purge requires days > 0")

        deleted: dict[str, int] = {}
        for table in _AGE_TABLES:
            try:
                result = await self.db.execute(
                    text(
                        f"DELETE FROM {table} "
                        f"WHERE created_at < NOW() - make_interval(days => :days)"
                    ),
                    {"days": days},
                )
                deleted[table] = result.rowcount or 0
            except Exception as e:  # noqa: BLE001
                logger.warning("RetentionService: purge of %s failed: %s", table, e)
                deleted[table] = -1  # -1 signals "purge attempt failed"

        logger.info("RetentionService: purged data older than %d days: %s",
                    days, deleted)
        return deleted

    async def stats(self) -> dict:
        """Row counts per table plus the oldest query timestamp."""
        out: dict = {"counts": {}, "oldest_query": None, "newest_query": None}
        tables = ("queries", "results", "chunks", "chunk_edges",
                  "agent_traces", "feedback", "source_trust")
        for table in tables:
            try:
                row = (
                    await self.db.execute(text(f"SELECT COUNT(*) AS n FROM {table}"))
                ).first()
                out["counts"][table] = int(row.n) if row else 0
            except Exception as e:  # noqa: BLE001
                logger.warning("RetentionService: count of %s failed: %s", table, e)
                out["counts"][table] = None

        try:
            row = (
                await self.db.execute(
                    text("SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest "
                         "FROM queries")
                )
            ).first()
            if row and row.oldest:
                out["oldest_query"] = row.oldest.isoformat()
            if row and row.newest:
                out["newest_query"] = row.newest.isoformat()
        except Exception as e:  # noqa: BLE001
            logger.warning("RetentionService: oldest-query lookup failed: %s", e)
        return out
