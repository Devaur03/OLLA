"""Brave Search implementation of SearchProvider."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.domain.interfaces.search_provider import SearchProvider, SearchCandidate
from app.core.errors.exceptions import SearchProviderError, RateLimitError

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

BLOCKED_DOMAINS = [
    "youtube.com", "youtu.be", "twitter.com", "x.com",
    "instagram.com", "facebook.com", "tiktok.com",
    "pinterest.com", "linkedin.com/in/",
]


class BraveSearch(SearchProvider):
    """
    Brave Search REST API implementation.

    Used as fallback when DuckDuckGo is rate-limited.

    Args:
        api_key: Brave Search API key (free tier: 2,000 queries/month).
        max_results: Maximum candidates per search call.
    """

    def __init__(self, api_key: str = "", max_results: int = 5) -> None:
        self._api_key = api_key
        self._max_results = max_results

    async def search(self, query: str, max_results: int = 0) -> list[SearchCandidate]:
        limit = max_results or self._max_results
        if not self._api_key:
            logger.warning("BraveSearch: no API key configured, skipping")
            return []

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        params = {
            "q": query,
            "count": limit * 2,
            "search_lang": "en",
            "result_filter": "web",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_BRAVE_URL, headers=headers, params=params)
                if resp.status_code == 401:
                    raise SearchProviderError(
                        "Brave Search 401 Unauthorized. "
                        "Check that BRAVE_API_KEY in .env is correct and active."
                    )
                if resp.status_code == 429:
                    raise RateLimitError(
                        provider="Brave Search",
                        retry_after=int(resp.headers.get("Retry-After", 0)),
                    )
                resp.raise_for_status()
                data = resp.json()

            candidates: list[SearchCandidate] = []
            for item in data.get("web", {}).get("results", []):
                url = item.get("url", "")
                if not self._is_valid(url):
                    continue
                candidates.append(SearchCandidate(
                    title=item.get("title", "Untitled"),
                    url=url,
                    snippet=item.get("description", ""),
                ))
                if len(candidates) >= limit:
                    break

            logger.info("BraveSearch: %d candidates for %r", len(candidates), query)
            return candidates

        except (SearchProviderError, RateLimitError):
            raise
        except httpx.HTTPStatusError as exc:
            logger.error("Brave HTTP error: %s", exc)
            return []
        except Exception as exc:
            logger.error("Brave failed: %s", exc, exc_info=True)
            return []

    async def health_check(self) -> bool:
        results = await self.search("test", max_results=1)
        return len(results) > 0

    def _is_valid(self, url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        return not any(b in url for b in BLOCKED_DOMAINS)
