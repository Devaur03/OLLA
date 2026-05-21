"""
PURPOSE: Per-chunk confidence scoring (COMPARISON_README §6, §10.3).

A chunk's confidence rises each time it is retrieved and validated as useful,
and falls when retrieved but not validated. Over time this makes the vector
store self-improving: high-confidence chunks float to the top, stale/low-value
chunks sink and become eligible for pruning.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_VALIDATED_DELTA = 0.05
_UNVALIDATED_DELTA = -0.02


class ConfidenceService:
    """Adjusts the `confidence` column on chunks as they are used."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_retrieval(self, chunk_id: str, validated: bool = True) -> None:
        """
        Register that a chunk was retrieved. `validated=True` nudges confidence
        up, `False` nudges it down. Always increments retrieval_count.
        """
        delta = _VALIDATED_DELTA if validated else _UNVALIDATED_DELTA
        try:
            await self.db.execute(
                text(
                    """
                    UPDATE chunks
                    SET confidence = LEAST(1.0, GREATEST(0.0, confidence + :delta)),
                        retrieval_count = retrieval_count + 1,
                        last_validated = NOW()
                    WHERE id = :id
                    """
                ),
                {"delta": delta, "id": chunk_id},
            )
        except Exception as e:  # noqa: BLE001 — confidence is best-effort
            logger.warning("ConfidenceService: failed to update %s: %s", chunk_id, e)

    async def record_retrievals(self, chunk_ids: list[str], validated: bool = True) -> None:
        """Batch variant of record_retrieval."""
        if not chunk_ids:
            return
        delta = _VALIDATED_DELTA if validated else _UNVALIDATED_DELTA
        try:
            await self.db.execute(
                text(
                    """
                    UPDATE chunks
                    SET confidence = LEAST(1.0, GREATEST(0.0, confidence + :delta)),
                        retrieval_count = retrieval_count + 1,
                        last_validated = NOW()
                    WHERE id = ANY(:ids)
                    """
                ),
                {"delta": delta, "ids": chunk_ids},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ConfidenceService: batch update failed: %s", e)
