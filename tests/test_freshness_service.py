"""Unit tests for the Phase 5 freshness scoring service."""

from datetime import datetime, timedelta, timezone

from app.services.freshness_service import FreshnessService
from app.services.query_classifier_service import QueryClass

svc = FreshnessService()
NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_just_refreshed_is_fully_fresh():
    assert svc.score(NOW, QueryClass.EVERGREEN, now=NOW) == 1.0


def test_missing_timestamp_is_worst_case():
    assert svc.score(None, QueryClass.EVERGREEN, now=NOW) == 0.0


def test_news_decays_fast():
    six_hours_ago = NOW - timedelta(hours=6)
    # 6h == news half-life → freshness ~0.5
    assert abs(svc.score(six_hours_ago, QueryClass.NEWS, now=NOW) - 0.5) < 0.05


def test_evergreen_barely_decays_over_a_week():
    week_ago = NOW - timedelta(days=7)
    assert svc.score(week_ago, QueryClass.EVERGREEN, now=NOW) > 0.95


def test_news_more_stale_than_evergreen_for_same_age():
    day_ago = NOW - timedelta(days=1)
    news = svc.score(day_ago, QueryClass.NEWS, now=NOW)
    evergreen = svc.score(day_ago, QueryClass.EVERGREEN, now=NOW)
    assert news < evergreen


def test_score_is_bounded():
    for age_days in (0, 1, 30, 365, 3650):
        ts = NOW - timedelta(days=age_days)
        for qc in QueryClass:
            s = svc.score(ts, qc, now=NOW)
            assert 0.0 <= s <= 1.0


def test_is_stale_for_old_news():
    old = NOW - timedelta(days=2)
    assert svc.is_stale(old, QueryClass.NEWS, now=NOW) is True


def test_is_not_stale_for_fresh_evergreen():
    recent = NOW - timedelta(days=2)
    assert svc.is_stale(recent, QueryClass.EVERGREEN, now=NOW) is False


def test_naive_datetime_is_tolerated():
    naive = datetime(2026, 5, 22, 6, 0, 0)  # no tzinfo
    s = svc.score(naive, QueryClass.NEWS, now=NOW)
    assert 0.0 <= s <= 1.0
