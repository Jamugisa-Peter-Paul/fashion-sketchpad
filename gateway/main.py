"""FastAPI app factory. Run with: uvicorn gateway.main:create_app --factory --host 127.0.0.1 --port 8190"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from gateway import __version__
from gateway.catalog import load_catalog
from gateway.comfy import ComfyClient
from gateway.config import Settings
from gateway.designs import DesignStore
from gateway.details import DetailsClient
from gateway.jobs import RenderQueue
from gateway.routes import catalog as catalog_routes
from gateway.routes import designs as designs_routes
from gateway.routes import jobs as jobs_routes
from gateway.routes import sketch as sketch_routes
from gateway.storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(
    settings: Settings | None = None,
    comfy_transport: httpx.AsyncBaseTransport | None = None,
    llm_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """`comfy_transport` / `llm_transport` let tests point the clients at in-process fakes."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.storage = Storage(settings.data_dir)
        app.state.designs = DesignStore(app.state.storage.designs)
        app.state.comfy = ComfyClient(settings.comfy_url, transport=comfy_transport)
        app.state.details = DetailsClient(settings.llm, transport=llm_transport)
        app.state.details_cache = {}  # POST /api/sketch/details results per sketch set
        app.state.queue = RenderQueue(
            app.state.designs, app.state.comfy, app.state.catalog, settings, app.state.details
        )
        app.state.queue.start()
        yield
        await app.state.queue.stop()
        await app.state.comfy.close()
        await app.state.details.close()

    app = FastAPI(title="Fashion Sketchpad gateway", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.catalog = load_catalog()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, str]:
        comfy_ok = await request.app.state.comfy.ping()
        return {
            "status": "ok",
            "version": __version__,
            "comfy": "ok" if comfy_ok else "unreachable",
            "details": "on" if settings.llm.enabled else "off",
        }

    app.include_router(catalog_routes.router)
    app.include_router(sketch_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(designs_routes.router)
    return app
