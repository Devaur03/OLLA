"""
PURPOSE: Fetch clean markdown content from URLs using Jina Reader.
Jina Reader (r.jina.ai) is a free service that takes any URL and returns
clean, readable text/markdown — no scraping or HTML parsing needed.

Usage: GET https://r.jina.ai/https://example.com
Returns: clean markdown text of that page

All fetches are done concurrently with asyncio + httpx.
A semaphore limits max concurrent requests to avoid being rate-limited.
"""

import asyncio
import logging
import httpx
from app.models.response import SearchCandidate, FetchedPage
from app.config import settings

logger = logging.getLogger(__name__)


class FetchService:
    """
    Fetches clean markdown content from a list of URLs concurrently.
    Uses Jina Reader API (r.jina.ai) as the extraction backend.
    """

    def __init__(
        self,
        timeout: int | None = None,
        max_concurrent: int | None = None,
    ):
        self.timeout = timeout or settings.fetch_timeout_seconds
        self.max_concurrent = max_concurrent or settings.max_concurrent_fetches
        self.base_url = settings.fetch_base_url  # "https://r.jina.ai"
        # Semaphore limits how many requests run at the same time
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def fetch_all(
        self,
        candidates: list[SearchCandidate],
        max_chars: int = 8000,
    ) -> list[FetchedPage]:
        """
        Fetch content from all candidate URLs concurrently.

        Args:
            candidates: List of SearchCandidate objects (title + url).
            max_chars: Truncate each page's content to this many characters.

        Returns:
            List of FetchedPage objects for successfully fetched pages.
            Failed fetches are silently dropped.
        """
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "HybridSearchAgent/1.0",
                "Accept": "text/plain, text/markdown",
                # X-Return-Format tells Jina to return markdown
                "X-Return-Format": "markdown",
            },
        ) as client:
            tasks = [
                self._fetch_one(client, candidate, max_chars)
                for candidate in candidates
            ]
            # return_exceptions=True prevents one failure from cancelling everything
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None values and exceptions
        pages = [r for r in raw_results if isinstance(r, FetchedPage)]
        logger.info(
            f"FetchService: fetched {len(pages)}/{len(candidates)} pages successfully"
        )
        return pages

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        candidate: SearchCandidate,
        max_chars: int,
    ) -> FetchedPage | None:
        """
        Fetch a single URL through Jina Reader.
        Uses semaphore to limit concurrent requests.
        Returns None on any failure.
        """
        async with self._semaphore:
            try:
                # Jina Reader format: https://r.jina.ai/{target_url}
                jina_url = f"{self.base_url}/{candidate.url}"

                response = await client.get(jina_url)
                response.raise_for_status()

                content = response.text

                # Truncate to max_chars — further processing happens downstream
                if len(content) > max_chars:
                    content = content[:max_chars]

                if not content.strip():
                    logger.debug(f"FetchService: empty content from {candidate.url}")
                    return None

                return FetchedPage(
                    title=candidate.title,
                    url=candidate.url,
                    raw_content=content,
                )

            except httpx.TimeoutException:
                logger.warning(f"FetchService: timeout fetching {candidate.url}")
                return None
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"FetchService: HTTP {e.response.status_code} for {candidate.url}"
                )
                return None
            except Exception as e:
                logger.warning(f"FetchService: failed to fetch {candidate.url}: {e}")
                return None
