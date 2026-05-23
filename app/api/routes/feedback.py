"""
Feedback endpoints (Phase 6 & 7).

`POST /api/v1/feedback`        — submit feedback on an answer / citation /
                                 chunk / source. Recording feedback also
                                 updates ranking signals (Phase 7).
`GET  /api/v1/feedback/stats`  — aggregate feedback analytics for the dashboard.

The decision/learning logic lives in `app.services.feedback_service`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.request import FeedbackRequest
from app.models.response import FeedbackResponse, FeedbackStats
from app.services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Record a feedback event and apply its ranking-signal effects.

    Feedback updates metadata and ranking signals only — it never rewrites
    scraped content. The `effects` field lists exactly what was updated.
    """
    try:
        feedback_id, effects = await FeedbackService(db).record(request)
        return FeedbackResponse(
            feedback_id=feedback_id,
            level=request.level.value,
            feedback_type=request.feedback_type.value,
            recorded=True,
            effects=effects,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Feedback recording failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Failed to record feedback: {e}") from e


@router.get("/feedback/stats", response_model=FeedbackStats)
async def feedback_stats(db: AsyncSession = Depends(get_db_session)):
    """Aggregate feedback analytics: counts, satisfaction rate, source quality."""
    try:
        return FeedbackStats(**await FeedbackService(db).stats())
    except Exception as e:  # noqa: BLE001
        logger.error("Feedback stats failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Failed to load feedback stats: {e}") from e
