"""FastAPI app factory. Run with: uvicorn gateway.main:app --host 127.0.0.1 --port 8190"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gateway import __version__
from gateway.auth import require_token
from gateway.catalog import CatalogResponse, catalog_with_templates, load_catalog
from gateway.config import Settings
from gateway.templates import find_view


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Fashion Sketchpad gateway", version=__version__)
    app.state.settings = settings
    app.state.catalog = load_catalog()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/catalog", dependencies=[Depends(require_token)])
    def catalog(request: Request) -> CatalogResponse:
        return catalog_with_templates(request.app.state.catalog, settings.templates_dir)

    @app.get("/api/templates/{body}/{view}/guide.png", dependencies=[Depends(require_token)])
    def template_guide(request: Request, body: str, view: str) -> FileResponse:
        if body not in {b.id for b in request.app.state.catalog.bodies}:
            raise HTTPException(status_code=404, detail="Unknown body type")
        template = find_view(settings.templates_dir, body, view)
        if template.guide is None:
            raise HTTPException(status_code=404, detail="Template not generated yet")
        return FileResponse(template.guide, media_type="image/png")

    return app


app = create_app()
