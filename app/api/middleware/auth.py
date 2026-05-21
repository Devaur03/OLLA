"""
API key authentication middleware.

When REQUIRE_AUTH=true every non-public request must carry an X-API-Key header.
The key is checked against:
  1. Static keys from the API_KEYS env var (comma-separated) — legacy / self-hosted.
  2. DB-backed api_keys table (hashed SHA-256) — used by the hosted SaaS layer.

On a DB hit the middleware attaches to request.state:
    api_key_id  — str UUID of the matched api_key row
    user_id     — str UUID of the owning user
    user_plan   — str plan name ("free", "starter", "pro", "team", "enterprise")
    user_email  — str email of the owning user

UsageMeterMiddleware reads these from request.state downstream.
"""

import hashlib
import logging

from fastapi.responses import JSONResponse
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/dashboard",
    "/billing",
    "/api/v1/keys/register",
    "/api/v1/billing/webhook",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _lookup_db_key(raw_key: str) -> dict | None:
    """
    Look up a hashed API key in the database.
    Returns a dict with user info on hit, or None on miss/error.
    Lazy-imports DB session to avoid circular imports.
    """
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.db.api_key import ApiKey
        from app.models.db.user import User

        key_hash = _sha256(raw_key)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApiKey, User)
                .join(User, ApiKey.user_id == User.id)
                .where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
            )
            row = result.first()
            if row:
                api_key, user = row
                # Update last_used_at
                from datetime import datetime, timezone
                api_key.last_used_at = datetime.now(timezone.utc)
                await session.commit()
                return {
                    "api_key_id": api_key.id,
                    "user_id": user.id,
                    "user_plan": user.plan,
                    "user_email": user.email,
                }
    except Exception as e:
        logger.warning("AuthMiddleware: DB key lookup failed: %s", e)
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """API key authentication — static env-var keys OR DB-backed keys."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always try to resolve user context from X-API-Key header,
        # even when REQUIRE_AUTH=false (so user-scoped routes work).
        raw_key = request.headers.get("X-API-Key", "").strip()

        if raw_key:
            # 1. Static keys (legacy / self-hosted)
            static_keys = settings.get_api_keys()
            if raw_key in static_keys:
                request.state.api_key_id = None
                request.state.user_id    = "static"
                request.state.user_plan  = "enterprise"
                request.state.user_email = ""
                return await call_next(request)

            # 2. DB-backed keys
            info = await _lookup_db_key(raw_key)
            if info:
                request.state.api_key_id = info["api_key_id"]
                request.state.user_id    = info["user_id"]
                request.state.user_plan  = info["user_plan"]
                request.state.user_email = info["user_email"]
                return await call_next(request)

            # Key provided but not valid
            if settings.require_auth and path not in PUBLIC_PATHS:
                logger.warning("AuthMiddleware: invalid key on %s", path)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or revoked API key."},
                )

        # No key provided
        if settings.require_auth and path not in PUBLIC_PATHS:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header."},
            )

        # Public path or auth not required — proceed without user context
        return await call_next(request)
