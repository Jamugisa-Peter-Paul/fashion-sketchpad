"""Render queue: one worker, one GPU, jobs run strictly one after another.

Job state lives in each design's design.json (see models.Render), so a restart loses nothing: unfinished
jobs are re-queued at startup, and a view that ComfyUI already finished is fetched instead of re-rendered.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from gateway.catalog import Catalog
from gateway.comfy import ComfyClient, ComfyError
from gateway.config import Settings
from gateway.depth import garment_depth, load_depth, strip_outline
from gateway.designs import DesignNotFound, DesignStore
from gateway.details import DetailsClient, DetailsError, SketchDetails
from gateway.models import Design, DesignView, Render, RenderView, View
from gateway.placement import BodyLandmarks, check_image, default_landmarks, landmarks_from_mask, load_mask, suggest_placement
from gateway.prompts import StyleOptions, build_prompt
from gateway.sketch import (
    CANVAS_H,
    CANVAS_W,
    Placement,
    SketchError,
    crop_to_content,
    place_on_canvas,
    product_shot_placement,
    to_png,
)
from gateway.templates import find_view
from gateway.workflow import OUTPUT_NODE, build_workflow

log = logging.getLogger(__name__)

SECONDS_PER_VIEW = 60  # observed on the RTX A4000; only used for the progress estimate


@dataclass
class Control:
    image: np.ndarray  # 832x1216 white-on-black lines fed to the lines ControlNet
    body: BodyLandmarks | None  # body it was placed on (None for product shots)
    background: Path | None  # template photo/outline, for the placement check image
    # The same placement with faint pencil kept and lines not thinned: only used to find the garment's
    # outline for the depth map (faint pencil leaves gaps in `image`).
    outline: np.ndarray | None = None


def compose_control(
    folder: Path,
    view: str,
    design_view: DesignView,
    style: StyleOptions,
    catalog: Catalog,
    templates_dir: Path,
    strip: bool = True,
) -> Control:
    crop = np.asarray(Image.open(folder / f"lines_{view}.png").convert("L"))
    if not catalog.scene(style.scene).on_mannequin:
        if design_view.source == "drawn":
            crop = crop_to_content(crop)
        h, w = crop.shape
        return Control(place_on_canvas(crop, product_shot_placement(w, h)), None, None)

    template = find_view(templates_dir, style.body, view)
    body = landmarks_from_mask(load_mask(template.mask)) if template.mask else default_landmarks()
    background = template.photo or template.guide
    if design_view.source == "drawn":
        placement = Placement(CANVAS_W / 2, CANVAS_H / 2, 1.0)  # drawn on the guide: already aligned
    elif design_view.placement is not None:  # the user's placement from the app
        placement = Placement(design_view.placement.cx, design_view.placement.cy, design_view.placement.scale)
    else:
        placement = suggest_placement(crop, catalog.garment(style.garment).placement, body)
    outline = place_on_canvas(crop, placement, stroke_target=None, floor=0)
    lines = place_on_canvas(crop, placement)
    if strip:
        lines = strip_outline(lines, outline, catalog.garment(style.garment).legs)
    return Control(lines, body, background, outline)


def control_files(control: Control) -> tuple[bytes, bytes]:
    """PNG of the control image and of its placement check (lines over the template, with landmarks)."""
    check = io.BytesIO()
    check_image(control.image, control.body, control.background).save(check, format="PNG")
    return to_png(control.image), check.getvalue()


def _find_render(design: Design, job_id: str) -> Render:
    return next(r for r in design.renders if r.id == job_id)


def depth_file(control: Control, depth_path: Path, mode: str, legs: bool = False) -> bytes:
    """The template depth with the garment's silhouette cut in (gateway/depth.py), as PNG."""
    lines = control.outline if control.outline is not None else control.image
    return to_png(garment_depth(load_depth(depth_path), lines, mode, legs))


