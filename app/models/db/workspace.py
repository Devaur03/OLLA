"""SQLAlchemy ORM model for the workspaces table (Phase 12)."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db.base import Base

if TYPE_CHECKING:
    from app.models.db.user import User
    from app.models.db.api_key import ApiKey

# A hard-coded UUID used as the "global" workspace for static API keys,
# unauthenticated requests (REQUIRE_AUTH=false), and legacy data that
# pre-dates the workspace migration.
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_WORKSPACE_NAME = "Default"


class Workspace(Base):
    """
    A tenant-isolated workspace (Phase 12).

    Every retrieval artifact (query, result, chunk), feedback event, and
    source-trust row belongs to exactly one workspace.  API keys are bound
    to a workspace so requests are automatically scoped.
    """

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="workspaces")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="workspace")
