"""
PURPOSE: Data import (Phase 12) — the inverse of `ExportService`.

Re-ingests a previously exported document so a fresh deployment can recover
the *learned signals* that took real usage to accumulate:

  - source_trust  — upserted by domain (learned per-domain trust survives).
  - feedback      — re-inserted as analytics records.

Deliberately NOT imported: queries / results / chunks / embeddings. Those are
re-derivable by simply re-running searches, and re-inserting them would mean
re-creating a tangle of foreign keys and absent embeddings. Imported feedback
therefore has its query/result/chunk foreign keys set to NULL — the event and
its domain/level/type are preserved, the dangling references are not.

Import is idempotent for source_trust (upsert) and additive for feedback.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ImportService:
    """Re-ingests an ExportService document."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_data(self, payload: dict) -> dict:
        """Import `source_trust` and `feedback` sections from an export dict."""
        summary = {"source_trust": 0, "feedback": 0, "errors": []}

        for row in payload.get("source_trust", []) or []:
            try:
                await self._upsert_trust(row)
                summary["source_trust"] += 1
            except Exception as e:  # noqa: BLE001
                summary["errors"].append(f"source_trust {row.get('domain')}: {e}")

        for row in payload.get("feedback", []) or []:
            try:
                await self._insert_feedback(row)
                summary["feedback"] += 1
            except Exception as e:  # noqa: BLE001
                summary["errors"].append(f"feedback {row.get('id')}: {e}")

        logger.info(
            "ImportService: imported %d trust rows, %d feedback rows, %d errors",
            summary["source_trust"], summary["feedback"], len(summary["errors"]),
        )
        return summary

    async def _upsert_trust(self, row: dict) -> None:
        domain = row.get("domain")
        if not domain:
            raise ValueError("source_trust row missing 'domain'")
        await self.db.execute(
            text(
                """
                INSERT INTO source_trust
                    (domain, trust_score, positive_count, negative_count,
                     bad_source_count, outdated_count, citation_success_count,
                     refresh_needed, updated_at)
                VALUES
                    (:domain, :trust, :pos, :neg, :bad, :outd, :cite,
                     :refresh, NOW())
                ON CONFLICT (domain) DO UPDATE SET
                    trust_score            = EXCLUDED.trust_score,
                    positive_count         = EXCLUDED.positive_count,
                    negative_count         = EXCLUDED.negative_count,
                    bad_source_count       = EXCLUDED.bad_source_count,
                    outdated_count         = EXCLUDED.outdated_count,
                    citation_success_count = EXCLUDED.citation_success_count,
                    refresh_needed         = EXCLUDED.refresh_needed,
                    updated_at             = NOW()
                """
            ),
            {
                "domain": domain,
                "trust": float(row.get("trust_score", 0.5) or 0.5),
                "pos": int(row.get("positive_count", 0) or 0),
                "neg": int(row.get("negative_count", 0) or 0),
                "bad": int(row.get("bad_source_count", 0) or 0),
                "outd": int(row.get("outdated_count", 0) or 0),
                "cite": int(row.get("citation_success_count", 0) or 0),
                "refresh": bool(row.get("refresh_needed", False)),
            },
        )

    async def _insert_feedback(self, row: dict) -> None:
        # FK columns are NULLed: the referenced query/result/chunk may not
        # exist in this deployment. The event itself is preserved.
        await self.db.execute(
            text(
                """
                INSERT INTO feedback
                    (id, query_id, result_id, chunk_id, source_domain,
                     source_url, level, feedback_type, comment, created_at)
                VALUES
                    (:id, NULL, NULL, NULL, :domain, :url,
                     :level, :ftype, :comment,
                     COALESCE(CAST(:created_at AS timestamptz), NOW()))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "domain": row.get("source_domain"),
                "url": row.get("source_url"),
                "level": row.get("level") or "source",
                "ftype": row.get("feedback_type") or "useful",
                "comment": row.get("comment"),
                "created_at": row.get("created_at"),
            },
        )
