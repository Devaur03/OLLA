"""FastAPI exception handlers that convert domain exceptions to JSON responses."""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors.exceptions import (
    HybridSearchError,
    SearchProviderError,
    RateLimitError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def register_handlers(app) -> None:
    """Register all exception handlers on the FastAPI app."""

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError):
        logger.warning("Rate limit: %s", exc.message)
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=429,
            content={"detail": exc.message, "type": "rate_limit"},
            headers=headers,
        )

    @app.exception_handler(SearchProviderError)
    async def search_provider_handler(request: Request, exc: SearchProviderError):
        logger.error("Search provider error: %s", exc.message)
        return JSONResponse(
            status_code=503,
            content={"detail": exc.message, "type": "search_provider_error"},
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.message, "type": "validation_error", "details": exc.details},
        )

    @app.exception_handler(HybridSearchError)
    async def generic_handler(request: Request, exc: HybridSearchError):
        logger.error("Application error: %s | details: %s", exc.message, exc.details)
        return JSONResponse(
            status_code=500,
            content={"detail": exc.message, "type": "internal_error"},
        )
