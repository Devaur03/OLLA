"""
Admin endpoints (Phase 12) — data retention and export.

  GET  /api/v1/admin/retention/stats  — store size + oldest/newest record
  POST /api/v1/admin/retention/purge  — delete data older than N days
  GET  /api/v1/admin/export           — dump sources / feedback / trust as JSON

These are operator endpoints. They sit behind the same API-key auth as the
rest of the API (when `REQUIRE_AUTH=true`); finer-grained role-based access
control is a separate, still-pending Phase 12 item.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rbac import require_admin
from app.config import settings
from app.db.session import get_db_session
from app.services.export_service import ExportService
from app.services.import_service import ImportService
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)

# Every /admin/* route requires the 'admin' role (RBAC, Phase 12). When
# REQUIRE_AUTH is off, self-hosted single-operator mode passes the check.
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[require_admin])


class PurgeRequest(BaseModel):
    """Body for a retention purge. `days` defaults to settings.retention_days."""

    days: int | None = Field(
        default=None,
        ge=1,
        description="Delete records older than this many days "
        "(defaults to the configured RETENTION_DAYS)",
    )


@router.get("/retention/stats")
async def retention_stats(db: AsyncSession = Depends(get_db_session)):
    """Report store size, the oldest/newest query, and the configured policy."""
    stats = await RetentionService(db).stats()
    stats["retention_days_configured"] = settings.retention_days
    return stats


@router.post("/retention/purge")
async def retention_purge(
    request: PurgeRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Delete data older than `days` (body) or the configured `RETENTION_DAYS`.

    Fails with 400 if neither is set, so a purge can never run unbounded.
    """
    days = request.days if request and request.days is not None else settings.retention_days
    if not days or days <= 0:
        raise HTTPException(
            status_code=400,
            detail="No retention window: pass 'days' in the body or set "
            "RETENTION_DAYS in the environment.",
        )
    try:
        deleted = await RetentionService(db).purge(days)
        return {"purged_older_than_days": days, "deleted": deleted}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("Retention purge failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Purge failed: {e}") from e


@router.get("/export")
async def export_data(
    limit: int = Query(default=1000, ge=1, le=100_000, description="Max rows per section"),
    db: AsyncSession = Depends(get_db_session),
):
    """Export sources, feedback, learned source trust, and query history."""
    try:
        return await ExportService(db).export(limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.error("Export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Export failed: {e}") from e


@router.post("/import")
async def import_data(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Re-ingest a previous export. Restores learned source trust (upsert) and
    feedback events; queries/results/chunks are intentionally not imported.
    """
    if not isinstance(payload, dict) or not (
        payload.get("source_trust") or payload.get("feedback")
    ):
        raise HTTPException(
            status_code=400,
            detail="Body must be an export document with a 'source_trust' "
            "and/or 'feedback' section.",
        )
    try:
        return await ImportService(db).import_data(payload)
    except Exception as e:  # noqa: BLE001
        logger.error("Import failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Import failed: {e}") from e
