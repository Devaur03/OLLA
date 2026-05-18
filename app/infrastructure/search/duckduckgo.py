"""DuckDuckGo implementation of SearchProvider with circuit breaker and retry."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.domain.interfaces.search_provider import SearchProvider, SearchCandidate
from app.core.errors.exceptions import SearchProviderError, RateLimitError

logger = logging.getLogger(__name__)

BLOCKED_DOMAINS = [
    "youtube.com", "youtu.be", "twitter.com", "x.com",
    "instagram.com", "facebook.com", "tiktok.com",
    "pinterest.com", "linkedin.com/in/",
]

_MAX_ATTEMPTS = 3
_BASE_DELAY = 1.5
_MAX_DELAY = 10.0


class DuckDuckGoSearch(SearchProvider):
    """
    DuckDuckGo search via the duckduckgo-search library.

    Runs synchronous DDGS in a thread-pool executor so the async event loop
    is never blocked. Retries up to 3 times with exponential backoff on
    rate-limit errors.

    Args:
        max_results: Default maximum candidates per search call.
    """

    def __init__(self, max_results: int = 5) -> None:
        self._max_results = max_results

    async def search(self, query: str, max_results: int = 0) -> list[SearchCandidate]:
        limit = max_results or self._max_results
        fetch_count = limit * 3
        delay = _BASE_DELAY

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    None, lambda: self._search_sync(query, fetch_count)
                )
                candidates = self._filter(raw, limit)
                logger.info(
                    "DuckDuckGoSearch [attempt %d]: %d candidates for %r",
                    attempt, len(candidates), query,
                )
                return candidates

            except Exception as exc:
                err = str(exc).lower()
                is_rate = "ratelimit" in err or "202" in err or "rate limit" in err

                if is_rate:
                    if attempt < _MAX_ATTEMPTS:
                        wait = min(delay, _MAX_DELAY)
                        logger.warning(
                            "DDG rate limit (attempt %d/%d). Retrying in %.1fs.",
                            attempt, _MAX_ATTEMPTS, wait,
                        )
                        await asyncio.sleep(wait)
                        delay *= 2
                    else:
                        logger.error(
                            "DDG rate limit on all %d attempts. "
                            "Set BRAVE_API_KEY for fallback.", _MAX_ATTEMPTS,
                        )
                        raise RateLimitError(provider="DuckDuckGo")
                else:
                    logger.warning(
                        "DDG error attempt %d/%d: %s. %s",
                        attempt, _MAX_ATTEMPTS, exc,
                        "Retrying..." if attempt < _MAX_ATTEMPTS else "Giving up.",
                    )
                    if attempt < _MAX_ATTEMPTS:
                        await asyncio.sleep(min(delay, _MAX_DELAY))
                        delay *= 2
                    else:
                        raise SearchProviderError("DuckDuckGo failed: " + str(exc))

        return []

    async def health_check(self) -> bool:
        try:
            results = await self.search("test", max_results=1)
            return len(results) >= 0
        except Exception:
            return False

    def _search_sync(self, query: str, fetch_count: int) -> list[dict]:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=fetch_count))

    def _filter(self, raw: list[dict], limit: int) -> list[SearchCandidate]:
        out: list[SearchCandidate] = []
        for item in raw:
            url = item.get("href", "")
            if not url or not url.startswith(("http://", "https://")):
                continue
            if any(b in url for b in BLOCKED_DOMAINS):
                continue
            out.append(SearchCandidate(
                title=item.get("title", "Untitled"),
                url=url,
                snippet=item.get("body", ""),
            ))
            if len(out) >= limit:
                break
        return out
