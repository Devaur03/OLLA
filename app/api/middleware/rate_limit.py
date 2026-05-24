"""
Rate-limiting middleware (Phase 12).

A sliding-window limiter: each client may make at most `RATE_LIMIT_PER_MINUTE`
requests in any rolling 60-second window. Exceeding it returns HTTP 429 with a
`Retry-After` header.

Client identity is the `X-API-Key` header when present (so each key gets its
own budget), otherwise the peer IP. The limiter is in-process — fine for a
single instance; a multi-instance deployment should move the window store to
Redis. `GET /api/v1/health` is always exempt so liveness probes never trip it.

Disabled by default (`RATE_LIMIT_PER_MINUTE=0`).
"""

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

_WINDOW_SECONDS = 60.0
_EXEMPT_PATHS = {"/api/v1/health"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-client request limiter."""

    def __init__(self, app):
        super().__init__(app)
        self.limit = settings.rate_limit_per_minute
        # client id -> deque of request timestamps within the window
        self._hits: dict[str, deque] = defaultdict(deque)

    def _client(self, request: Request) -> str:
        key = request.headers.get("x-api-key")
        if key:
            return f"key:{key}"
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Disabled, or an exempt path → straight through.
        if self.limit <= 0 or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        now = time.monotonic()
        cutoff = now - _WINDOW_SECONDS
        hits = self._hits[self._client(request)]

        # Drop timestamps that have aged out of the window.
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = int(_WINDOW_SECONDS - (now - hits[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again shortly.",
                    "limit_per_minute": self.limit,
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        hits.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.limit - len(hits)))
        return response
