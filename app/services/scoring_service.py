"""
PURPOSE: The feedback-aware weighted scoring formula (Phase 7).

A single place that turns six independent signals into one final ranking score.
Keeping it isolated means the weights are auditable, testable, and tunable
without touching the pipeline or the router.

    final_score = semantic       * 0.40
                + keyword         * 0.15
                + source_trust    * 0.15
                + freshness       * 0.10
                + feedback        * 0.10
                + content_density * 0.10

Every input is expected in [0,1]; the output is clamped to [0,1]. Callers that
lack a signal (e.g. the web pipeline has no embeddings at rank time) pass a
sensible neutral default rather than zero, so a missing signal does not
silently crater a result.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Component weights — must sum to 1.0.
WEIGHTS: dict[str, float] = {
    "semantic": 0.40,
    "keyword": 0.15,
    "source_trust": 0.15,
    "freshness": 0.10,
    "feedback": 0.10,
    "density": 0.10,
}


@dataclass
class ScoreBreakdown:
    """The final score plus the per-signal contributions, for transparency."""

    final: float
    components: dict[str, float]  # raw signal values
    contributions: dict[str, float]  # signal * weight


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


class ScoringService:
    """Applies the feedback-aware weighted ranking formula."""

    @staticmethod
    def density_score(char_count: int, target: int = 4000) -> float:
        """
        Map raw content length to a 0-1 'richness' signal. Saturates at
        `target` chars so a 50k-char page does not dominate purely on size.
        """
        if char_count <= 0:
            return 0.0
        return _clamp(char_count / target)

    @staticmethod
    def feedback_score(positive: int, negative: int) -> float:
        """
        Wilson-style usefulness from positive/negative counts. Neutral (0.5)
        with no feedback; converges toward the observed ratio as evidence grows.
        """
        total = positive + negative
        if total == 0:
            return 0.5
        # Smoothed ratio: add a neutral prior of one positive + one negative.
        return _clamp((positive + 1) / (total + 2))

    def score(
        self,
        *,
        semantic: float = 0.5,
        keyword: float = 0.5,
        source_trust: float = 0.5,
        freshness: float = 0.5,
        feedback: float = 0.5,
        density: float = 0.5,
    ) -> ScoreBreakdown:
        """Combine the six signals into one final score with a full breakdown."""
        components = {
            "semantic": _clamp(semantic),
            "keyword": _clamp(keyword),
            "source_trust": _clamp(source_trust),
            "freshness": _clamp(freshness),
            "feedback": _clamp(feedback),
            "density": _clamp(density),
        }
        contributions = {k: round(v * WEIGHTS[k], 4) for k, v in components.items()}
        final = round(_clamp(sum(contributions.values())), 4)
        return ScoreBreakdown(final=final, components=components, contributions=contributions)
