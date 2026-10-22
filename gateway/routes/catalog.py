from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from gateway.auth import require_token
from gateway.catalog import CatalogResponse, catalog_with_templates
from gateway.templates import find_view

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/catalog")
def catalog(request: Request) -> CatalogResponse:
    state = request.app.state
    return catalog_with_templates(state.catalog, state.settings.templates_dir)


@router.get("/templates/{body}/{view}/guide.png")
def template_guide(request: Request, body: str, view: str) -> FileResponse:
    state = request.app.state
    if body not in {b.id for b in state.catalog.bodies}:
        raise HTTPException(status_code=404, detail="Unknown body type")
    template = find_view(state.settings.templates_dir, body, view)
    if template.guide is None:
        raise HTTPException(status_code=404, detail="Template not generated yet")
    return FileResponse(template.guide, media_type="image/png")
