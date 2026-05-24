"""
Unit tests for the search layer — request models, SearchService filtering,
and AnswerService context building.

(File kept under its original path; it now covers live components that
replaced the archived SearchOrchestrator.)
"""

import pytest

from app.models.request import GraphSearchRequest, SafeSearchLevel, SearchRequest, TimeLimit
from app.models.response import SearchResult
from app.services.answer_service import AnswerService
from app.services.search_service import SearchService


def test_search_request_defaults():
    req = SearchRequest(query="how does pgvector work")
    assert req.safesearch == SafeSearchLevel.MODERATE
    assert req.timelimit is None
    assert req.region == "wt-wt"


def test_search_request_region_alias_normalized():
    assert SearchRequest(query="latest ai news", region="US").region == "us-en"


def test_search_request_coerces_enums():
    req = SearchRequest(query="recent docker news", safesearch="off", timelimit="w")
    assert req.safesearch == SafeSearchLevel.OFF
    assert req.timelimit == TimeLimit.WEEK


def test_search_request_rejects_punctuation_only_query():
    with pytest.raises(Exception):
        SearchRequest(query="!!!@@@###")


def test_graph_search_request_defaults():
    req = GraphSearchRequest(query="knowledge graph", hops=3)
    assert req.hops == 3 and req.seed_k == 5


def test_search_service_filters_blocked_and_invalid_urls():
    svc = SearchService(max_results=5)
    raw = [
        {"title": "Good", "href": "https://docs.docker.com", "body": "docs"},
        {"title": "Blocked", "href": "https://youtube.com/watch?v=x", "body": "video"},
        {"title": "NoUrl", "body": "missing url"},
    ]
    candidates = svc._filter_candidates(raw)
    assert len(candidates) == 1
    assert candidates[0].url == "https://docs.docker.com"


def test_search_service_url_validation():
    svc = SearchService()
    assert svc._is_valid_url("https://example.com") is True
    assert svc._is_valid_url("ftp://example.com") is False
    assert svc._is_valid_url("") is False


def test_answer_service_context_builder_numbers_sources():
    results = [
        SearchResult(
            rank=1,
            title="IBM",
            url="https://ibm.com",
            content="IBM info " * 20,
            chunks=[],
            score=0.9,
            char_count=200,
            chunk_count=2,
        ),
        SearchResult(
            rank=2,
            title="Wiki",
            url="https://wikipedia.org",
            content="more " * 20,
            chunks=[],
            score=0.8,
            char_count=100,
            chunk_count=1,
        ),
    ]
    ctx = AnswerService()._build_context(results)
    assert "[1]" in ctx and "[2]" in ctx
    assert "ibm.com" in ctx
