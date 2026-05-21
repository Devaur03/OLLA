"""
PURPOSE: Resilient web search.

Strategy (inspired by COMPARISON_README §4–5):
  1. DuckDuckGo with multi-backend fallback — try each backend in order
     ("auto" → "html" → "lite"). The "lite" endpoint in particular bypasses
     much of DuckDuckGo's bot detection.
  2. Each backend gets retry-with-backoff on rate-limit errors.
  3. Brave Search is used as a final provider fallback when DDG is exhausted
     (only if BRAVE_API_KEY is set).
  4. Optional proxy rotation when DDG rate-limits the server IP entirely.

Safe-search, time-limit and region are first-class parameters so callers can
control crawl coverage and recency.
"""

import asyncio
import logging
import random

import httpx
from duckduckgo_search import DDGS

from app.config import settings
from app.models.request import SafeSearchLevel, TimeLimit
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


def _proxy_pool() -> list[str]:
    """Parse the comma-separated PROXY_POOL setting into a list."""
    return [p.strip() for p in settings.proxy_pool.split(",") if p.strip()]


def _random_proxy() -> str | None:
    pool = _proxy_pool()
    return random.choice(pool) if pool else None


class SearchService:
    """
    Resilient web search with multi-backend DuckDuckGo + Brave fallback.

    Args:
        max_results: default maximum candidates returned per search.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results
        self.backends = [
            b.strip() for b in settings.ddg_backends.split(",") if b.strip()
        ] or ["auto"]

    async def search(
        self,
        query: str,
        safesearch: SafeSearchLevel | str = SafeSearchLevel.MODERATE,
        timelimit: TimeLimit | str | None = None,
        region: str = "wt-wt",
    ) -> list[SearchCandidate]:
        """
        Run a resilient search. Returns a filtered list of candidate URLs.

        Falls back: DDG backends → Brave → empty list.
        """
        safe_val = safesearch.value if isinstance(safesearch, SafeSearchLevel) else str(safesearch)
        time_val = timelimit.value if isinstance(timelimit, TimeLimit) else timelimit

        candidates = await self._search_ddg(query, safe_val, time_val, region)
        if candidates:
            return candidates

        if settings.brave_api_key:
            logger.warning(
                "SearchService: all DDG backends exhausted — falling back to Brave Search."
            )
            candidates = await self._search_brave(query)
            if candidates:
                return candidates
            logger.error("SearchService: Brave Search also failed.")
        else:
            logger.error(
                "SearchService: DuckDuckGo failed on every backend and no Brave "
                "fallback is configured. Set BRAVE_API_KEY in .env."
            )
        return []

    # ------------------------------------------------------------------ DDG

    async def _search_ddg(
        self, query: str, safesearch: str, timelimit: str | None, region: str
    ) -> list[SearchCandidate]:
        """Try each DDG backend in order; first one that yields results wins."""
        for backend in self.backends:
            raw = await self._search_one_backend(
                query, safesearch, timelimit, region, backend
            )
            candidates = self._filter_candidates(raw)
            if candidates:
                logger.info(
                    "SearchService [DDG/%s]: %d candidates for %r",
                    backend, len(candidates), query,
                )
                return candidates
            logger.warning(
                "SearchService [DDG/%s]: no usable results — trying next backend.", backend
            )
        return []

    async def _search_one_backend(
        self, query: str, safesearch: str, timelimit: str | None,
        region: str, backend: str,
    ) -> list[dict]:
        """Run one backend with retry-with-backoff on rate-limit errors."""
        fetch_count = self.max_results * 3
        delay = _DDG_BASE_DELAY

        for attempt in range(1, _DDG_MAX_ATTEMPTS + 1):
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self._ddg_sync(
                        query, fetch_count, safesearch, timelimit, region, backend
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — provider errors are opaque
                err = str(exc).lower()
                is_rate = "ratelimit" in err or "202" in err or "rate limit" in err
                if attempt < _DDG_MAX_ATTEMPTS:
                    wait = min(delay, _DDG_MAX_DELAY)
                    logger.warning(
                        "SearchService [DDG/%s]: %s (attempt %d/%d). Retrying in %.1fs.",
                        backend, "rate limit" if is_rate else exc,
                        attempt, _DDG_MAX_ATTEMPTS, wait,
                    )
                    await asyncio.sleep(wait)
                    delay *= 2
                else:
                    logger.error(
                        "SearchService [DDG/%s]: failed after %d attempts: %s",
                        backend, _DDG_MAX_ATTEMPTS, exc,
                    )
        return []

    def _ddg_sync(
        self, query: str, fetch_count: int, safesearch: str,
        timelimit: str | None, region: str, backend: str,
    ) -> list[dict]:
        """Blocking DDG call — always run inside a thread-pool executor."""
        proxy = _random_proxy()
        ddgs_kwargs: dict = {}
        if proxy:
            ddgs_kwargs["proxy"] = proxy
        with DDGS(**ddgs_kwargs) as ddgs:
            return list(
                ddgs.text(
                    query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=fetch_count,
                    backend=backend,
                )
            )

    # ---------------------------------------------------------------- Brave

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
            candidates: list[SearchCandidate] = []
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
                "SearchService [Brave]: %d candidates for %r", len(candidates), query
            )
            return candidates

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 401:
                logger.error("SearchService: Brave 401 — check BRAVE_API_KEY.")
            elif code == 429:
                logger.error("SearchService: Brave 429 — monthly quota exhausted.")
            else:
                logger.error("SearchService: Brave HTTP error: %s", e)
            return []
        except Exception as e:  # noqa: BLE001
            logger.error("SearchService: Brave failed: %s", e, exc_info=True)
            return []

    # --------------------------------------------------------------- filter

    def _filter_candidates(self, raw_results: list[dict]) -> list[SearchCandidate]:
        candidates: list[SearchCandidate] = []
        for result in raw_results:
            # DDG result dicts use 'href'/'body'; some backends use 'url'.
            url = result.get("href") or result.get("url", "")
            if not self._is_valid_url(url):
                continue
            candidates.append(
                SearchCandidate(
                    title=result.get("title", "Untitled"),
                    url=url,
                    snippet=result.get("body") or result.get("description", ""),
                )
            )
            if len(candidates) >= self.max_results:
                break
        return candidates

    def _is_valid_url(self, url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        return not any(blocked in url for blocked in BLOCKED_DOMAINS)
