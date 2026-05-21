import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base


class ChunkEdge(Base):
    """
    A weighted edge in the knowledge graph between two semantically related
    chunks (COMPARISON_README §8, §10.6). Edges are drawn when the cosine
    similarity of two chunk embeddings exceeds a configurable threshold.

    Enables multi-hop graph-traversal retrieval that pure vector search misses.
    """
    __tablename__ = "chunk_edges"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chunk_a_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    chunk_b_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String(50), default="semantic_similarity")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
