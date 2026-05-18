"""
PURPOSE: Query DuckDuckGo (with retry + backoff) and fall back to Brave Search
if DDG is throttled. Returns a filtered list of candidate URLs.

Provider priority:
  1. DuckDuckGo (free, no key) -- up to 3 attempts with exponential backoff
  2. Brave Search (optional, set BRAVE_API_KEY in .env) -- used when DDG fails
"""

import asyncio
import logging
import httpx
from duckduckgo_search import DDGS

from app.config import settings
from app.models.response import SearchCandidate

logger = logging.getLogger(__name__)

BLOCKED_DOMAINS = [
    "youtube.com", "youtu.be", "twitter.com", "x.com",
    "instagram.com", "facebook.com", "tiktok.com",
    "reddit.com/r/", "pinterest.com", "linkedin.com/in/",
]

_DDG_MAX_ATTEMPTS = 3
_DDG_BASE_DELAY = 1.5
_DDG_MAX_DELAY = 10.0


class SearchService:
    """
    Wraps web search with automatic retry-backoff and provider fallback.
    DuckDuckGo is tried first; Brave Search is used as fallback when BRAVE_API_KEY is set.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    async def search(self, query: str) -> list[SearchCandidate]:
        candidates = await self._search_ddg_with_retry(query)
        if candidates:
            return candidates

        if settings.brave_api_key:
            logger.warning(
                "SearchService: DDG exhausted all retries -- falling back to Brave Search. "
                "If this happens frequently, DDG may be throttling your IP."
            )
            candidates = await self._search_brave(query)
            if candidates:
                return candidates
            logger.error(
                "SearchService: Brave Search also failed. "
                "Check your BRAVE_API_KEY and network connectivity."
            )
        else:
            logger.error(
                "SearchService: DuckDuckGo failed and no fallback is configured. "
                "Set BRAVE_API_KEY in .env for automatic fallback "
                "(free tier: https://brave.com/search/api/)."
            )

        return []

    async def _search_ddg_with_retry(self, query: str) -> list[SearchCandidate]:
        fetch_count = self.max_results * 3
        delay = _DDG_BASE_DELAY

        for attempt in range(1, _DDG_MAX_ATTEMPTS + 1):
            try:
                loop = asyncio.get_event_loop()
                raw_results = await loop.run_in_executor(
                    None,
                    lambda: self._ddg_search_sync(query, fetch_count),
                )
                candidates = self._filter_candidates(raw_results)
                logger.info(
                    "SearchService [DDG attempt %s]: found %s candidates for '%s'",
                    attempt, len(candidates), query,
                )
                return candidates

            except Exception as e:
                err_str = str(e).lower()
                is_ratelimit = "ratelimit" in err_str or "202" in err_str or "rate limit" in err_str

                if is_ratelimit:
                    if attempt < _DDG_MAX_ATTEMPTS:
                        actual_delay = min(delay, _DDG_MAX_DELAY)
                        logger.warning(
                            "SearchService: DDG rate limit hit (attempt %s/%s). "
                            "Retrying in %.1fs... "
                            "Tip: set BRAVE_API_KEY in .env for automatic fallback.",
                            attempt, _DDG_MAX_ATTEMPTS, actual_delay,
                        )
                        await asyncio.sleep(actual_delay)
                        delay *= 2
                    else:
                        logger.error(
                            "SearchService: DDG rate limit hit on all %s attempts. "
                            "Set BRAVE_API_KEY in .env to enable fallback to Brave Search.",
                            _DDG_MAX_ATTEMPTS,
                        )
                else:
                    logger.warning(
                        "SearchService: DDG error on attempt %s/%s: %s. %s",
                        attempt, _DDG_MAX_ATTEMPTS, e,
                        "Retrying..." if attempt < _DDG_MAX_ATTEMPTS else "Giving up.",
                    )
                    if attempt < _DDG_MAX_ATTEMPTS:
                        await asyncio.sleep(min(delay, _DDG_MAX_DELAY))
                        delay *= 2

        return []

    def _ddg_search_sync(self, query: str, fetch_count: int) -> list[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=fetch_count))

    async def _search_brave(self, query: str) -> list[SearchCandidate]:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.brave_api_key,
        }
        params = {
            "q": query,
            "count": self.max_results * 2,
            "search_lang": "en",
            "result_filter": "web",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            web_results = data.get("web", {}).get("results", [])
            candidates = []
            for item in web_results:
                url_val = item.get("url", "")
                if not self._is_valid_url(url_val):
                    continue
                candidates.append(
                    SearchCandidate(
                        title=item.get("title", "Untitled"),
                        url=url_val,
                        snippet=item.get("description", ""),
                    )
                )
                if len(candidates) >= self.max_results:
                    break

            logger.info(
                "SearchService [Brave fallback]: found %s candidates for '%s'",
                len(candidates), query,
            )
            return candidates

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error(
                    "SearchService: Brave Search 401 Unauthorized. "
                    "Check that BRAVE_API_KEY in .env is correct and active."
                )
            elif e.response.status_code == 429:
                logger.error(
                    "SearchService: Brave Search rate limit exceeded. "
                    "You may have hit your monthly free-tier quota (2,000 queries)."
                )
            else:
                logger.error("SearchService: Brave Search HTTP error: %s", e)
            return []

        except Exception as e:
            logger.error("SearchService: Brave Search failed: %s", e, exc_info=True)
            return []

    def _filter_candidates(self, raw_results: list[dict]) -> list[SearchCandidate]:
        candidates: list[SearchCandidate] = []
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
        return candidates

    def _is_valid_url(self, url: str) -> bool:
        if not url:
            return False
        if not url.startswith(("http://", "https://")):
            return False
        return not any(blocked in url for blocked in BLOCKED_DOMAINS)
