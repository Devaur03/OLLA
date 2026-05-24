"""
Workspace management endpoints (Phase 12).

POST /api/v1/workspaces            — create a new workspace
GET  /api/v1/workspaces            — list workspaces for the authenticated user
GET  /api/v1/workspaces/{ws_id}    — get workspace details
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.db.workspace import Workspace

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: str | None = None


class CreateWorkspaceResponse(BaseModel):
    message: str
    workspace: WorkspaceInfo


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user_id


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateWorkspaceResponse, status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new workspace for the authenticated user."""
    user_id = _get_user_id(request)

    ws = Workspace(
        id=str(uuid.uuid4()),
        name=body.name.strip(),
        owner_id=user_id,
    )
    db.add(ws)
    await db.commit()

    logger.info("workspaces.create: %s for user %s", ws.id, user_id)
    return CreateWorkspaceResponse(
        message="Workspace created.",
        workspace=WorkspaceInfo(
            id=ws.id,
            name=ws.name,
            owner_id=ws.owner_id,
            created_at=ws.created_at.isoformat() if ws.created_at else None,
        ),
    )


@router.get("", response_model=list[WorkspaceInfo])
async def list_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """List all workspaces the authenticated user owns."""
    user_id = _get_user_id(request)
    result = await db.execute(
        select(Workspace)
        .where(Workspace.owner_id == user_id)
        .order_by(Workspace.created_at.desc())
    )
    workspaces = result.scalars().all()
    return [
        WorkspaceInfo(
            id=w.id,
            name=w.name,
            owner_id=w.owner_id,
            created_at=w.created_at.isoformat() if w.created_at else None,
        )
        for w in workspaces
    ]


@router.get("/{workspace_id}", response_model=WorkspaceInfo)
async def get_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Get details of a specific workspace."""
    user_id = _get_user_id(request)
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.owner_id == user_id,
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return WorkspaceInfo(
        id=ws.id,
        name=ws.name,
        owner_id=ws.owner_id,
        created_at=ws.created_at.isoformat() if ws.created_at else None,
    )
