"""
Unit tests for RankingEngine.

Pure domain logic — no external dependencies.
"""
import pytest
from app.domain.services.ranking_engine import RankingEngine


def make_item(title, url, content, chunks=None):
    return (title, url, content, chunks or [])


@pytest.fixture
def engine():
    return RankingEngine()


class TestRank:
    def test_returns_empty_for_empty_input(self, engine):
        assert engine.rank("query", []) == []

    def test_scores_are_between_0_and_1(self, engine):
        items = [
            make_item("Python Async", "https://docs.python.org/async",
                      "Python supports async and await for concurrency."),
            make_item("Java Spring", "https://spring.io",
                      "Java Spring Boot is a framework for building APIs."),
        ]
        ranked = engine.rank("python async programming", items)
        for r in ranked:
            assert 0.0 <= r.score <= 1.0

    def test_relevant_result_ranks_first(self, engine):
        items = [
            make_item("Cooking Recipes", "https://food.com",
                      "This article covers recipes for pasta, pizza, and Italian food."),
            make_item("Vector Search RAG", "https://arxiv.org/vector-rag",
                      "Vector search is used in RAG systems to find semantically similar chunks."),
        ]
        ranked = engine.rank("vector search RAG", items)
        assert ranked[0].title == "Vector Search RAG"

    def test_results_sorted_descending_by_score(self, engine):
        items = [
            make_item(f"Result {i}", f"https://example.com/{i}",
                      f"Content about topic number {i} " * 10)
            for i in range(5)
        ]
        ranked = engine.rank("topic content", items)
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_field_reflects_final_sort_position(self, engine):
        items = [
            make_item("Doc A", "https://arxiv.org/a",
                      "Highly relevant content about vector databases and pgvector search."),
            make_item("Doc B", "https://medium.com/b",
                      "Mildly relevant blog post about pgvector setup."),
        ]
        ranked = engine.rank("pgvector vector databases", items)
        for i, r in enumerate(ranked, 1):
            assert r.rank == i

    def test_trusted_domain_gets_credibility_boost(self, engine):
        items = [
            make_item("Arxiv Paper", "https://arxiv.org/paper",
                      "Identical content for testing credibility scoring."),
            make_item("Medium Post", "https://medium.com/post",
                      "Identical content for testing credibility scoring."),
        ]
        ranked = engine.rank("credibility test", items)
        arxiv = next(r for r in ranked if "arxiv" in r.url)
        medium = next(r for r in ranked if "medium" in r.url)
        assert arxiv.score > medium.score


class TestInternals:
    def test_tfidf_zero_for_no_overlap(self, engine):
        score = engine._tfidf(["python", "async"], "java spring boot rest", ["java spring boot rest"])
        assert score == 0.0

    def test_tfidf_positive_for_overlap(self, engine):
        score = engine._tfidf(["python"], "python is great", ["python is great"])
        assert score > 0.0

    def test_credibility_known_domain(self, engine):
        assert engine._cred("https://arxiv.org/paper/123") == 0.95
        assert engine._cred("https://stackoverflow.com/q/123") == 0.82

    def test_credibility_unknown_domain(self, engine):
        from app.domain.services.ranking_engine import DEFAULT_CREDIBILITY
        assert engine._cred("https://unknown-blog.io/post") == DEFAULT_CREDIBILITY
