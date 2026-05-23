"""SQLAlchemy ORM model for the api_keys table."""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db.base import Base

if TYPE_CHECKING:
    from app.models.db.usage_event import UsageEvent
    from app.models.db.user import User


class ApiKey(Base):
    __tablename__ = "api_keys"

    id:         Mapped[str]  = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:    Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash:   Mapped[str]  = mapped_column(String(64),  unique=True, nullable=False)
    key_prefix: Mapped[str]  = mapped_column(String(20),  nullable=False)
    name:       Mapped[str]  = mapped_column(String(255), nullable=False, default="Default key")
    # RBAC (migration 006): 'admin' | 'member'. Gates the /admin/* endpoints.
    role:       Mapped[str]  = mapped_column(String(20), nullable=False, default="member")
    is_active:  Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user:         Mapped["User"]          = relationship(back_populates="api_keys")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="api_key")
