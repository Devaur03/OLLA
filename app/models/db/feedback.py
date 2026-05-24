import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base
from app.models.db.workspace import DEFAULT_WORKSPACE_ID


class Feedback(Base):
    """
    A single feedback event (Phase 6).

    Feedback can be attached at four levels — `answer`, `citation`, `chunk`,
    or `source` — and only the identifiers relevant to that level are filled
    in. Foreign keys use ON DELETE SET NULL so feedback survives even if the
    underlying query/result/chunk is later pruned.

    IMPORTANT: feedback updates *metadata and ranking signals* only. It never
    rewrites scraped content.
    """

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Phase 12: multi-tenant workspace scoping
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
        index=True,
    )
    query_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("queries.id", ondelete="SET NULL"), nullable=True
    )
    result_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("results.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
    )
    source_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'answer' | 'citation' | 'chunk' | 'source'
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'useful' | 'not_useful' | 'incorrect' | 'outdated' | 'bad_source' | 'missing_context'
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
