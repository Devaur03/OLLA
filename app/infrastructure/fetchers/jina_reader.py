"""
Jina Reader implementation of ContentFetcher.

Calls r.jina.ai/<url> to get clean markdown from any web page.
Falls back to raw httpx fetch if Jina is unavailable.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.domain.interfaces.content_fetcher import ContentFetcher, FetchedPage
from app.core.errors.exceptions import ContentFetchError

logger = logging.getLogger(__name__)

_JINA_BASE = "https://r.jina.ai/"
_JINA_TIMEOUT = 20.0
_MIN_CONTENT_LEN = 100


class JinaReaderFetcher(ContentFetcher):
    """
    Fetches page content via Jina Reader (r.jina.ai), which strips navigation,
    ads, and boilerplate and returns clean markdown.

    Falls back to a direct httpx GET when Jina returns an error or empty body.
    """

    def __init__(
        self,
        jina_api_key: Optional[str] = None,
        timeout: float = _JINA_TIMEOUT,
        max_concurrent: int = 5,
    ) -> None:
        self._jina_api_key = jina_api_key
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------
    # ContentFetcher interface
    # ------------------------------------------------------------------

    async def fetch_all(self, urls: list[str]) -> list[FetchedPage]:
        tasks = [self._fetch_one(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        pages: list[FetchedPage] = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.warning("JinaReaderFetcher: failed to fetch %s: %s", url, result)
                pages.append(FetchedPage(url=url, content="", success=False, error=str(result)))
            else:
                pages.append(result)
        return pages

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(_JINA_BASE + "https://example.com")
                return resp.status_code < 500
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_one(self, url: str) -> FetchedPage:
        async with self._semaphore:
            content = await self._fetch_jina(url)
            if content and len(content) >= _MIN_CONTENT_LEN:
                return FetchedPage(url=url, content=content, success=True)
            logger.debug("JinaReaderFetcher: Jina returned short content for %s, trying direct", url)
            content = await self._fetch_direct(url)
            if content:
                return FetchedPage(url=url, content=content, success=True)
            return FetchedPage(url=url, content="", success=False, error="Both Jina and direct fetch failed")

    async def _fetch_jina(self, url: str) -> str:
        jina_url = _JINA_BASE + url
        headers = {"Accept": "text/plain"}
        if self._jina_api_key:
            headers["Authorization"] = "Bearer " + self._jina_api_key
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                resp = await client.get(jina_url, headers=headers)
                if resp.status_code == 200:
                    return resp.text.strip()
                logger.debug("JinaReaderFetcher: Jina returned %s for %s", resp.status_code, url)
                return ""
        except Exception as exc:
            logger.debug("JinaReaderFetcher: Jina error for %s: %s", url, exc)
            return ""

    async def _fetch_direct(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HybridSearch/1.0; +https://github.com/you/hybrid-search)",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                text = resp.text
                # Very light HTML tag stripping
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                return text
        except Exception as exc:
            logger.debug("JinaReaderFetcher: direct fetch error for %s: %s", url, exc)
            return ""
