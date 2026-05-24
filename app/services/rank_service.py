"""
PURPOSE: Score each result by relevance to the original query and sort them.

Scoring formula (MVP — keyword-based, no embeddings):
  final_score = (tf_idf_score * 0.6) + (title_match_score * 0.3) + (density_bonus * 0.1)

- tf_idf_score: How often query terms appear in content relative to total words
- title_match_score: Fraction of query terms found in the page title
- density_bonus: Longer content gets a small bonus (up to 0.1) — more content = richer source

All scores are normalized to 0.0–1.0.
This is intentionally simple and replaceable with embedding cosine similarity in Phase 3.
"""

import math
import logging
from collections import Counter
from app.models.response import ProcessedResult

logger = logging.getLogger(__name__)

# Words to ignore when tokenizing (common English stop words)
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "not",
    "no",
    "nor",
    "so",
}


class RankService:
    """
    Scores ProcessedResult objects by relevance to a query and returns them sorted.
    """

    def rank(
        self,
        query: str,
        results: list[ProcessedResult],
    ) -> list[ProcessedResult]:
        """
        Score and sort results by relevance.

        Args:
            query: The original search query.
            results: List of ProcessedResult objects to rank.

        Returns:
            Same list, sorted descending by score (highest relevance first).
            Each result's .score field is set in place.
        """
        if not results:
            return []

        query_terms = self._tokenize(query)

        if not query_terms:
            # No meaningful terms — return as-is with score 0
            for result in results:
                result.score = 0.0
            return results

        for result in results:
            result.score = self._compute_score(query_terms, result)

        ranked = sorted(results, key=lambda r: r.score, reverse=True)

        logger.debug(
            f"RankService: ranked {len(ranked)} results for '{query}' — "
            f"top score: {ranked[0].score:.4f}"
        )
        return ranked

    def _compute_score(self, query_terms: list[str], result: ProcessedResult) -> float:
        """
        Compute a relevance score for a single result.
        Returns float in [0.0, 1.0].
        """
        content_score = self._tf_idf_score(query_terms, result.content)
        title_score = self._title_match_score(query_terms, result.title)
        density_bonus = self._density_bonus(result.content)

        final = (content_score * 0.6) + (title_score * 0.3) + (density_bonus * 0.1)
        return round(min(final, 1.0), 4)

    def _tf_idf_score(self, query_terms: list[str], content: str) -> float:
        """
        Compute a TF-IDF-inspired score for query terms in content.
        Uses a simplified IDF (no corpus — self-referential dampening).
        """
        if not content:
            return 0.0

        content_tokens = self._tokenize(content)
        if not content_tokens:
            return 0.0

        token_counts = Counter(content_tokens)
        total_tokens = len(content_tokens)

        term_scores = []
        for term in query_terms:
            count = token_counts.get(term, 0)
            # TF: frequency in this document
            tf = count / total_tokens
            # IDF proxy: rare terms score higher; log dampens very frequent terms
            idf = math.log(1 + (total_tokens / (1 + count)))
            term_scores.append(tf * idf)

        raw_score = sum(term_scores) / len(query_terms)

        # Normalize to 0–1 with a reasonable cap
        # Typical raw TF-IDF scores are in range 0.0001–0.05
        return min(raw_score * 50, 1.0)

    def _title_match_score(self, query_terms: list[str], title: str) -> float:
        """
        Score how many query terms appear in the page title.
        Title matches are strong signals — given 30% weight.
        """
        if not title or not query_terms:
            return 0.0

        title_tokens = set(self._tokenize(title))
        matches = sum(1 for term in query_terms if term in title_tokens)
        return matches / len(query_terms)

    def _density_bonus(self, content: str) -> float:
        """
        Small bonus for content-rich pages.
        Pages with 5000+ characters get full bonus (0.1).
        """
        return min(len(content) / 5000, 1.0)

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text into lowercase words, removing stop words and short tokens.
        """
        words = text.lower().split()
        return [w.strip(".,!?;:\"'()[]{}") for w in words if len(w) > 2 and w not in STOP_WORDS]
