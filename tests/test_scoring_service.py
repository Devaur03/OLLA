"""Unit tests for the Phase 7 feedback-aware scoring service."""

from app.services.scoring_service import WEIGHTS, ScoringService

svc = ScoringService()


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_all_ones_scores_one():
    b = svc.score(semantic=1, keyword=1, source_trust=1,
                  freshness=1, feedback=1, density=1)
    assert b.final == 1.0


def test_all_zeros_scores_zero():
    b = svc.score(semantic=0, keyword=0, source_trust=0,
                  freshness=0, feedback=0, density=0)
    assert b.final == 0.0


def test_semantic_dominates():
    """Semantic carries 0.40 weight — the largest single lever."""
    high_sem = svc.score(semantic=1, keyword=0, source_trust=0,
                         freshness=0, feedback=0, density=0).final
    high_density = svc.score(semantic=0, keyword=0, source_trust=0,
                             freshness=0, feedback=0, density=1).final
    assert high_sem > high_density
    assert high_sem == WEIGHTS["semantic"]


def test_inputs_are_clamped():
    b = svc.score(semantic=5.0, keyword=-2.0, source_trust=0.5,
                  freshness=0.5, feedback=0.5, density=0.5)
    assert 0.0 <= b.final <= 1.0
    assert b.components["semantic"] == 1.0
    assert b.components["keyword"] == 0.0


def test_feedback_score_neutral_with_no_data():
    assert svc.feedback_score(0, 0) == 0.5


def test_feedback_score_rises_with_positive():
    assert svc.feedback_score(10, 0) > svc.feedback_score(0, 0)


def test_feedback_score_falls_with_negative():
    assert svc.feedback_score(0, 10) < svc.feedback_score(0, 0)


def test_feedback_score_bounded():
    for p in (0, 1, 50):
        for n in (0, 1, 50):
            assert 0.0 <= svc.feedback_score(p, n) <= 1.0


def test_density_score_saturates():
    assert svc.density_score(0) == 0.0
    assert svc.density_score(100_000) == 1.0
    assert 0.0 < svc.density_score(2000) < 1.0


def test_breakdown_contributions_sum_to_final():
    b = svc.score(semantic=0.8, keyword=0.6, source_trust=0.7,
                  freshness=0.5, feedback=0.4, density=0.3)
    assert abs(sum(b.contributions.values()) - b.final) < 1e-6
