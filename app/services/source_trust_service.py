"""
PURPOSE: Learned per-domain trust (Phase 7).

`CredibilityService` is the *static* half of source quality — a hand-curated
table of domain weights. This service is the *dynamic* half: it accumulates
real feedback so the system learns which domains actually serve good answers.

`get_trust(url)` returns a blend of the two:

    trust = 0.5 * static_credibility + 0.5 * learned_trust

A brand-new domain therefore inherits its static credibility (learned starts
neutral at 0.5). As feedback arrives the learned half pulls the blend up or
down, so a domain that keeps producing bad citations sinks even if it started
with a high static weight.

Feedback never edits scraped content — only this trust signal and the
`refresh_needed` flag.
"""

import logging
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credibility_service import CredibilityService

logger = logging.getLogger(__name__)

# How far each feedback type nudges the learned trust score.
_TRUST_DELTAS: dict[str, float] = {
    "useful": 0.05,
    "not_useful": -0.04,
    "incorrect": -0.06,
    "bad_source": -0.12,
    "outdated": -0.03,
    "missing_context": -0.02,
}
_MIN_TRUST, _MAX_TRUST = 0.0, 1.0


def domain_of(url: str) -> str:
    """Extract a normalised registrable-ish domain from a URL (strips www.)."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or url.lower()
    except Exception:  # noqa: BLE001
        return (url or "").lower()


class SourceTrustService:
    """Reads and updates the `source_trust` table; blends with static scores."""

    def __init__(self, db: AsyncSession, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id
        self._credibility = CredibilityService()

    # ----------------------------------------------------------- reads

    async def get_trust(self, url: str) -> float:
        """Blended trust score in [0,1] for the domain behind `url`."""
        domain = domain_of(url)
        static = self._credibility.score(url)
        learned = await self._learned_trust(domain)
        return round(0.5 * static + 0.5 * learned, 4)

    async def get_trust_map(self, urls: list[str]) -> dict[str, float]:
        """Batch variant of `get_trust` — one map keyed by URL."""
        return {u: await self.get_trust(u) for u in urls}

    async def _learned_trust(self, domain: str) -> float:
        """The learned half only; 0.5 (neutral) when the domain is unseen."""
        try:
            row = (
                await self.db.execute(
                    text(
                        "SELECT trust_score FROM source_trust WHERE workspace_id = :ws AND domain = :d"
                    ),
                    {"ws": self.workspace_id, "d": domain},
                )
            ).first()
            return float(row.trust_score) if row else 0.5
        except Exception as e:  # noqa: BLE001
            logger.warning("SourceTrustService: trust lookup failed: %s", e)
            return 0.5

    # ----------------------------------------------------------- writes

    async def apply_feedback(self, url: str, feedback_type: str) -> None:
        """
        Fold one feedback event into a domain's learned trust.

        Upserts the `source_trust` row, adjusts the matching counters, recomputes
        `trust_score`, and raises `refresh_needed` when content is flagged
        outdated. Best-effort: a failure here must not break feedback recording.
        """
        domain = domain_of(url)
        delta = _TRUST_DELTAS.get(feedback_type, 0.0)
        positive = 1 if feedback_type == "useful" else 0
        negative = 1 if feedback_type in {"not_useful", "incorrect", "missing_context"} else 0
        bad = 1 if feedback_type == "bad_source" else 0
        outdated = 1 if feedback_type == "outdated" else 0

        try:
            # Ensure a row exists (seeded at the static credibility score so a
            # first-ever negative does not over-punish a reputable domain).
            seed = self._credibility.score(url)
            await self.db.execute(
                text(
                    """
                    INSERT INTO source_trust (workspace_id, domain, trust_score)
                    VALUES (:ws, :d, :seed)
                    ON CONFLICT (workspace_id, domain) DO NOTHING
                    """
                ),
                {"ws": self.workspace_id, "d": domain, "seed": seed},
            )
            await self.db.execute(
                text(
                    """
                    UPDATE source_trust SET
                        trust_score            = LEAST(:hi, GREATEST(:lo, trust_score + :delta)),
                        positive_count          = positive_count + :pos,
                        negative_count          = negative_count + :neg,
                        bad_source_count        = bad_source_count + :bad,
                        outdated_count          = outdated_count + :outd,
                        refresh_needed          = (refresh_needed OR :outd = 1),
                        updated_at              = NOW()
                    WHERE workspace_id = :ws AND domain = :d
                    """
                ),
                {
                    "ws": self.workspace_id,
                    "d": domain,
                    "delta": delta,
                    "pos": positive,
                    "neg": negative,
                    "bad": bad,
                    "outd": outdated,
                    "lo": _MIN_TRUST,
                    "hi": _MAX_TRUST,
                },
            )
            logger.info("SourceTrustService: %s %+.2f on %r", domain, delta, feedback_type)
        except Exception as e:  # noqa: BLE001
            logger.warning("SourceTrustService: apply_feedback failed: %s", e)

    async def record_citation_success(self, url: str) -> None:
        """Bump a domain's citation-success counter (small positive nudge)."""
        domain = domain_of(url)
        try:
            seed = self._credibility.score(url)
            await self.db.execute(
                text(
                    "INSERT INTO source_trust (workspace_id, domain, trust_score) VALUES (:ws, :d, :seed) "
                    "ON CONFLICT (workspace_id, domain) DO NOTHING"
                ),
                {"ws": self.workspace_id, "d": domain, "seed": seed},
            )
            await self.db.execute(
                text(
                    """
                    UPDATE source_trust SET
                        citation_success_count = citation_success_count + 1,
                        trust_score = LEAST(:hi, trust_score + 0.01),
                        updated_at = NOW()
                    WHERE workspace_id = :ws AND domain = :d
                    """
                ),
                {"ws": self.workspace_id, "d": domain, "hi": _MAX_TRUST},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("SourceTrustService: record_citation_success failed: %s", e)

    async def worst_sources(self, limit: int = 10) -> list[dict]:
        """Lowest-trust domains — feeds the feedback analytics dashboard."""
        try:
            rows = (
                await self.db.execute(
                    text(
                        """
                        SELECT domain, trust_score, negative_count, bad_source_count,
                               outdated_count, refresh_needed
                        FROM source_trust
                        WHERE workspace_id = :ws
                        ORDER BY trust_score ASC
                        LIMIT :lim
                        """
                    ),
                    {"ws": self.workspace_id, "lim": limit},
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]
        except Exception as e:  # noqa: BLE001
            logger.warning("SourceTrustService: worst_sources failed: %s", e)
            return []

    async def best_sources(self, limit: int = 10) -> list[dict]:
        """Highest-trust domains — feeds the feedback analytics dashboard."""
        try:
            rows = (
                await self.db.execute(
                    text(
                        """
                        SELECT domain, trust_score, positive_count,
                               citation_success_count
                        FROM source_trust
                        WHERE workspace_id = :ws
                        ORDER BY trust_score DESC
                        LIMIT :lim
                        """
                    ),
                    {"ws": self.workspace_id, "lim": limit},
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]
        except Exception as e:  # noqa: BLE001
            logger.warning("SourceTrustService: best_sources failed: %s", e)
            return []
