"""
PURPOSE: Query DuckDuckGo and return a filtered list of candidate URLs.
Uses duckduckgo-search (DDGS) library — no API key required.
Fetches 3x requested results to allow for filtering invalid URLs.
"""

import logging
from duckduckgo_search import DDGS
from app.models.response import SearchCandidate

logger = logging.getLogger(__name__)

# Domains that typically don't contain useful readable text for RAG
BLOCKED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "reddit.com/r/",
    "pinterest.com",
    "linkedin.com/in/",
]


class SearchService:
    """
    Wraps DuckDuckGo text search and returns filtered SearchCandidate objects.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def search(self, query: str) -> list[SearchCandidate]:
        """
        Search DuckDuckGo for the query and return up to max_results valid candidates.

        Args:
            query: The search query string.

        Returns:
            List of SearchCandidate objects with title, url, snippet.
            Returns empty list if search fails — caller should handle this gracefully.
        """
        candidates: list[SearchCandidate] = []

        try:
            # Fetch 3x requested results so we have enough after filtering
            fetch_count = self.max_results * 3

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=fetch_count))

            for result in raw_results:
                url = result.get("href", "")
                if not self._is_valid_url(url):
                    continue

                candidates.append(
                    SearchCandidate(
                        title=result.get("title", "Untitled"),
                        url=url,
                        snippet=result.get("body", ""),
                    )
                )

                if len(candidates) >= self.max_results:
                    break

            logger.info(f"SearchService: found {len(candidates)} candidates for '{query}'")
            return candidates

        except Exception as e:
            logger.error(f"SearchService: DuckDuckGo search failed: {e}")
            return []

    def _is_valid_url(self, url: str) -> bool:
        """
        Returns True if the URL is a valid, fetchable web page.
        Rejects non-HTTP URLs and blocked domains.
        """
        if not url:
            return False
        if not url.startswith(("http://", "https://")):
            return False
        return not any(blocked in url for blocked in BLOCKED_DOMAINS)
