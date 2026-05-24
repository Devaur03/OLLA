import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db.base import Base
from app.models.db.workspace import DEFAULT_WORKSPACE_ID

if TYPE_CHECKING:
    from app.models.db.result import StoredResult


class StoredChunk(Base):
    """
    Persisted text chunk.

    The `embedding` column is added in migration 002 (pgvector). Migration 004
    adds the Turiya-inspired self-improving columns: per-chunk confidence,
    retrieval bookkeeping, memory tier, and extracted entities.
    """

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False
    )
    # Phase 12: multi-tenant workspace scoping
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        default=DEFAULT_WORKSPACE_ID,
        index=True,
    )
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # embedding column added in migration 002

    # --- migration 004: confidence + memory tiers (COMPARISON_README §6, §10) ---
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    last_validated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 'stm' = recently fetched, 'ltm' = consolidated + validated
    memory_tier: Mapped[str] = mapped_column(String(10), default="stm")
    # spaCy-extracted named entities: [{"text": ..., "label": ...}, ...]
    entities: Mapped[list] = mapped_column(JSONB, default=list)

    # --- migration 005: feedback-aware ranking (Phase 6/7) ---------------
    positive_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    # Aggregate usefulness in [0,1]; nudged by feedback, used in ranking.
    usefulness_score: Mapped[float] = mapped_column(Float, default=0.5)

    # --- migration 007: parent-child chunking (Phase 10) -----------------
    # is_parent: a large context chunk. parent_id: on a child, its parent's id.
    is_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    result: Mapped["StoredResult"] = relationship("StoredResult", back_populates="chunks")
