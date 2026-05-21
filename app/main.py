"""
Application entry point.

Middleware order (outermost = first on request):
  CORS → Tracing → UsageMeter → Auth

Routers: health, search, semantic, keys, billing, dashboard
"""
import asyncio
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import os


from app.config import settings
from app.core.logging.setup import configure_logging
from app.core.errors.handlers import register_handlers
from app.api.routes import health, search, semantic, dashboard, graph
from app.api.routes import keys, billing
from app.api.middleware.auth import AuthMiddleware
from app.api.middleware.usage_meter import UsageMeterMiddleware
from app.api.middleware.tracing import RequestTracingMiddleware

configure_logging(json_output=settings.log_json, log_dir="logs")
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

    # Middleware — outermost runs first on request, last on response
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestTracingMiddleware)
    app.add_middleware(UsageMeterMiddleware)   # reads state set by AuthMiddleware
    app.add_middleware(AuthMiddleware)         # must be innermost so state is set first

    register_handlers(app)

    # Routers
    app.include_router(health.router,   prefix="/api/v1")
    app.include_router(search.router,   prefix="/api/v1")
    app.include_router(semantic.router, prefix="/api/v1")
    app.include_router(graph.router,    prefix="/api/v1")
    app.include_router(keys.router)       # prefix defined in router: /api/v1/keys
    app.include_router(billing.router)    # prefix defined in router: /api/v1/billing

    # Mount static files and SPA route if frontend/dist exists
    frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
    if os.path.exists(frontend_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

        @app.get("/{path_name:path}", include_in_schema=False)
        async def catch_all(path_name: str):
            if path_name.startswith("api/") or path_name.startswith("openapi.json") or path_name.startswith("docs") or path_name.startswith("redoc"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Not Found")
            
            # Check if requested path matches a file directly (e.g. favicon.svg, icons.svg)
            file_path = os.path.join(frontend_dist, path_name)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            # Serve SPA index.html
            index_path = os.path.join(frontend_dist, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)

            return HTMLResponse(content="<h3>Frontend is building... Please refresh.</h3>")


    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "Starting %s v%s | auth=%s | embeddings=%s | brave=%s | stripe=%s | logs=%s",
            settings.app_name,
            settings.app_version,
            settings.require_auth,
            "local-BGE" if settings.use_local_embeddings else "openai",
            "yes" if settings.brave_api_key else "no",
            "yes" if settings.stripe_secret_key else "no",
            "json" if settings.log_json else "text",
        )
        db_host = settings.database_url.split("@")[-1] if "@" in settings.database_url else "?"
        logger.info("Database: %s", db_host)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Shutting down %s", settings.app_name)

    return app


app = create_app()
