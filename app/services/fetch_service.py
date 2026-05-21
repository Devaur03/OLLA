"""
PURPOSE: Fetch clean content from URLs concurrently with a resilient waterfall.

Waterfall (COMPARISON_README §5.2) — each URL falls through these in order:
  1. Jina Reader (r.jina.ai)  — fast, clean Markdown output.
  2. Direct HTML scrape        — custom browser User-Agent + BeautifulSoup-style
                                 tag stripping; works on many Jina-blocked sites.
  3. DuckDuckGo snippet        — the short `snippet` already carried on the
                                 SearchCandidate. Short but never fails.

Before this change a single Jina failure silently dropped the page. Now the
page degrades to lower-fidelity content instead of disappearing — eliminating
the pipeline's biggest single point of failure.
"""

import asyncio
import logging
import re

import httpx

from app.config import settings
from app.models.response import FetchedPage, SearchCandidate

logger = logging.getLogger(__name__)

_JINA_MAX_ATTEMPTS = 2
_JINA_BASE_DELAY = 1.0
_MIN_CONTENT_LEN = 100  # below this, treat fetched content as a failure

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags whose content is noise for RAG.
_JUNK_TAGS = ("script", "style", "nav", "footer", "header", "aside", "noscript", "svg")


def _strip_html(raw: str) -> str:
    """Best-effort HTML → plain text. Drops junk tags, then all remaining tags."""
    for tag in _JUNK_TAGS:
        raw = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>", " ", raw,
            flags=re.DOTALL | re.IGNORECASE,
        )
    raw = re.sub(r"<!--.*?-->", " ", raw, flags=re.DOTALL)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"&nbsp;", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


class FetchService:
    """Fetches content from a list of candidates concurrently, via the waterfall."""

    def __init__(self, timeout=None, max_concurrent=None):
        self.timeout = timeout or settings.fetch_timeout_seconds
        self.max_concurrent = max_concurrent or settings.max_concurrent_fetches
        self.base_url = settings.fetch_base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def fetch_all(
        self, candidates: list[SearchCandidate], max_chars: int = 8000
    ) -> list[FetchedPage]:
        """Fetch every candidate concurrently; return all pages that yielded content."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
        ) as client:
            tasks = [self._fetch_one(client, c, max_chars) for c in candidates]
            raw = await asyncio.gather(*tasks, return_exceptions=True)

        pages = [r for r in raw if isinstance(r, FetchedPage)]
        by_method: dict[str, int] = {}
        for p in pages:
            by_method[p.fetch_method] = by_method.get(p.fetch_method, 0) + 1
        logger.info(
            "FetchService: %d/%d pages fetched (%s)",
            len(pages), len(candidates),
            ", ".join(f"{k}={v}" for k, v in by_method.items()) or "none",
        )
        return pages

    async def _fetch_one(
        self, client: httpx.AsyncClient, candidate: SearchCandidate, max_chars: int
    ) -> FetchedPage | None:
        async with self._semaphore:
            # Method 1 — Jina Reader
            content = await self._try_jina(client, candidate.url)
            method = "jina"

            # Method 2 — direct HTML scrape
            if not content or len(content) < _MIN_CONTENT_LEN:
                direct = await self._try_direct(client, candidate.url)
                if direct and len(direct) >= _MIN_CONTENT_LEN:
                    content, method = direct, "direct"

            # Method 3 — DuckDuckGo snippet (last resort, always short but reliable)
            if not content or len(content) < _MIN_CONTENT_LEN:
                snippet = (candidate.snippet or "").strip()
                if snippet:
                    content, method = snippet, "snippet"
                    logger.debug("FetchService: using DDG snippet for %s", candidate.url)

            if not content:
                logger.warning("FetchService: all methods failed for %s", candidate.url)
                return None

            if len(content) > max_chars:
                content = content[:max_chars]
            return FetchedPage(
                title=candidate.title,
                url=candidate.url,
                raw_content=content,
                fetch_method=method,
            )

    async def _try_jina(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Fetch via Jina Reader with retry + back-off."""
        headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
        if settings.jina_api_key:
            headers["Authorization"] = f"Bearer {settings.jina_api_key}"

        delay = _JINA_BASE_DELAY
        for attempt in range(1, _JINA_MAX_ATTEMPTS + 1):
            try:
                resp = await client.get(f"{self.base_url}/{url}", headers=headers)
                resp.raise_for_status()
                text = resp.text.strip()
                if text:
                    return text
                return None
            except httpx.TimeoutException:
                logger.warning(
                    "FetchService[Jina]: timeout %s (attempt %d/%d)",
                    url, attempt, _JINA_MAX_ATTEMPTS,
                )
                if attempt < _JINA_MAX_ATTEMPTS:
                    await asyncio.sleep(delay)
                    delay *= 2
            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    logger.warning(
                        "FetchService[Jina]: %d on %s — falling through",
                        e.response.status_code, url,
                    )
                    return None
                if attempt < _JINA_MAX_ATTEMPTS:
                    await asyncio.sleep(delay)
                    delay *= 2
            except Exception as e:  # noqa: BLE001
                logger.debug("FetchService[Jina]: error on %s: %s", url, e)
                return None
        return None

    async def _try_direct(self, client: httpx.AsyncClient, url: str) -> str | None:
        """Direct HTML scrape with a real browser User-Agent."""
        try:
            resp = await client.get(url, headers=_BROWSER_HEADERS)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "html" in ct:
                return _strip_html(resp.text) or None
            return resp.text.strip() or None
        except httpx.TimeoutException:
            logger.warning("FetchService[direct]: timeout for %s", url)
            return None
        except Exception as e:  # noqa: BLE001
            logger.debug("FetchService[direct]: failed for %s: %s", url, e)
            return None
