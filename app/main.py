"""
Application entry point.

Wires together:
  - Structured logging (plain-text dev, JSON prod)
  - FastAPI app with CORS + Auth + Tracing middleware
  - Domain exception handlers (uniform JSON error responses)
  - DI container (singletons wired at startup)
  - All API routers
"""
import asyncio
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging.setup import configure_logging
from app.core.errors.handlers import register_handlers
from app.api.routes import health, search, semantic, dashboard
from app.api.middleware.auth import AuthMiddleware
from app.api.middleware.tracing import RequestTracingMiddleware

configure_logging(
    json_output=settings.log_json,
    log_dir="logs",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Application factory.

    Returns:
        Fully configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Web retrieval system for AI agents and RAG applications. "
            "Supports web search, content extraction, chunking, semantic search, "
            "and MCP agent integration."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ------------------------------------------------------------------ middleware
    # Order matters: outermost middleware runs first on request, last on response.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestTracingMiddleware)
    app.add_middleware(AuthMiddleware)

    # ------------------------------------------------------------------ exception handlers
    register_handlers(app)

    # ------------------------------------------------------------------ routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(semantic.router, prefix="/api/v1")
    app.include_router(dashboard.router)

    # ------------------------------------------------------------------ lifecycle
    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "Starting %s v%s | auth=%s | embeddings=%s | brave=%s | logs=%s",
            settings.app_name,
            settings.app_version,
            settings.require_auth,
            "local-BGE" if settings.use_local_embeddings else "openai",
            "yes" if settings.brave_api_key else "no",
            "json" if settings.log_json else "text",
        )
        db_host = settings.database_url.split("@")[-1] if "@" in settings.database_url else "?"
        logger.info("Database: %s", db_host)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Shutting down %s", settings.app_name)

    return app


app = create_app()