class RenderQueue:
    def __init__(
        self,
        store: DesignStore,
        comfy: ComfyClient,
        catalog: Catalog,
        settings: Settings,
        details: DetailsClient | None = None,
    ) -> None:
        self.store = store
        self.comfy = comfy
        self.details = details
        self.catalog = catalog
        self.settings = settings
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending: list[str] = []
        self.current: str | None = None
        self.current_view_started: float | None = None
        self._task: asyncio.Task[None] | None = None

    # --- lifecycle -------------------------------------------------------------------------------------

    def start(self) -> None:
        self._recover()
        self._task = asyncio.create_task(self._worker(), name="render-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _recover(self) -> None:
        unfinished = [
            (render.created_at, render.id)
            for design in self.store.all()
            for render in design.renders
            if any(v.status in ("queued", "running") for v in render.views.values())
        ]
        for _, job_id in sorted(unfinished):
            self.enqueue(job_id)
        if unfinished:
            log.info("Re-queued %d unfinished job(s)", len(unfinished))

    # --- queue info --------------------------------------------------------------------------------------

    def enqueue(self, job_id: str) -> None:
        self._pending.append(job_id)
        self._queue.put_nowait(job_id)

    def position(self, job_id: str) -> int | None:
        """0 = running now (or next up), n = n jobs ahead. None = not in the queue (finished)."""
        if job_id == self.current:
            return 0
        if job_id in self._pending:
            return self._pending.index(job_id) + (1 if self.current else 0)
        return None

    def eta_seconds(self, job_id: str) -> int | None:
        if self.position(job_id) is None:
            return None
        ahead: list[str] = []
        if job_id != self.current:
            ahead = ([self.current] if self.current else []) + self._pending[: self._pending.index(job_id)]
        views = sum(self._remaining_views(j) for j in ahead) + self._remaining_views(job_id)
        elapsed = time.time() - self.current_view_started if self.current_view_started else 0
        return max(int(views * SECONDS_PER_VIEW - elapsed), 5)

    def _remaining_views(self, job_id: str) -> int:
        design_id = self.store.design_for_job(job_id)
        try:
            render = _find_render(self.store.load(design_id), job_id) if design_id else None
        except (DesignNotFound, StopIteration):
            return 0
        return sum(1 for v in render.views.values() if v.status in ("queued", "running")) if render else 0

    # --- worker ------------------------------------------------------------------------------------------

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            if job_id in self._pending:
                self._pending.remove(job_id)
            self.current = job_id
            try:
                await self._run(job_id)
            except Exception:  # never let one bad job kill the worker
                log.exception("Job %s crashed", job_id)
            finally:
                self.current = None
                self.current_view_started = None

    async def _run(self, job_id: str) -> None:
        design_id = self.store.design_for_job(job_id)
        if not design_id or not self.store.exists(design_id):
            return  # design deleted while queued
        render = _find_render(self.store.load(design_id), job_id)
        if any(state.status in ("queued", "running") for state in render.views.values()):
            await self._resolve_details(design_id, job_id)
        for view, state in render.views.items():
            if state.status in ("queued", "running"):
                await self._render_view(design_id, job_id, view)

    async def _resolve_details(self, design_id: str, job_id: str) -> None:
        """Pick the construction details for this render, once: the user's chips, else the details already
        read off these sketches, else ask the LLM now. Without any, the render just uses the sketch."""
        design = self.store.load(design_id)
        render = _find_render(design, job_id)
        if render.details is not None:
            return
        details = render.style.details if render.style.details is not None else design.details
        if details is None and self.details is not None and self.details.enabled:
            folder = self.store.folder(design_id)
            sketches = {view: folder / f"sketch_{view}.png" for view in design.views}
            sketches = {view: path for view, path in sketches.items() if path.exists()}
            try:
                details = await self.details.extract(self.catalog.garment(render.style.garment).prompt, sketches)
            except DetailsError as exc:
                log.warning("Job %s: no sketch details (%s)", job_id, exc)
            except Exception:  # details are optional: never let them stop the render
                log.exception("Job %s: reading sketch details crashed", job_id)
        try:
            with self.store.update(design_id) as stored:
                if details is not None and stored.details is None and render.style.details is None:
                    stored.details = details
                _find_render(stored, job_id).details = details or SketchDetails()
        except DesignNotFound:
            pass

    def _set_view(self, design_id: str, job_id: str, view: View, **changes: object) -> None:
        with self.store.update(design_id) as design:
            state = _find_render(design, job_id).views[view]
            for key, value in changes.items():
                setattr(state, key, value)

    async def _render_view(self, design_id: str, job_id: str, view: View) -> None:
        self.current_view_started = time.time()
        try:
            self._set_view(design_id, job_id, view, status="running", started_at=time.time(), error=None)
            design = self.store.load(design_id)
            render = _find_render(design, job_id)
            prompt_id = await self._resume(render.views[view])
            if prompt_id is None:
                prompt_id, prompt = await self._submit(design, render, view)
                self._set_view(design_id, job_id, view, prompt_id=prompt_id, prompt=prompt)
            output = await self.comfy.wait_for_output(
                prompt_id, OUTPUT_NODE, self.settings.render.view_timeout_s, self.settings.render.poll_interval_s
            )
            data = await self.comfy.download(output)
            (self.store.folder(design_id) / f"render_{job_id}_{view}.png").write_bytes(data)
            self._set_view(design_id, job_id, view, status="done", finished_at=time.time())
        except DesignNotFound:
            log.info("Design %s was deleted during job %s", design_id, job_id)
        except (ComfyError, httpx.HTTPError, SketchError, OSError) as exc:
            log.warning("Job %s view %s failed: %s", job_id, view, exc)
            message = str(exc) or exc.__class__.__name__
            if isinstance(exc, httpx.HTTPError):
                message = f"Could not reach ComfyUI ({exc.__class__.__name__})"
            try:
                self._set_view(design_id, job_id, view, status="error", error=message, finished_at=time.time())
            except DesignNotFound:
                pass

    async def _resume(self, state: RenderView) -> str | None:
        """After a restart: keep waiting on a prompt ComfyUI still knows about instead of rendering twice."""
        if state.prompt_id and await self.comfy.knows(state.prompt_id):
            return state.prompt_id
        return None

    async def _submit(self, design: Design, render: Render, view: View) -> tuple[str, str]:
        folder = self.store.folder(design.id)
        style = render.style
        control = await asyncio.to_thread(
            compose_control,
            folder,
            view,
            design.views[view],
            style,
            self.catalog,
            self.settings.templates_dir,
            self.settings.render.strip_outline,
        )
        control_png, check_png = await asyncio.to_thread(control_files, control)
        (folder / f"control_{view}.png").write_bytes(control_png)
        # Placement check for every job: GET /api/jobs/{job}/{view}/check.png
        (folder / f"check_{render.id}_{view}.png").write_bytes(check_png)
        lines_name = await self.comfy.upload_image(control_png, f"fashion_{render.id}_{view}.png")

        depth_name = None
        on_mannequin = self.catalog.scene(style.scene).on_mannequin
        template = find_view(self.settings.templates_dir, style.body, view)
        if on_mannequin and template.depth and self.settings.render.depth_strength > 0:
            legs = self.catalog.garment(style.garment).legs
            depth_png = await asyncio.to_thread(
                depth_file, control, template.depth, self.settings.render.depth_garment, legs
            )
            # GET /api/jobs/{job}/{view}/depth.png
            (folder / f"depth_{render.id}_{view}.png").write_bytes(depth_png)
            depth_name = await self.comfy.upload_image(depth_png, f"fashion_depth_{render.id}_{view}.png")

        prompt = build_prompt(self.catalog, style, view, self.settings.render.view_hint, render.details)
        workflow = build_workflow(
            prompt,
            lines_name,
            render.seed,
            self.settings.render,
            depth_name,
            filename_prefix=f"fashion/{render.id}_{view}",
            source=design.views[view].source,
            on_mannequin=on_mannequin,
        )
        # Exactly what ComfyUI gets, for debugging: GET /api/jobs/{job}/{view}/workflow.json. The file is
        # ComfyUI's API format, so it can also be queued by hand (POST /prompt) to reproduce a render.
        (folder / f"workflow_{render.id}_{view}.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        (folder / f"prompt_{render.id}_{view}.txt").write_text(prompt + "\n", encoding="utf-8")
        return await self.comfy.queue_prompt(workflow), prompt
