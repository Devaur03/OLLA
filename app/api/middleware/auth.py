from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Paths that do not require authentication
PUBLIC_PATHS = {"/api/v1/health", "/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    API key authentication middleware.
    Checks X-API-Key header against the configured set of valid keys.
    Only active when REQUIRE_AUTH=true.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth if not required
        if not settings.require_auth:
            return await call_next(request)

        # Skip auth for public paths
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        valid_keys = settings.get_api_keys()

        if not api_key or api_key not in valid_keys:
            logger.warning(
                f"AuthMiddleware: rejected request from {request.client.host} "
                f"— invalid or missing API key"
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing API key. Pass X-API-Key header."}
            )

        return await call_next(request)
