import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from app.models.db.base import Base
from app.models.db.workspace import DEFAULT_WORKSPACE_ID

if TYPE_CHECKING:
    from app.models.db.query import StoredQuery
    from app.models.db.chunk import StoredChunk

class StoredResult(Base):
    """Persisted search result linked to a query."""
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    # Phase 12: multi-tenant workspace scoping
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, default=DEFAULT_WORKSPACE_ID, index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # --- migration 005: freshness routing (Phase 5) ----------------------
    # When the source content was last (re)fetched from the web. Drives the
    # freshness score the hybrid router uses to decide on a web refresh.
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Set TRUE when feedback flags the source as outdated.
    refresh_needed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    query: Mapped["StoredQuery"] = relationship("StoredQuery", back_populates="results")
    chunks: Mapped[list["StoredChunk"]] = relationship(
        "StoredChunk", back_populates="result", cascade="all, delete-orphan"
    )
