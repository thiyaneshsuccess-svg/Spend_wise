"""Application factory.

One process serves both the API and (when built) the SPA. Same-origin matters:
it keeps session cookies simple, removes CORS from production, and means a
single container is the whole deployment.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import BACKEND_DIR, get_settings

PROJECT_ROOT = BACKEND_DIR.parent
SPA_DIST = PROJECT_ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SpendWise API",
        version="0.1.0",
        description="Local-first personal finance intelligence workbench",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    if SPA_DIST.is_dir():
        app.mount("/", StaticFiles(directory=SPA_DIST, html=True), name="spa")

    return app
