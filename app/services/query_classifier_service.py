"""
PURPOSE: Query classification for the hybrid retrieval router (Phase 5).

Before the router can decide *where* to look for an answer (local semantic
memory vs. a live web crawl), it needs to know *what kind* of question it is
being asked. A definition ("what is a vector database") is evergreen — local
memory is almost always fine. A news query ("latest GPT release this week")
must always hit the web no matter how confident memory is.

This service is deliberately dependency-free heuristics: fast, deterministic,
unit-testable, and good enough to route. It is the cheap front door of the
router — an LLM classifier could replace it later without changing callers.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryClass(str, Enum):
    """The intent buckets the router cares about."""

    NEWS = "news"  # current events — web ALWAYS required
    RECENT = "recent"  # "latest", "2026", recency-sensitive — prefer web
    COMPARISON = "comparison"  # "x vs y" — memory ok if both sides stored
    TECHNICAL = "technical"  # docs/how-to — memory usually fine
    DEFINITION = "definition"  # "what is x" — evergreen, memory fine
    RESEARCH = "research"  # deep/multi-faceted — favour DEEP mode
    EVERGREEN = "evergreen"  # general stable knowledge — memory fine


# Query classes whose answers go stale quickly; the router forces a web
# refresh for these regardless of how confident local memory is.
WEB_REQUIRED_CLASSES: frozenset[QueryClass] = frozenset({QueryClass.NEWS, QueryClass.RECENT})


@dataclass
class Classification:
    """Result of classifying one query."""

    query_class: QueryClass
    web_required: bool  # answer is recency-sensitive → must crawl
    confidence: float  # 0-1, how sure the heuristic is
    signals: list[str]  # human-readable reasons (for traces/debugging)


# --- keyword signal banks --------------------------------------------------
_NEWS_TERMS = {
    "news",
    "breaking",
    "headline",
    "headlines",
    "announced",
    "announcement",
    "today",
    "yesterday",
    "this morning",
    "just now",
    "live",
}
_RECENT_TERMS = {
    "latest",
    "newest",
    "recent",
    "recently",
    "current",
    "currently",
    "this week",
    "this month",
    "this year",
    "now",
    "up to date",
    "updated",
    "new release",
    "just released",
    "upcoming",
}
_COMPARISON_TERMS = {
    " vs ",
    " versus ",
    " or ",
    "compare",
    "comparison",
    "difference between",
    "better than",
    "pros and cons",
}
_DEFINITION_PATTERNS = (
    r"^\s*what\s+(is|are|was|were)\b",
    r"^\s*who\s+(is|are|was|were)\b",
    r"^\s*define\b",
    r"^\s*meaning\s+of\b",
    r"\bexplain\b",
)
_TECHNICAL_TERMS = {
    "how to",
    "how do",
    "install",
    "configure",
    "setup",
    "set up",
    "error",
    "fix",
    "debug",
    "tutorial",
    "example",
    "documentation",
    "docs",
    "api",
    "implement",
    "code",
    "syntax",
    "command",
}
_RESEARCH_TERMS = {
    "research",
    "in depth",
    "in-depth",
    "comprehensive",
    "analysis",
    "survey",
    "literature",
    "study",
    "deep dive",
    "everything about",
    "overview of",
    "state of the art",
    "review of",
}
# Any 4-digit year >= the project's "current" era is a strong recency signal.
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


class QueryClassifier:
    """Classifies a query into a QueryClass via lightweight heuristics."""

    def classify(self, query: str) -> Classification:
        q = f" {query.lower().strip()} "
        signals: list[str] = []

        # --- NEWS: strongest, most time-sensitive bucket ------------------
        if any(t in q for t in _NEWS_TERMS):
            hit = next(t for t in _NEWS_TERMS if t in q)
            signals.append(f"news term: {hit.strip()!r}")
            return Classification(QueryClass.NEWS, True, 0.9, signals)

        # --- RECENT: recency words or an explicit recent year -------------
        year_match = _YEAR_RE.search(query)
        if year_match:
            signals.append(f"year mentioned: {year_match.group(1)}")
        recent_hit = next((t for t in _RECENT_TERMS if t in q), None)
        if recent_hit:
            signals.append(f"recency term: {recent_hit.strip()!r}")
        if recent_hit or year_match:
            conf = 0.85 if recent_hit and year_match else 0.75
            return Classification(QueryClass.RECENT, True, conf, signals)

        # --- RESEARCH: deep/broad intent ----------------------------------
        research_hit = next((t for t in _RESEARCH_TERMS if t in q), None)
        if research_hit:
            signals.append(f"research term: {research_hit.strip()!r}")
            return Classification(QueryClass.RESEARCH, False, 0.7, signals)

        # --- COMPARISON ---------------------------------------------------
        comp_hit = next((t for t in _COMPARISON_TERMS if t in q), None)
        if comp_hit:
            signals.append(f"comparison term: {comp_hit.strip()!r}")
            return Classification(QueryClass.COMPARISON, False, 0.7, signals)

        # --- DEFINITION ---------------------------------------------------
        for pat in _DEFINITION_PATTERNS:
            if re.search(pat, q):
                signals.append(f"definition pattern: {pat!r}")
                return Classification(QueryClass.DEFINITION, False, 0.8, signals)

        # --- TECHNICAL ----------------------------------------------------
        tech_hit = next((t for t in _TECHNICAL_TERMS if t in q), None)
        if tech_hit:
            signals.append(f"technical term: {tech_hit.strip()!r}")
            return Classification(QueryClass.TECHNICAL, False, 0.7, signals)

        # --- default: evergreen -------------------------------------------
        signals.append("no time-sensitive or intent signal — assumed evergreen")
        return Classification(QueryClass.EVERGREEN, False, 0.5, signals)
