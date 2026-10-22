"""Render queue: one worker, one GPU, jobs run strictly one after another.

Job state lives in each design's design.json (see models.Render), so a restart loses nothing: unfinished
jobs are re-queued at startup, and a view that ComfyUI already finished is fetched instead of re-rendered.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from gateway.catalog import Catalog
from gateway.comfy import ComfyClient, ComfyError
from gateway.config import Settings
from gateway.designs import DesignNotFound, DesignStore
from gateway.models import Design, DesignView, Render, RenderView, View
from gateway.placement import default_landmarks, landmarks_from_mask, load_mask, suggest_placement
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


def control_image(
    folder: Path, view: str, design_view: DesignView, style: StyleOptions, catalog: Catalog, templates_dir: Path
) -> np.ndarray:
    """The 832x1216 white-on-black image fed to the lines ControlNet."""
    crop = np.asarray(Image.open(folder / f"lines_{view}.png").convert("L"))
    if not catalog.scene(style.scene).on_mannequin:
        if design_view.source == "drawn":
            crop = crop_to_content(crop)
        h, w = crop.shape
        return place_on_canvas(crop, product_shot_placement(w, h))
    if design_view.source == "drawn":
        return place_on_canvas(crop, Placement(CANVAS_W / 2, CANVAS_H / 2, 1.0))  # already aligned
    placement = design_view.placement
    if placement is None:
        template = find_view(templates_dir, style.body, view)
        landmarks = landmarks_from_mask(load_mask(template.mask)) if template.mask else default_landmarks()
        p = suggest_placement(design_view.width, design_view.height, catalog.garment(style.garment).placement, landmarks)
        return place_on_canvas(crop, p)
    return place_on_canvas(crop, Placement(placement.cx, placement.cy, placement.scale))


def _find_render(design: Design, job_id: str) -> Render:
    return next(r for r in design.renders if r.id == job_id)


class RenderQueue:
    def __init__(self, store: DesignStore, comfy: ComfyClient, catalog: Catalog, settings: Settings) -> None:
        self.store = store
        self.comfy = comfy
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
        for view, state in render.views.items():
            if state.status in ("queued", "running"):
                await self._render_view(design_id, job_id, view)

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
            control_image, folder, view, design.views[view], style, self.catalog, self.settings.templates_dir
        )
        control_png = to_png(control)
        (folder / f"control_{view}.png").write_bytes(control_png)  # kept for debugging
        lines_name = await self.comfy.upload_image(control_png, f"fashion_{render.id}_{view}.png")

        depth_name = None
        template = find_view(self.settings.templates_dir, style.body, view)
        if self.catalog.scene(style.scene).on_mannequin and template.depth and self.settings.render.depth_strength > 0:
            depth_name = await self.comfy.upload_image(template.depth.read_bytes(), f"fashion_depth_{style.body}_{view}.png")

        prompt = build_prompt(self.catalog, style, view, self.settings.render.view_hint)
        workflow = build_workflow(
            prompt, lines_name, render.seed, self.settings.render, depth_name, filename_prefix=f"fashion/{render.id}_{view}"
        )
        return await self.comfy.queue_prompt(workflow), prompt
