"""Pydantic models for designs, render jobs and the generate request. Designs are saved as JSON."""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

from gateway.prompts import StyleOptions

View = Literal["front", "back", "side"]
ViewStatus = Literal["queued", "running", "done", "error"]
Source = Literal["paper", "drawn"]


class PlacementModel(BaseModel):
    cx: float
    cy: float
    scale: float = Field(gt=0)


class DesignView(BaseModel):
    """One sketched view of a design. Files: sketch_<view>.png, lines_<view>.png in the design folder."""

    source: Source
    placement: PlacementModel | None = None  # on-mannequin placement of the lines crop
    width: int
    height: int


class RenderView(BaseModel):
    status: ViewStatus = "queued"
    error: str | None = None
    prompt: str = ""
    prompt_id: str | None = None  # ComfyUI's id, so a restart can pick up a finished render
    started_at: float | None = None
    finished_at: float | None = None


class Render(BaseModel):
    """One generate call (a job): every sketched view rendered with the same seed and style."""

    id: str
    seed: int
    style: StyleOptions
    views: dict[View, RenderView]
    created_at: float = Field(default_factory=time.time)

    @property
    def status(self) -> ViewStatus:
        states = {v.status for v in self.views.values()}
        if "running" in states:
            return "running"
        if "queued" in states:
            return "running" if states & {"done", "error"} else "queued"
        return "error" if states == {"error"} else "done"


class Design(BaseModel):
    id: str
    title: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    style: StyleOptions  # latest choices
    views: dict[View, DesignView] = {}
    renders: list[Render] = []


class ViewInput(BaseModel):
    clean_id: str
    placement: PlacementModel | None = None  # omitted: use the placement suggested by /api/sketch/clean


class GenerateRequest(BaseModel):
    """New design: `views` is required. Existing design (`design_id`): `views` replaces only those views.

    New variation = same style, no seed. Change colour = new style, seed of the render being changed.
    """

    design_id: str | None = None
    title: str | None = Field(default=None, max_length=80)
    style: StyleOptions
    views: dict[View, ViewInput] = {}
    seed: int | None = Field(default=None, ge=0, lt=2**31)


class GenerateResponse(BaseModel):
    job_id: str
    design_id: str


class JobViewStatus(BaseModel):
    status: ViewStatus
    error: str | None = None
    image_url: str | None = None


class JobStatus(BaseModel):
    id: str
    design_id: str
    status: ViewStatus
    seed: int
    position: int | None  # jobs ahead of this one in the queue (0 = next / running)
    eta_seconds: int | None
    views: dict[View, JobViewStatus]


class DesignSummary(BaseModel):
    id: str
    title: str
    garment: str
    body: str
    updated_at: float
    render_count: int
    thumbnail_url: str | None
