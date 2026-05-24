"""
PURPOSE: Query rewriting + multi-query expansion (Phase 10).

A single user query is often a weak retrieval probe — too short, full of
filler, or phrased one specific way when the answer is indexed under another.

This service does two related jobs, both with cheap deterministic heuristics:

  rewrite(query)        — clean a weak query into a better search string
                          (drop filler, collapse whitespace, strip trailing
                          punctuation).
  expand(query, n)      — produce N complementary query variants so the crawl
                          casts a wider net (a docs-flavoured variant, a
                          tutorial-flavoured variant, a bare-keyword variant).

No LLM call — fast, offline, unit-testable. An LLM rewriter could replace this
later behind the same interface.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Conversational filler that adds no retrieval signal.
_FILLER = [
    "can you tell me", "could you tell me", "i want to know", "i would like to know",
    "please tell me", "tell me about", "i need to know", "help me understand",
    "can you explain", "could you explain", "please explain", "explain to me",
    "i am looking for", "i'm looking for", "what i want is", "please", "kindly",
]
_FILLER_RE = re.compile("|".join(re.escape(f) for f in _FILLER), re.IGNORECASE)

# Question-lead words to drop when forming a bare-keyword variant. After the
# lead word, any run of auxiliary/determiner words ("is a", "does the") is also
# dropped so "what is a vector database" → "vector database".
_LEAD_RE = re.compile(
    r"^\s*(?:what|who|where|when|why|how|is|are|does|do|can|should)\s+"
    r"(?:(?:is|are|do|does|the|a|an)\s+)*",
    re.IGNORECASE,
)


class QueryExpansionService:
    """Rewrites weak queries and expands one query into several variants."""

    def rewrite(self, query: str) -> str:
        """Return a cleaned, retrieval-friendlier version of `query`."""
        q = _FILLER_RE.sub(" ", query or "")
        q = re.sub(r"\s+", " ", q).strip()
        q = q.rstrip("?.!,;: ").strip()
        # If filler removal emptied it, fall back to the original.
        return q or (query or "").strip()

    def keyword_form(self, query: str) -> str:
        """Strip leading question words → a bare keyword probe."""
        q = self.rewrite(query)
        stripped = _LEAD_RE.sub("", q).strip()
        return stripped or q

    def expand(self, query: str, n: int = 4) -> list[str]:
        """
        Return up to `n` distinct query variants, the cleaned original first.

        Variants: cleaned original, bare-keyword form, a documentation-flavoured
        form, and a tutorial/example-flavoured form. Deduplicated, order-stable.
        """
        base = self.rewrite(query)
        candidates = [
            base,
            self.keyword_form(query),
            f"{self.keyword_form(query)} documentation official",
            f"{self.keyword_form(query)} tutorial example",
        ]
        seen: set[str] = set()
        variants: list[str] = []
        for c in candidates:
            key = c.lower().strip()
            if key and key not in seen:
                seen.add(key)
                variants.append(c.strip())
            if len(variants) >= n:
                break
        return variants
