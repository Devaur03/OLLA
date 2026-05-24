from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db.base import Base
from app.models.db.workspace import DEFAULT_WORKSPACE_ID


class SourceTrust(Base):
    """
    Learned per-domain trust (Phase 7), scoped to a workspace (Phase 12).

    Distinct from the *static* weights in `CredibilityService`: this table is
    the *dynamic* half — it accumulates from real user feedback. A domain that
    is repeatedly marked useful climbs; one repeatedly flagged bad/outdated
    sinks. `SourceTrustService` blends this with the static baseline.

    Phase 12: the primary key is now (workspace_id, domain) so each workspace
    maintains independent trust rankings.
    """

    __tablename__ = "source_trust"

    # Phase 12: composite primary key (workspace_id, domain)
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
        default=DEFAULT_WORKSPACE_ID,
    )
    domain: Mapped[str] = mapped_column(String(255), primary_key=True)

    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    bad_source_count: Mapped[int] = mapped_column(Integer, default=0)
    outdated_count: Mapped[int] = mapped_column(Integer, default=0)
    citation_success_count: Mapped[int] = mapped_column(Integer, default=0)
    refresh_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
