import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import health, search

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler replacing deprecated on_event."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    yield
    logger.info("Shutting down application")


def create_app() -> FastAPI:
    """
    FastAPI application factory.
    Creates and configures the app instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Web retrieval system for AI agents and RAG applications. "
            "Searches the web, fetches clean content, chunks it for RAG, "
            "and returns structured JSON with relevance scores."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS — allow all origins in development
    # Restrict this in production to your specific frontend domain
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes with /api/v1 prefix
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")

    return app


app = create_app()
