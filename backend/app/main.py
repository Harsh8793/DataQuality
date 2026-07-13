"""FastAPI application factory and entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.init_db import init_db
from app.exceptions import register_exception_handlers
from app.middleware import RequestLoggingMiddleware
from app.schemas.common import ApiResponse

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize logging, storage and database on startup."""
    configure_logging()
    settings.ensure_directories()
    init_db()
    logger.info("%s started (env=%s, llm=%s)", settings.app_name, settings.app_env, settings.is_llm_ready)
    yield
    logger.info("%s shutting down.", settings.app_name)


def create_app() -> FastAPI:
    """Application factory: build and configure the FastAPI app."""
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Enterprise AI Copilot for Data Quality, Analytics & Governance.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["System"])
    def health():
        """Liveness probe."""
        return ApiResponse.ok({"status": "healthy", "llm": settings.is_llm_ready})

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React SPA if it's bundled alongside the API.

    In the combined production image the frontend build is copied to
    ``backend/static``. When present, static assets are served and any
    non-API path falls back to ``index.html`` so client-side routing works.
    All ``/api`` and ``/health`` routes are registered first, so they win.
    """
    static_dir = Path(__file__).resolve().parent.parent / "static"
    index_file = static_dir / "index.html"
    if not index_file.exists():
        return  # dev mode: Vite serves the frontend separately

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)

    logger.info("Serving bundled frontend from %s", static_dir)


app = create_app()
