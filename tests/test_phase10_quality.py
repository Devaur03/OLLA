"""Unit tests for the Phase 10 retrieval-quality services."""

from app.services.citation_verifier_service import CitationVerifierService
from app.services.diversity_service import DiversityService
from app.services.query_expansion_service import QueryExpansionService

# --------------------------------------------------------- query expansion

exp = QueryExpansionService()


def test_rewrite_strips_filler():
    out = exp.rewrite("can you tell me what is pgvector?")
    assert "can you tell me" not in out.lower()
    assert "pgvector" in out.lower()
    assert not out.endswith("?")


def test_rewrite_collapses_whitespace():
    assert exp.rewrite("  vector    search   ") == "vector search"


def test_rewrite_falls_back_when_emptied():
    # A query that is entirely filler must not become empty.
    assert exp.rewrite("please kindly").strip() != ""


def test_keyword_form_drops_question_words():
    assert exp.keyword_form("what is a vector database").lower().startswith("vector")


def test_expand_returns_distinct_variants():
    variants = exp.expand("what is RAG", n=4)
    assert variants[0] == exp.rewrite("what is RAG")
    assert len(variants) == len(set(v.lower() for v in variants))
    assert len(variants) <= 4


def test_expand_respects_n():
    assert len(exp.expand("vector search", n=2)) <= 2


# -------------------------------------------------------------- diversity

div = DiversityService()


def _u(domain, n):
    return [{"url": f"https://{domain}/{i}"} for i in range(n)]


def test_diversify_breaks_domain_monopoly():
    # 4 from one domain, 1 from another, cap 2.
    items = _u("a.com", 4) + _u("b.com", 1)
    out = div.diversify(items, max_per_domain=2)
    # b.com's single result should surface within the first 3, not last.
    first_three = [i["url"] for i in out[:3]]
    assert any("b.com" in u for u in first_three)


def test_diversify_keeps_all_items():
    items = _u("a.com", 4) + _u("b.com", 3)
    out = div.diversify(items, max_per_domain=2)
    assert len(out) == len(items)


def test_diversify_small_list_unchanged():
    items = _u("a.com", 2)
    assert div.diversify(items, max_per_domain=2) == items


def test_domain_spread_counts():
    items = _u("a.com", 3) + _u("b.com", 1)
    spread = div.domain_spread(items)
    assert spread["a.com"] == 3
    assert spread["b.com"] == 1


# ------------------------------------------------------ citation verifier

ver = CitationVerifierService()


def test_verify_no_citations():
    r = ver.verify("a plain answer with no markers", [])
    assert r.total_citations == 0
    assert r.support_rate == 0.0


def test_verify_supported_citation():
    answer = "pgvector stores embeddings as fixed-length vectors in postgres [1]."
    results = [{"content": "pgvector stores embeddings vectors postgres extension index"}]
    r = ver.verify(answer, results)
    assert r.total_citations == 1
    assert r.supported_citations == 1
    assert r.support_rate == 1.0
    assert r.unsupported_markers == []


def test_verify_unsupported_citation():
    answer = "quantum chromodynamics describes gluon confinement [1]."
    results = [{"content": "a recipe for chocolate cake with flour and sugar"}]
    r = ver.verify(answer, results)
    assert r.supported_citations == 0
    assert r.unsupported_markers == [1]


def test_verify_marker_out_of_range():
    r = ver.verify("claim with a bad marker [9].", [{"content": "anything"}])
    assert 9 in r.unsupported_markers


def test_verify_mixed():
    answer = "vector databases index embeddings [1]. unrelated tangent [2]."
    results = [
        {"content": "vector databases index embeddings for similarity search"},
        {"content": "completely different gardening topic about roses"},
    ]
    r = ver.verify(answer, results)
    assert r.total_citations == 2
    assert r.supported_citations == 1
    assert r.support_rate == 0.5
