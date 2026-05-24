"""
Retrieval quality metrics (Phase 11).

Two families:

LABEL-BASED — need ground-truth relevance (a query's `relevant_domains`):
    precision_at_k, ndcg_at_k, mrr

LABEL-FREE — work on any result set, no gold labels needed:
    citation_support_rate, mean, percentile

All functions are pure and deterministic so they can be unit tested without a
running backend.
"""

import math
import re


# --------------------------------------------------------------- helpers

def _domain(url: str) -> str:
    """Lower-cased registrable-ish domain, www. stripped."""
    m = re.search(r"https?://([^/]+)", url or "")
    host = (m.group(1) if m else (url or "")).lower()
    return host[4:] if host.startswith("www.") else host


def _is_relevant(url: str, relevant_domains: list[str]) -> bool:
    """A result is relevant if its domain matches (or is a subdomain of) a label."""
    d = _domain(url)
    return any(d == rd or d.endswith("." + rd) for rd in relevant_domains)


# ----------------------------------------------------------- label-based

def precision_at_k(result_urls: list[str], relevant_domains: list[str], k: int = 5) -> float:
    """Fraction of the top-k results whose domain is in the relevance set."""
    if not relevant_domains or k <= 0:
        return 0.0
    topk = result_urls[:k]
    if not topk:
        return 0.0
    hits = sum(1 for u in topk if _is_relevant(u, relevant_domains))
    return round(hits / len(topk), 4)


def ndcg_at_k(result_urls: list[str], relevant_domains: list[str], k: int = 5) -> float:
    """
    Normalised Discounted Cumulative Gain over the top-k results.

    Binary relevance (1 if the domain is in the label set, else 0). DCG
    rewards relevant results that appear higher; nDCG divides by the ideal
    ordering so the score is in [0,1].
    """
    if not relevant_domains or k <= 0:
        return 0.0
    gains = [1.0 if _is_relevant(u, relevant_domains) else 0.0
             for u in result_urls[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(gains, reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return round(dcg / idcg, 4) if idcg > 0 else 0.0


def mrr(result_urls: list[str], relevant_domains: list[str]) -> float:
    """Reciprocal rank of the first relevant result (0.0 if none)."""
    if not relevant_domains:
        return 0.0
    for i, u in enumerate(result_urls, start=1):
        if _is_relevant(u, relevant_domains):
            return round(1.0 / i, 4)
    return 0.0


# ------------------------------------------------------------ label-free

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2}


def citation_support_rate(answer: str, results: list[dict]) -> float:
    """
    Heuristic: of the inline [n] citations in the answer, what fraction point
    at a result whose content actually shares vocabulary with the answer?

    Not a proof of factual support, but a cheap signal that cited sources are
    on-topic rather than spurious. Returns 0.0 when the answer has no [n]
    markers.
    """
    if not answer:
        return 0.0
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    if not cited:
        return 0.0
    answer_tokens = _tokens(answer)
    if not answer_tokens:
        return 0.0

    supported = 0
    for n in cited:
        idx = n - 1  # [1] -> results[0]
        if 0 <= idx < len(results):
            content = results[idx].get("content") or ""
            overlap = answer_tokens & _tokens(content)
            # "supported" if the cited source shares a non-trivial vocabulary.
            if len(overlap) >= 3:
                supported += 1
    return round(supported / len(cited), 4)


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile (p in [0,100])."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 4)
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    frac = rank - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 4)
