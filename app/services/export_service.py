"""
PURPOSE: Data export (Phase 12).

Lets an operator pull the knowledge base and its learned signals out of the
system — for backup, migration between deployments, audit, or simply to own
their data. The export is plain JSON-serialisable Python.

`ExportService.export()` returns four sections:
  - sources       — stored results (title, url, score, freshness flags)
  - feedback      — every feedback event
  - source_trust  — learned per-domain trust table
  - queries       — query history metadata

Embeddings themselves are intentionally NOT exported (large, and re-derivable
by re-running `/search/embed-and-store`); chunk *metadata* counts are included
so the size of the corpus is visible.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _jsonable(value):
    """Make a DB cell JSON-serialisable (datetimes → ISO strings)."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows(result) -> list[dict]:
    return [{k: _jsonable(v) for k, v in row._mapping.items()} for row in result.fetchall()]


class ExportService:
    """Exports stored content, feedback, and learned signals as JSON."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export(self, limit: int = 1000) -> dict:
        """
        Build the export document.

        `limit` caps the per-section row count so an export of a huge store
        stays bounded; pass a larger value for a full dump.
        """
        limit = max(1, min(limit, 100_000))
        export: dict = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "limit": limit,
            "sources": [],
            "feedback": [],
            "source_trust": [],
            "queries": [],
            "summary": {},
        }

        export["sources"] = await self._safe(
            f"""
            SELECT id, query_id, rank, title, url, score, char_count,
                   chunk_count, fetched_at, last_refreshed_at, refresh_needed
            FROM results
            ORDER BY fetched_at DESC
            LIMIT {limit}
            """
        )
        export["feedback"] = await self._safe(
            f"""
            SELECT id, query_id, result_id, chunk_id, source_domain, source_url,
                   level, feedback_type, comment, created_at
            FROM feedback
            ORDER BY created_at DESC
            LIMIT {limit}
            """
        )
        export["source_trust"] = await self._safe(
            f"""
            SELECT domain, trust_score, positive_count, negative_count,
                   bad_source_count, outdated_count, citation_success_count,
                   refresh_needed, updated_at
            FROM source_trust
            ORDER BY trust_score DESC
            LIMIT {limit}
            """
        )
        export["queries"] = await self._safe(
            f"""
            SELECT id, query_text, query_hash, created_at, result_count,
                   processing_ms
            FROM queries
            ORDER BY created_at DESC
            LIMIT {limit}
            """
        )

        export["summary"] = {
            "sources": len(export["sources"]),
            "feedback": len(export["feedback"]),
            "source_trust": len(export["source_trust"]),
            "queries": len(export["queries"]),
        }
        logger.info("ExportService: exported %s", export["summary"])
        return export

    async def _safe(self, sql: str) -> list[dict]:
        """Run a SELECT, returning [] (not raising) on any failure."""
        try:
            return _rows(await self.db.execute(text(sql)))
        except Exception as e:  # noqa: BLE001
            logger.warning("ExportService: section query failed: %s", e)
            return []
