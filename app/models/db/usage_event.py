"""SQLAlchemy ORM model for the usage_events table."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.db.base import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id:      Mapped[str | None] = mapped_column(String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    user_id:         Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id",    ondelete="SET NULL"), nullable=True)
    endpoint:        Mapped[str]      = mapped_column(String(100), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    cache_hit:       Mapped[bool]     = mapped_column(Boolean(), nullable=False, default=False)
    status_code:     Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at:      Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    api_key: Mapped["ApiKey | None"] = relationship(back_populates="usage_events")
    user:    Mapped["User | None"]   = relationship(back_populates="usage_events")
