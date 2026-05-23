"""
Hybrid retrieval endpoint (Phase 5).

`POST /api/v1/search/hybrid` — confidence-routed retrieval. Unlike `/search`,
which always crawls the web, this endpoint checks cache and local semantic
memory first and only refreshes from the web when memory confidence is low,
the stored content is stale, or the query is recency-sensitive.

The decision logic lives in `app.services.retrieval_router.RetrievalRouter`.
This handler is intentionally thin.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.request import HybridSearchRequest
from app.models.response import HybridSearchResponse
from app.services.retrieval_router import RetrievalRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["hybrid"])


@router.post("/search/hybrid", response_model=HybridSearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Confidence-routed hybrid retrieval: cache → local vector memory → web.

    The router classifies the query, scores how confident local memory is, and
    only crawls the web when needed. `routing_trace` on the response explains
    every decision it made.
    """
    try:
        return await RetrievalRouter(db).run(request)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Hybrid retrieval crashed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Hybrid retrieval failed: {e}") from e
