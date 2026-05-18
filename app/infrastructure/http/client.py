"""Shared async HTTP client with connection pooling and retry-backoff."""
from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Optional, Type

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_DEFAULT_MAX_CONNECTIONS = 100
_DEFAULT_MAX_KEEPALIVE = 20


class HTTPClient:
    """
    Async HTTP client with connection pooling and exponential-backoff retry.

    Use as an async context manager:

        async with HTTPClient(timeout=15) as client:
            response = await client.get_with_retry("https://example.com")

    Args:
        timeout: Request timeout in seconds.
        max_retries: Number of retry attempts on server errors (5xx / timeout).
        max_connections: Maximum total connection pool size.
    """

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = 3,
        max_connections: int = _DEFAULT_MAX_CONNECTIONS,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=_DEFAULT_MAX_KEEPALIVE,
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HTTPClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            limits=self._limits,
            follow_redirects=True,
            headers={"User-Agent": "HybridSearch/1.0"},
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Simple GET — no retry."""
        assert self._client, "Use HTTPClient as an async context manager"
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Simple POST — no retry."""
        assert self._client, "Use HTTPClient as an async context manager"
        return await self._client.post(url, **kwargs)

    async def get_with_retry(
        self,
        url: str,
        max_attempts: Optional[int] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        GET with exponential-backoff retry on server errors and timeouts.

        Client errors (4xx) are NOT retried.

        Args:
            url: Target URL.
            max_attempts: Override instance default.
            **kwargs: Forwarded to httpx.AsyncClient.get().

        Returns:
            Successful httpx.Response.

        Raises:
            httpx.HTTPStatusError: On non-retryable 4xx errors.
            RuntimeError: If all attempts are exhausted.
        """
        assert self._client, "Use HTTPClient as an async context manager"
        attempts = max_attempts or self._max_retries
        delay = 1.0

        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
                logger.warning(
                    "HTTP %d on attempt %d/%d for %s",
                    exc.response.status_code, attempt, attempts, url,
                )
                if attempt == attempts:
                    raise
            except httpx.TimeoutException as exc:
                if attempt == attempts:
                    raise
                logger.warning("HTTP timeout attempt %d/%d for %s", attempt, attempts, url)
            except httpx.HTTPStatusError:
                raise
            await asyncio.sleep(min(delay, 10.0))
            delay *= 2

        raise RuntimeError("get_with_retry exhausted without result")
