import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import health, search, semantic
from app.api.middleware.auth import AuthMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth middleware (only active when REQUIRE_AUTH=true)
    app.add_middleware(AuthMiddleware)

    # Routes
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(semantic.router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup():
        logger.info(f"Starting {settings.app_name} v{settings.app_version}")
        logger.info(f"Auth required: {settings.require_auth}")
        logger.info(f"Database: {settings.database_url.split('@')[-1]}")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Shutting down application")

    return app


app = create_app()
