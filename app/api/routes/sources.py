"""
Source inspection + refresh endpoints (Phase 8).

  GET  /api/v1/sources/{result_id}          — read a stored result + chunks
  POST /api/v1/sources/{result_id}/refresh  — re-crawl and replace its content
  GET  /api/v1/sources/trusted-domains      — learned per-domain trust ranking
  GET  /api/v1/sources/recent-queries       — recent query history

The last two are small read-only views that also back the MCP resources.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.sources_service import SourcesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("/trusted-domains")
async def trusted_domains(
    http_request: Request,
    limit: int = Query(default=25, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """Learned per-domain trust, highest first."""
    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT domain, trust_score, positive_count, negative_count,
                           citation_success_count, refresh_needed
                    FROM source_trust
                    WHERE workspace_id = :ws
                    ORDER BY trust_score DESC
                    LIMIT :lim
                    """
                ),
                {"lim": limit, "ws": getattr(http_request.state, "workspace_id", None)},
            )
        ).fetchall()
        return {"domains": [dict(r._mapping) for r in rows]}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Lookup failed: {e}") from e


@router.get("/recent-queries")
async def recent_queries(
    http_request: Request,
    limit: int = Query(default=25, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """Most recent queries with their result counts."""
    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT query_text, created_at, result_count, processing_ms
                    FROM queries
                    WHERE workspace_id = :ws
                    ORDER BY created_at DESC
                    LIMIT :lim
                    """
                ),
                {"lim": limit, "ws": getattr(http_request.state, "workspace_id", None)},
            )
        ).fetchall()
        return {
            "queries": [
                {
                    "query": r.query_text,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "result_count": r.result_count,
                    "processing_ms": r.processing_ms,
                }
                for r in rows
            ]
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Lookup failed: {e}") from e


@router.get("/{result_id}")
async def get_source(
    http_request: Request, result_id: str, db: AsyncSession = Depends(get_db_session)
):
    """Read one stored result and its chunks back out of the knowledge base."""
    source = await SourcesService(db, getattr(http_request.state, "workspace_id", None)).get_source(
        result_id
    )
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {result_id} not found")
    return source


@router.post("/{result_id}/refresh")
async def refresh_source(
    http_request: Request, result_id: str, db: AsyncSession = Depends(get_db_session)
):
    """Re-crawl a stored source's URL and replace its content and chunks."""
    try:
        return await SourcesService(
            db, getattr(http_request.state, "workspace_id", None)
        ).refresh_source(result_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("Source refresh failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Refresh failed: {e}") from e
