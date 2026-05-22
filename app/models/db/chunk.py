import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db.base import Base

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

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("results.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # embedding column added in migration 002

    # --- migration 004: confidence + memory tiers (COMPARISON_README §6, §10) ---
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    last_validated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'stm' = recently fetched, 'ltm' = consolidated + validated
    memory_tier: Mapped[str] = mapped_column(String(10), default="stm")
    # spaCy-extracted named entities: [{"text": ..., "label": ...}, ...]
    entities: Mapped[list] = mapped_column(JSONB, default=list)

    result: Mapped["StoredResult"] = relationship("StoredResult", back_populates="chunks")
