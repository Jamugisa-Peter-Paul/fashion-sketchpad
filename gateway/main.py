"""FastAPI app factory. Run with: uvicorn gateway.main:create_app --factory --host 127.0.0.1 --port 8190"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway import __version__
from gateway.catalog import load_catalog
from gateway.config import Settings
from gateway.routes import catalog as catalog_routes
from gateway.routes import sketch as sketch_routes
from gateway.storage import Storage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Fashion Sketchpad gateway", version=__version__)
    app.state.settings = settings
    app.state.catalog = load_catalog()
    app.state.storage = Storage(settings.data_dir)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(catalog_routes.router)
    app.include_router(sketch_routes.router)
    return app

