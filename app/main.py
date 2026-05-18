import logging
import sys
import json
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import health, search, semantic, dashboard
from app.api.middleware.auth import AuthMiddleware


# --- Logging setup -----------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for production log aggregators."""

    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
    root.addHandler(handler)


_configure_logging()
logger = logging.getLogger(__name__)


# --- App factory -------------------------------------------------------------

def create_app():
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(AuthMiddleware)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(semantic.router, prefix="/api/v1")
    app.include_router(dashboard.router)

    @app.on_event("startup")
    async def on_startup():
        logger.info("Starting %s v%s", settings.app_name, settings.app_version)
        logger.info(
            "Config: auth=%s | embeddings=%s | brave_fallback=%s | log_format=%s",
            settings.require_auth,
            "local-BGE" if settings.use_local_embeddings else "openai",
            "yes" if settings.brave_api_key else "no",
            "json" if settings.log_json else "text",
        )
        logger.info("Database: %s", settings.database_url.split("@")[-1])

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Shutting down application")

    return app


app = create_app()
