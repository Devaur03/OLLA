"""Unit tests for the Phase 11 evaluation metrics."""

from eval import metrics

REL = ["github.com", "postgresql.org"]


def test_precision_all_relevant():
    urls = ["https://github.com/a", "https://www.postgresql.org/docs"]
    assert metrics.precision_at_k(urls, REL, k=5) == 1.0


def test_precision_none_relevant():
    urls = ["https://medium.com/x", "https://reddit.com/y"]
    assert metrics.precision_at_k(urls, REL, k=5) == 0.0


def test_precision_half():
    urls = ["https://github.com/a", "https://medium.com/x"]
    assert metrics.precision_at_k(urls, REL, k=2) == 0.5


def test_precision_no_labels_is_zero():
    assert metrics.precision_at_k(["https://github.com/a"], [], k=5) == 0.0


def test_subdomain_counts_as_relevant():
    urls = ["https://gist.github.com/a"]
    assert metrics.precision_at_k(urls, REL, k=1) == 1.0


def test_ndcg_perfect_ordering_is_one():
    urls = ["https://github.com/a", "https://postgresql.org/b"]
    assert metrics.ndcg_at_k(urls, REL, k=5) == 1.0


def test_ndcg_rewards_higher_relevant_rank():
    top = metrics.ndcg_at_k(["https://github.com/a", "https://medium.com/x"], REL, 5)
    bottom = metrics.ndcg_at_k(["https://medium.com/x", "https://github.com/a"], REL, 5)
    assert top > bottom


def test_ndcg_no_relevant_is_zero():
    assert metrics.ndcg_at_k(["https://medium.com/x"], REL, k=5) == 0.0


def test_mrr_first_position():
    assert metrics.mrr(["https://github.com/a", "https://medium.com/x"], REL) == 1.0


def test_mrr_third_position():
    urls = ["https://medium.com/x", "https://reddit.com/y", "https://github.com/a"]
    assert metrics.mrr(urls, REL) == round(1 / 3, 4)


def test_mrr_no_match():
    assert metrics.mrr(["https://medium.com/x"], REL) == 0.0


def test_citation_support_no_citations():
    assert metrics.citation_support_rate("plain answer text", []) == 0.0


def test_citation_support_matches_content():
    answer = "pgvector stores embeddings as vectors [1]."
    results = [{"content": "pgvector stores embeddings as fixed-length vectors in postgres"}]
    assert metrics.citation_support_rate(answer, results) == 1.0


def test_citation_support_unsupported():
    answer = "quantum chromodynamics gluon confinement [1]."
    results = [{"content": "totally unrelated cooking recipe about pasta"}]
    assert metrics.citation_support_rate(answer, results) == 0.0


def test_mean_and_percentile():
    assert metrics.mean([]) == 0.0
    assert metrics.mean([2.0, 4.0]) == 3.0
    assert metrics.percentile([10, 20, 30, 40], 50) == 25.0
    assert metrics.percentile([5], 95) == 5.0
