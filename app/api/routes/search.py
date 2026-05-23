"""
Main search endpoint.

The pipeline itself lives in `app.services.pipeline.SearchPipeline` — a staged,
traced orchestrator. This handler is intentionally thin: parse the request,
run the pipeline, translate pipeline errors into HTTP responses.

Pipeline stages: cache → search → fetch → clean → chunk → rank → store → graph.
See OPTIMIZATION_PLAN.md §2.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.request import SearchRequest
from app.models.response import SearchResponse
from app.services.pipeline import PipelineError, SearchPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: Request,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Search the web, fetch + clean + chunk + rank content, persist it, and
    return structured, citation-ready JSON.

    Resilience features (see COMPARISON_README):
    - Multi-backend DuckDuckGo (auto → html → lite) with Brave fallback.
    - Jina → direct-scrape → snippet fetch waterfall.
    - safesearch / timelimit / region request controls.
    - Prompt-injection sanitization of scraped content.
    - Per-stage trace + graceful degradation (`degraded` flag on the response).
    """
    workspace_id = getattr(request.state, "workspace_id", None)
    pipeline = SearchPipeline(db, workspace_id)
    try:
        return await pipeline.run(body)
    except PipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Search pipeline crashed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Search pipeline failed: {e}") from e
