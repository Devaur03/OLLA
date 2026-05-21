"""
PURPOSE: STM → LTM memory tier management (COMPARISON_README §6, §10.4, §10.11).

Inspired by Turiya's two-tier memory. Every freshly fetched chunk starts in
short-term memory ('stm'). Chunks that prove useful — high confidence AND
retrieved repeatedly — are promoted to long-term memory ('ltm'). Stale, low-
confidence STM chunks are pruned so the store does not bloat indefinitely.

These operations are intended to run as a periodic background job (APScheduler
/ Celery beat / the `schedule` skill). They are also safe to call ad hoc.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryService:
    """Promotes, prunes and reports on the STM/LTM chunk tiers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def promote_to_ltm(self) -> int:
        """
        Promote high-confidence, frequently-retrieved STM chunks to LTM.
        Returns the number of chunks promoted.
        """
        result = await self.db.execute(
            text(
                """
                UPDATE chunks
                SET memory_tier = 'ltm'
                WHERE memory_tier = 'stm'
                  AND confidence >= :conf
                  AND retrieval_count >= :retr
                """
            ),
            {
                "conf": settings.ltm_confidence_threshold,
                "retr": settings.ltm_retrieval_threshold,
            },
        )
        promoted = result.rowcount or 0
        if promoted:
            logger.info("MemoryService: promoted %d chunk(s) STM → LTM", promoted)
        return promoted

    async def prune_stm(self) -> int:
        """
        Delete stale, low-confidence STM chunks older than the configured age.
        LTM chunks are never pruned. Returns the number of chunks deleted.
        """
        result = await self.db.execute(
            text(
                """
                DELETE FROM chunks
                WHERE memory_tier = 'stm'
                  AND confidence < :conf
                  AND char_count >= 0
                  AND id IN (
                      SELECT id FROM chunks
                      WHERE memory_tier = 'stm'
                        AND confidence < :conf
                  )
                  AND result_id IN (
                      SELECT r.id FROM results r
                      JOIN queries q ON r.query_id = q.id
                      WHERE q.created_at < NOW() - (:days || ' days')::interval
                  )
                """
            ),
            {"conf": settings.stm_prune_confidence, "days": settings.stm_prune_age_days},
        )
        pruned = result.rowcount or 0
        if pruned:
            logger.info("MemoryService: pruned %d stale STM chunk(s)", pruned)
        return pruned

    async def stats(self) -> dict:
        """Return a snapshot of memory-tier counts for the dashboard."""
        result = await self.db.execute(
            text(
                """
                SELECT memory_tier,
                       COUNT(*)        AS n,
                       AVG(confidence) AS avg_conf
                FROM chunks
                GROUP BY memory_tier
                """
            )
        )
        out: dict = {"stm": 0, "ltm": 0, "avg_confidence": {}}
        for row in result.fetchall():
            tier = row.memory_tier or "stm"
            out[tier] = int(row.n)
            out["avg_confidence"][tier] = round(float(row.avg_conf or 0.0), 4)
        return out

    async def run_maintenance(self) -> dict:
        """Convenience: promote then prune in one pass. Commits the session."""
        promoted = await self.promote_to_ltm()
        pruned = await self.prune_stm()
        await self.db.commit()
        return {"promoted": promoted, "pruned": pruned}
