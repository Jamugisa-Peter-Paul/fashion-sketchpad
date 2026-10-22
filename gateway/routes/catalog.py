from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image

from gateway.auth import require_token
from gateway.catalog import CatalogResponse, catalog_with_templates
from gateway.templates import ViewTemplate, find_view

THUMB_SIZE = 240

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/catalog")
def catalog(request: Request) -> CatalogResponse:
    state = request.app.state
    return catalog_with_templates(state.catalog, state.settings.templates_dir)


def _template(request: Request, body: str, view: str) -> ViewTemplate:
    state = request.app.state
    if body not in {b.id for b in state.catalog.bodies}:
        raise HTTPException(status_code=404, detail="Unknown body type")
    return find_view(state.settings.templates_dir, body, view)


@router.get("/templates/{body}/{view}/guide.png")
def template_guide(request: Request, body: str, view: str) -> FileResponse:
    template = _template(request, body, view)
    if template.guide is None:
        raise HTTPException(status_code=404, detail="Template not generated yet")
    return FileResponse(template.guide, media_type="image/png")


@lru_cache(maxsize=128)
def _thumbnail(path: Path, mtime: float) -> bytes:
    image = Image.open(path).convert("RGB")
    image.thumbnail((THUMB_SIZE, THUMB_SIZE * 2))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


@router.get("/templates/{body}/{view}/photo.jpg")
def template_photo(request: Request, body: str, view: str) -> Response:
    """Small JPEG of the template's mannequin photo, for the body-type cards."""
    template = _template(request, body, view)
    if template.photo is None:
        raise HTTPException(status_code=404, detail="Template not generated yet")
    return Response(_thumbnail(template.photo, template.photo.stat().st_mtime), media_type="image/jpeg")
