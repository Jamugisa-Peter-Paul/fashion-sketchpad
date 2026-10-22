"""Gallery: list, open, rename and delete designs, plus their sketch images."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gateway.auth import require_token
from gateway.designs import DesignNotFound
from gateway.models import Design, DesignSummary, DesignView, RenderView, View, ViewStatus
from gateway.prompts import StyleOptions
from gateway.routes.jobs import render_image_url

router = APIRouter(prefix="/api/designs", dependencies=[Depends(require_token)])


class RenderOut(BaseModel):
    id: str
    seed: int
    style: StyleOptions
    views: dict[View, RenderView]
    created_at: float
    status: ViewStatus
    image_urls: dict[View, str]


class DesignOut(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float
    style: StyleOptions
    views: dict[View, DesignView]
    renders: list[RenderOut]
    sketch_urls: dict[View, str]
    lines_urls: dict[View, str]


class DesignPatch(BaseModel):
    title: str = Field(max_length=80)


def _load(request: Request, design_id: str) -> Design:
    try:
        return request.app.state.designs.load(design_id)
    except DesignNotFound as exc:
        raise HTTPException(status_code=404, detail="Design not found") from exc


def _thumbnail(design: Design) -> str | None:
    for render in reversed(design.renders):
        for view, state in render.views.items():
            if state.status == "done":
                return render_image_url(render.id, view)
    view = next(iter(design.views), None)
    return f"/api/designs/{design.id}/sketch/{view}.png" if view else None


def _out(design: Design) -> DesignOut:
    renders = [
        RenderOut(
            **render.model_dump(),
            status=render.status,
            image_urls={v: render_image_url(render.id, v) for v, s in render.views.items() if s.status == "done"},
        )
        for render in design.renders
    ]
    data = design.model_dump(exclude={"renders"})
    return DesignOut(
        **data,
        renders=renders,
        sketch_urls={v: f"/api/designs/{design.id}/sketch/{v}.png" for v in design.views},
        lines_urls={v: f"/api/designs/{design.id}/lines/{v}.png" for v in design.views},
    )


@router.get("")
def list_designs(request: Request) -> list[DesignSummary]:
    return [
        DesignSummary(
            id=d.id,
            title=d.title,
            garment=d.style.garment,
            body=d.style.body,
            updated_at=d.updated_at,
            render_count=len(d.renders),
            thumbnail_url=_thumbnail(d),
        )
        for d in request.app.state.designs.all()
    ]


@router.get("/{design_id}")
def get_design(request: Request, design_id: str) -> DesignOut:
    return _out(_load(request, design_id))


@router.patch("/{design_id}")
def rename_design(request: Request, design_id: str, patch: DesignPatch) -> DesignOut:
    try:
        with request.app.state.designs.update(design_id) as design:
            design.title = patch.title
    except DesignNotFound as exc:
        raise HTTPException(status_code=404, detail="Design not found") from exc
    return _out(design)


@router.delete("/{design_id}", status_code=204)
def delete_design(request: Request, design_id: str) -> Response:
    try:
        request.app.state.designs.delete(design_id)
    except DesignNotFound as exc:
        raise HTTPException(status_code=404, detail="Design not found") from exc
    return Response(status_code=204)


@router.get("/{design_id}/{kind}/{view}.png")
def design_image(request: Request, design_id: str, kind: str, view: View) -> FileResponse:
    if kind not in ("sketch", "lines"):
        raise HTTPException(status_code=404, detail="Not found")
    design = _load(request, design_id)
    path = request.app.state.designs.folder(design.id) / f"{kind}_{view}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/png")
