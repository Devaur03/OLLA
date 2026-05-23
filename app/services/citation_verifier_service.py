"""
PURPOSE: Citation verification (Phase 10).

A synthesized answer carries inline [n] markers pointing at numbered sources.
Nothing so far checks that source [2] actually has anything to do with the
sentence citing it — a hallucinated or mis-numbered citation looks identical to
a good one.

`CitationVerifierService.verify()` does a cheap, transparent check: for each
[n] marker, does the cited result's content share meaningful vocabulary with
the answer? It is a *support signal*, not a factual-entailment proof — but it
reliably catches citations that point at unrelated sources.

Pure and deterministic — no model, no network, fully unit-testable.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")
# A cited source must share at least this many content words with the answer.
_MIN_OVERLAP = 3

# Very common words carry no topical signal — ignore them in the overlap.
_STOP = {
    "the", "and", "for", "are", "was", "were", "this", "that", "with", "from",
    "have", "has", "had", "not", "but", "you", "your", "can", "will", "any",
    "all", "its", "their", "they", "them", "how", "what", "when", "which",
}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower())
            if len(w) > 2 and w not in _STOP}


@dataclass
class CitationCheck:
    """Verification result for a single [n] citation."""
    marker: int
    supported: bool
    overlap: int
    reason: str


@dataclass
class VerificationResult:
    """Aggregate citation-verification outcome for one answer."""
    support_rate: float                       # supported / cited, in [0,1]
    total_citations: int
    supported_citations: int
    unsupported_markers: list[int] = field(default_factory=list)
    checks: list[CitationCheck] = field(default_factory=list)


class CitationVerifierService:
    """Checks whether an answer's [n] citations point at on-topic sources."""

    def verify(self, answer: str, results: list) -> VerificationResult:
        """
        Verify every [n] marker in `answer` against `results`.

        `results` is the ordered source list — marker [1] maps to results[0].
        Each result is a dict or object exposing `content` (then `text`).
        """
        if not answer:
            return VerificationResult(0.0, 0, 0)

        markers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
        if not markers:
            return VerificationResult(0.0, 0, 0)

        answer_tokens = _tokens(answer)
        checks: list[CitationCheck] = []
        for n in markers:
            idx = n - 1
            if not (0 <= idx < len(results)):
                checks.append(CitationCheck(n, False, 0, "marker has no matching source"))
                continue
            content = _content_of(results[idx])
            overlap = len(answer_tokens & _tokens(content))
            supported = overlap >= _MIN_OVERLAP
            checks.append(CitationCheck(
                n, supported, overlap,
                "shares topical vocabulary" if supported
                else "little/no vocabulary overlap with the answer",
            ))

        supported = [c for c in checks if c.supported]
        return VerificationResult(
            support_rate=round(len(supported) / len(checks), 4),
            total_citations=len(checks),
            supported_citations=len(supported),
            unsupported_markers=[c.marker for c in checks if not c.supported],
            checks=checks,
        )


def _content_of(item) -> str:
    if isinstance(item, dict):
        return item.get("content") or item.get("text") or ""
    return getattr(item, "content", None) or getattr(item, "text", "") or ""
