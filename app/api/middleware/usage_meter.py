"""
Usage metering + tier quota enforcement middleware.

For every request that carries a valid API key this middleware:
  1. Looks up the associated user and their plan.
  2. Counts how many usage_events they have in the current calendar month.
  3. If over quota → returns HTTP 429 with a clear upgrade message.
  4. After the request completes → writes a usage_event row (non-blocking).

Tier limits (queries / calendar month):
  free       :   1 000
  starter    :  10 000
  pro        :  50 000
  team       : 200 000
  enterprise :  unlimited

The middleware skips metering for:
  - Requests with no API key (unauthenticated — handled by AuthMiddleware).
  - Public paths (/health, /docs, /redoc, /openapi.json, /dashboard, /billing).
  - Requests where REQUIRE_AUTH is False (dev mode).
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# Monthly query limits per plan  (None = unlimited)
PLAN_LIMITS: dict[str, int | None] = {
    "free": 1_000,
    "starter": 10_000,
    "pro": 50_000,
    "team": 200_000,
    "enterprise": None,
}

# Paths exempt from metering
_EXEMPT_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/dashboard",
    "/billing",
    "/api/v1/keys/register",
    "/api/v1/billing/webhook",  # Stripe webhook — never metered
}

_METERED_PATHS_PREFIX = "/api/v1/search"  # only search endpoints consume quota


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class UsageMeterMiddleware(BaseHTTPMiddleware):
    """
    Sits *after* AuthMiddleware in the middleware stack so API key auth has
    already run.  Reads the resolved api_key_id and user_id from request.state
    (set by AuthMiddleware when it validates a key).

    Falls back gracefully — if DB is unavailable it logs a warning and lets the
    request through rather than blocking legitimate users.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip metering in dev mode or for exempt paths
        if not settings.require_auth:
            return await call_next(request)

        path = request.url.path
        if path in _EXEMPT_PATHS or not path.startswith(_METERED_PATHS_PREFIX):
            return await call_next(request)

        # Auth middleware sets these on request.state when key is valid
        api_key_id: str | None = getattr(request.state, "api_key_id", None)
        user_id: str | None = getattr(request.state, "user_id", None)
        user_plan: str = getattr(request.state, "user_plan", "free")

        if not user_id:
            # No authenticated user — let AuthMiddleware's 403 handle it
            return await call_next(request)

        # ── Quota check ───────────────────────────────────────────────────────
        limit = PLAN_LIMITS.get(user_plan)
        if limit is not None:
            try:
                count = await _count_monthly_usage(user_id)
                if count >= limit:
                    logger.warning(
                        "Quota exceeded: user=%s plan=%s count=%d limit=%d",
                        user_id,
                        user_plan,
                        count,
                        limit,
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                f"Monthly query limit reached ({count}/{limit} on the "
                                f"'{user_plan}' plan). "
                                "Upgrade at /dashboard to continue."
                            ),
                            "plan": user_plan,
                            "used": count,
                            "limit": limit,
                            "upgrade_url": "/dashboard#billing",
                        },
                    )
            except Exception as e:
                logger.warning("UsageMeterMiddleware: quota check failed (letting through): %s", e)

        # ── Run request + record event ────────────────────────────────────────
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Fire-and-forget: write usage event after response is already sent
        try:
            await _record_usage(
                api_key_id=api_key_id,
                user_id=user_id,
                endpoint=path,
                response_time_ms=elapsed_ms,
                status_code=response.status_code,
            )
        except Exception as e:
            logger.warning("UsageMeterMiddleware: failed to record usage event: %s", e)

        return response


# ── DB helpers (async, import lazily to avoid circular imports) ───────────────


async def _count_monthly_usage(user_id: str) -> int:
    """Return the number of search queries the user has made this calendar month."""
    from sqlalchemy import select, func, and_
    from app.db.session import AsyncSessionLocal
    from app.models.db.usage_event import UsageEvent

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(UsageEvent.id)).where(
                and_(
                    UsageEvent.user_id == user_id,
                    UsageEvent.created_at >= month_start,
                    UsageEvent.endpoint.startswith("/api/v1/search"),
                )
            )
        )
        return result.scalar_one() or 0


async def _record_usage(
    *,
    api_key_id: str | None,
    user_id: str | None,
    endpoint: str,
    response_time_ms: int,
    status_code: int,
) -> None:
    """Insert a single usage_event row."""
    from app.db.session import AsyncSessionLocal
    from app.models.db.usage_event import UsageEvent

    async with AsyncSessionLocal() as session:
        event = UsageEvent(
            id=str(uuid.uuid4()),
            api_key_id=api_key_id,
            user_id=user_id,
            endpoint=endpoint,
            response_time_ms=response_time_ms,
            cache_hit=False,  # updated retroactively if needed
            status_code=status_code,
        )
        session.add(event)
        await session.commit()
