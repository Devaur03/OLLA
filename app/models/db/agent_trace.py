import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class AgentTrace(Base):
    """
    Per-stage observability record for a single search pipeline run
    (COMPARISON_README §8, §10.5).

    One row per pipeline stage (search, fetch, clean, chunk, rank, store,
    graph) so the dashboard and logs can pinpoint where a query slowed down
    or which stage fell back / failed.
    """

    __tablename__ = "agent_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Nullable: a trace may be recorded even if the query row was never stored.
    query_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success/failed/fallback/skipped
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Free-form context (counts, error messages, backend used, etc.).
    # Attribute is not named `metadata` — that name is reserved by SQLAlchemy.
    trace_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
