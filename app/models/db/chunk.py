import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.db.base import Base

if TYPE_CHECKING:
    from app.models.db.result import StoredResult


class StoredChunk(Base):
    """
    Persisted text chunk.
    The `embedding` column is added in Phase 3 via Alembic migration
    once the pgvector extension is enabled.
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
    # embedding column added in Phase 3 migration

    result: Mapped["StoredResult"] = relationship("StoredResult", back_populates="chunks")
