"""POST /api/sketch/clean and the cleaned-image previews.

Every sketch, drawn or photographed, goes through /clean first. The response carries a `clean_id`
and a suggested placement on the 832x1216 canvas; /api/generate then references the clean_id with the
(possibly user-adjusted) placement, so images are uploaded once.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel

from gateway.auth import require_token
from gateway.models import PlacementModel
from gateway.placement import default_landmarks, landmarks_from_mask, load_mask, suggest_placement
from gateway.routes import read_upload
from gateway.sketch import (
    CANVAS_H,
    CANVAS_W,
    Placement,
    SketchError,
    clean_drawn,
    clean_paper,
    decode_image,
    product_shot_placement,
    to_png,
)
from gateway.storage import write_json
from gateway.templates import find_view

router = APIRouter(prefix="/api/sketch", dependencies=[Depends(require_token)])

SKETCH_MAX_SIDE = 2048  # stored copy of the original, for the gallery


class CleanResponse(BaseModel):
    clean_id: str
    source: Literal["paper", "drawn"]
    width: int  # cleaned crop size in px
    height: int
    placement: PlacementModel
    lines_url: str  # white lines on black: what the model sees
    overlay_url: str  # dark lines on transparent: for showing over the body guide


@router.post("/clean")
def clean(
    request: Request,
    image: UploadFile = File(...),
    source: Literal["paper", "drawn"] = Form("paper"),
    scene: str = Form("light_room"),
    garment: str = Form("shirt"),
    body: str = Form("female_slim"),
    view: Literal["front", "back", "side"] = Form("front"),
    whole_body: bool = Form(False),
) -> CleanResponse:
    state = request.app.state
    try:
        scene_item = state.catalog.scene(scene)
        garment_item = state.catalog.garment(garment)
        state.catalog.find("bodies", body)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=exc.args[0]) from exc

    data = read_upload(image, state.settings.max_upload_mb)
    try:
        picture = decode_image(data)
        # Drawn sketches keep the full canvas so they stay aligned with the guide; the product-shot crop
        # happens at render time, so switching scenes later still works.
        crop = clean_paper(picture).lines if source == "paper" else clean_drawn(picture)
    except SketchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    height, width = crop.shape
    if source == "drawn":
        placement = Placement(CANVAS_W / 2, CANVAS_H / 2, 1.0)
    elif not scene_item.on_mannequin:
        placement = product_shot_placement(width, height)
    else:
        template = find_view(state.settings.templates_dir, body, view)
        landmarks = landmarks_from_mask(load_mask(template.mask)) if template.mask else default_landmarks()
        kind = "figure" if whole_body else garment_item.placement
        placement = suggest_placement(width, height, kind, landmarks)

    clean_id, folder = state.storage.new_upload_dir()
    picture.thumbnail((SKETCH_MAX_SIDE, SKETCH_MAX_SIDE))
    picture.save(folder / "sketch.png")
    (folder / "lines.png").write_bytes(to_png(crop))
    placement_model = PlacementModel(cx=placement.cx, cy=placement.cy, scale=placement.scale)
    write_json(
        folder / "meta.json",
        {
            "source": source,
            "scene": scene,
            "garment": garment,
            "body": body,
            "view": view,
            "width": width,
            "height": height,
            "placement": placement_model.model_dump(),
            "created": time.time(),
        },
    )
    state.storage.purge_old_uploads()
    return CleanResponse(
        clean_id=clean_id,
        source=source,
        width=width,
        height=height,
        placement=placement_model,
        lines_url=f"/api/sketch/{clean_id}/lines.png",
        overlay_url=f"/api/sketch/{clean_id}/overlay.png",
    )


def _upload_file(request: Request, clean_id: str, name: str) -> Path:
    folder = request.app.state.storage.upload_dir(clean_id)
    if folder is None or not (folder / name).exists():
        raise HTTPException(status_code=404, detail="Sketch not found (cleaned sketches expire after 3 days)")
    return folder / name


@router.get("/{clean_id}/lines.png")
def lines_png(request: Request, clean_id: str) -> FileResponse:
    return FileResponse(_upload_file(request, clean_id, "lines.png"), media_type="image/png")


@router.get("/{clean_id}/overlay.png")
def overlay_png(request: Request, clean_id: str) -> Response:
    lines = np.asarray(Image.open(_upload_file(request, clean_id, "lines.png")).convert("L"))
    rgba = np.zeros((*lines.shape, 4), np.uint8)
    rgba[..., :3] = 25
    rgba[..., 3] = np.clip(lines.astype(np.uint16) * 2, 0, 255)  # pencil is faint; boost for the preview only
    return Response(content=to_png(rgba), media_type="image/png")

