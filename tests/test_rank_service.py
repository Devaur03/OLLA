import pytest
from app.services.rank_service import RankService
from app.models.response import ProcessedResult, ContentChunk


def make_result(title: str, content: str) -> ProcessedResult:
    return ProcessedResult(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        content=content,
        chunks=[ContentChunk(chunk_id=0, text=content[:100], char_count=100)],
        score=0.0,
    )


@pytest.fixture
def svc():
    return RankService()


def test_scores_are_between_0_and_1(svc):
    results = [
        make_result("Python Async", "Python supports async and await for concurrency."),
        make_result("Java Spring", "Java Spring Boot is a framework for building APIs."),
    ]
    ranked = svc.rank("python async programming", results)
    for r in ranked:
        assert 0.0 <= r.score <= 1.0


def test_relevant_result_scores_higher(svc):
    relevant = make_result(
        "Vector Search RAG",
        "Vector search is used in RAG systems to find semantically similar chunks.",
    )
    irrelevant = make_result(
        "Cooking Recipes",
        "This article covers recipes for pasta, pizza, and other Italian food.",
    )
    ranked = svc.rank("vector search RAG", [irrelevant, relevant])
    assert ranked[0].title == "Vector Search RAG"


def test_empty_results_returns_empty(svc):
    assert svc.rank("test query", []) == []


def test_results_are_sorted_descending(svc):
    results = [
        make_result(f"Result {i}", f"Content about topic number {i} " * 10) for i in range(5)
    ]
    ranked = svc.rank("topic content", results)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
