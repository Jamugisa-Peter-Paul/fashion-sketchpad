"""POST /api/generate and job status/results."""

from __future__ import annotations

import secrets
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from gateway.auth import require_token
from gateway.designs import DesignNotFound
from gateway.models import (
    Design,
    DesignView,
    GenerateRequest,
    GenerateResponse,
    JobStatus,
    JobViewStatus,
    PlacementModel,
    Render,
    RenderView,
    View,
)
from gateway.storage import new_id, read_json

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.post("/generate", status_code=202)
async def generate(request: Request, body: GenerateRequest) -> GenerateResponse:
    state = request.app.state
    catalog, store, storage = state.catalog, state.designs, state.storage
    try:
        body.style.check_ids(catalog)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=exc.args[0]) from exc

    if body.design_id:
        try:
            design = store.load(body.design_id)
        except DesignNotFound as exc:
            raise HTTPException(status_code=404, detail="Design not found") from exc
    else:
        if not body.views:
            raise HTTPException(status_code=422, detail="Sketch at least one view")
        design = Design(id=new_id(), style=body.style)

    folder = store.folder(design.id)
    folder.mkdir(exist_ok=True)
    for view, view_input in body.views.items():
        upload = storage.upload_dir(view_input.clean_id)
        if upload is None:
            raise HTTPException(status_code=422, detail=f"The {view} sketch has expired, please add it again")
        meta = read_json(upload / "meta.json")
        placement = view_input.placement
        if placement is None and meta["source"] == "paper" and catalog.scene(meta["scene"]).on_mannequin:
            placement = PlacementModel(**meta["placement"])
        shutil.copyfile(upload / "sketch.png", folder / f"sketch_{view}.png")
        shutil.copyfile(upload / "lines.png", folder / f"lines_{view}.png")
        design.views[view] = DesignView(
            source=meta["source"], placement=placement, width=meta["width"], height=meta["height"]
        )

    if body.views:
        design.details = None  # a sketch changed: details read off the old one no longer apply
    design.style = body.style
    if body.title is not None:
        design.title = body.title
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    render = Render(id=new_id(), seed=seed, style=body.style, views={v: RenderView() for v in design.views})
    design.renders.append(render)
    store.save(design)
    state.queue.enqueue(render.id)
    return GenerateResponse(job_id=render.id, design_id=design.id)


def _load_job(request: Request, job_id: str) -> tuple[Design, Render]:
    store = request.app.state.designs
    design_id = store.design_for_job(job_id)
    try:
        design = store.load(design_id) if design_id else None
    except DesignNotFound:
        design = None
    render = next((r for r in design.renders if r.id == job_id), None) if design else None
    if design is None or render is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return design, render


def render_image_url(job_id: str, view: str) -> str:
    return f"/api/jobs/{job_id}/{view}.png"


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str) -> JobStatus:
    design, render = _load_job(request, job_id)
    queue = request.app.state.queue
    return JobStatus(
        id=render.id,
        design_id=design.id,
        status=render.status,
        seed=render.seed,
        position=queue.position(job_id),
        eta_seconds=queue.eta_seconds(job_id),
        views={
            view: JobViewStatus(
                status=state.status,
                error=state.error,
                image_url=render_image_url(job_id, view) if state.status == "done" else None,
            )
            for view, state in render.views.items()
        },
        details=render.details,
    )


@router.get("/jobs/{job_id}/{view}.png")
def job_image(request: Request, job_id: str, view: View) -> FileResponse:
    design, _ = _load_job(request, job_id)
    path = request.app.state.designs.folder(design.id) / f"render_{job_id}_{view}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Render not ready")
    return FileResponse(path, media_type="image/png")


@router.get("/jobs/{job_id}/{view}/check.png")
def job_check_image(request: Request, job_id: str, view: View) -> FileResponse:
    """Placement check: the control lines over the body template with neck/shoulder/waist/hip lines."""
    design, _ = _load_job(request, job_id)
    path = request.app.state.designs.folder(design.id) / f"check_{job_id}_{view}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Check image not ready")
    return FileResponse(path, media_type="image/png")


@router.get("/jobs/{job_id}/{view}/depth.png")
def job_depth_image(request: Request, job_id: str, view: View) -> FileResponse:
    """The body depth fed to the depth ControlNet, with the garment's silhouette cut in (on-mannequin only)."""
    design, _ = _load_job(request, job_id)
    path = request.app.state.designs.folder(design.id) / f"depth_{job_id}_{view}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No depth image for this view")
    return FileResponse(path, media_type="image/png")


@router.get("/jobs/{job_id}/{view}/workflow.json")
def job_workflow(request: Request, job_id: str, view: View) -> FileResponse:
    """The exact ComfyUI workflow (API format, prompt included) that was queued for this view."""
    design, _ = _load_job(request, job_id)
    path = request.app.state.designs.folder(design.id) / f"workflow_{job_id}_{view}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Workflow not submitted yet")
    return FileResponse(path, media_type="application/json")
