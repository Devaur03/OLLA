"""Unit tests for the Phase 5 query classifier."""

from app.services.query_classifier_service import (
    QueryClass,
    QueryClassifier,
    WEB_REQUIRED_CLASSES,
)

clf = QueryClassifier()


def test_news_query_requires_web():
    c = clf.classify("breaking news on the AI summit today")
    assert c.query_class == QueryClass.NEWS
    assert c.web_required is True


def test_recent_query_requires_web():
    c = clf.classify("latest large language models")
    assert c.query_class == QueryClass.RECENT
    assert c.web_required is True


def test_year_mention_is_recent():
    c = clf.classify("best vector databases 2026")
    assert c.query_class == QueryClass.RECENT
    assert c.web_required is True


def test_definition_query_is_evergreen_path():
    c = clf.classify("what is a vector database")
    assert c.query_class == QueryClass.DEFINITION
    assert c.web_required is False


def test_comparison_query():
    c = clf.classify("pgvector vs pinecone")
    assert c.query_class == QueryClass.COMPARISON
    assert c.web_required is False


def test_technical_query():
    c = clf.classify("how to install pgvector on postgres")
    assert c.query_class == QueryClass.TECHNICAL
    assert c.web_required is False


def test_research_query():
    c = clf.classify("comprehensive analysis of retrieval augmented generation")
    assert c.query_class == QueryClass.RESEARCH
    assert c.web_required is False


def test_plain_query_is_evergreen():
    c = clf.classify("binary search tree properties")
    assert c.query_class == QueryClass.EVERGREEN
    assert c.web_required is False


def test_web_required_classes_membership():
    assert QueryClass.NEWS in WEB_REQUIRED_CLASSES
    assert QueryClass.RECENT in WEB_REQUIRED_CLASSES
    assert QueryClass.DEFINITION not in WEB_REQUIRED_CLASSES


def test_classification_always_has_signals():
    for q in ["what is x", "latest news", "python tutorial", "random topic"]:
        assert clf.classify(q).signals, f"no signals for {q!r}"
