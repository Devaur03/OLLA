"""
PURPOSE: Freshness scoring for stored content (Phase 5).

A chunk that was scraped an hour ago and a chunk scraped two years ago are not
equally trustworthy — but *how much* staleness matters depends on the question.
A news answer rots in hours; a definition of "binary search" barely rots at all.

`FreshnessService.score()` returns a 0-1 freshness value using exponential
decay whose half-life is chosen per `QueryClass`. The router folds this into
its confidence calculation: stale content drags confidence down and triggers a
web refresh.

Pure, dependency-free, deterministic — safe to unit test.
"""

import logging
from datetime import datetime, timezone

from app.services.query_classifier_service import QueryClass

logger = logging.getLogger(__name__)

# Half-life (in hours) per query class: the age at which freshness == 0.5.
# News halves in 6h; evergreen content takes ~1 year.
_HALF_LIFE_HOURS: dict[QueryClass, float] = {
    QueryClass.NEWS: 6.0,
    QueryClass.RECENT: 72.0,  # 3 days
    QueryClass.COMPARISON: 24.0 * 90,  # 90 days
    QueryClass.TECHNICAL: 24.0 * 180,  # 180 days
    QueryClass.RESEARCH: 24.0 * 180,
    QueryClass.DEFINITION: 24.0 * 365,  # 1 year
    QueryClass.EVERGREEN: 24.0 * 365,
}
_DEFAULT_HALF_LIFE = 24.0 * 90


class FreshnessService:
    """Computes how 'fresh' stored content is, relative to a query class."""

    def score(
        self,
        last_refreshed_at: datetime | None,
        query_class: QueryClass = QueryClass.EVERGREEN,
        now: datetime | None = None,
    ) -> float:
        """
        Return a freshness score in [0.0, 1.0].

        1.0 = just refreshed; 0.5 = one half-life old; → 0.0 as content ages.
        A missing timestamp is treated as worst-case stale (0.0) so unknown-age
        content never blocks a web refresh.
        """
        if last_refreshed_at is None:
            return 0.0

        now = now or datetime.now(timezone.utc)
        # Tolerate naive datetimes coming back from the DB driver.
        if last_refreshed_at.tzinfo is None:
            last_refreshed_at = last_refreshed_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_hours = max(0.0, (now - last_refreshed_at).total_seconds() / 3600.0)
        half_life = _HALF_LIFE_HOURS.get(query_class, _DEFAULT_HALF_LIFE)

        # Exponential decay: freshness = 0.5 ** (age / half_life)
        freshness = 0.5 ** (age_hours / half_life)
        return round(min(1.0, max(0.0, freshness)), 4)

    def is_stale(
        self,
        last_refreshed_at: datetime | None,
        query_class: QueryClass = QueryClass.EVERGREEN,
        threshold: float = 0.4,
        now: datetime | None = None,
    ) -> bool:
        """True when freshness has decayed below `threshold` — refresh advised."""
        return self.score(last_refreshed_at, query_class, now) < threshold
