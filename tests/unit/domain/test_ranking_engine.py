"""
Unit tests for RankService — relevance ranking of processed results.

(File kept under its original path; it now covers the live RankService that
replaced the archived RankingEngine.)
"""
from app.models.response import ProcessedResult
from app.services.rank_service import RankService


def _result(title: str, url: str, content: str) -> ProcessedResult:
    return ProcessedResult(title=title, url=url, content=content, chunks=[])


def test_rank_orders_relevant_result_first():
    results = [
        _result("Unrelated cooking blog", "https://b.com",
                "recipes for soup and bread baking " * 20),
        _result("pgvector similarity guide", "https://a.com",
                "pgvector vector similarity search in postgres " * 20),
    ]
    ranked = RankService().rank("pgvector vector similarity search", results)
    assert ranked[0].url == "https://a.com"


def test_rank_scores_within_unit_interval():
    results = [_result("t", "https://x.com", "some content about vectors " * 10)]
    ranked = RankService().rank("vectors", results)
    assert all(0.0 <= r.score <= 1.0 for r in ranked)


def test_rank_empty_input_returns_empty():
    assert RankService().rank("anything", []) == []


def test_rank_title_match_boosts_score():
    on_topic = _result("docker containers explained", "https://a.com",
                        "general text " * 30)
    off_topic = _result("gardening tips", "https://b.com", "general text " * 30)
    ranked = RankService().rank("docker containers", [off_topic, on_topic])
    assert ranked[0].url == "https://a.com"
