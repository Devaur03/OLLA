import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING
from app.models.db.base import Base

if TYPE_CHECKING:
    from app.models.db.result import StoredResult

class StoredQuery(Base):
    """Persisted search query with metadata."""
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Relationship: one query → many results
    results: Mapped[list["StoredResult"]] = relationship(
        "StoredResult", back_populates="query", cascade="all, delete-orphan"
    )
