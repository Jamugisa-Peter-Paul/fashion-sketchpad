"""Auto-placement of a cropped paper sketch onto a body template (on-mannequin scenes).

Body landmarks (neck, shoulders, waist, crotch, feet) are measured from the template's `<view>_mask.png`.
The cropped garment is then fitted into a region of the body chosen by the garment's `placement`:
    top    shoulders .. just below the crotch (shirts, jackets, hoodies)
    bottom waist .. feet (trousers, skirts, shorts)
    full   shoulders .. feet (dresses, coats, kaftans)
    figure head .. feet (the sketch itself shows a whole body)
The result is only a starting point: the app lets the user drag/pinch it before generating.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from gateway.sketch import CANVAS_H, CANVAS_W, Placement

PlacementKind = Literal["top", "bottom", "full", "figure"]


@dataclass(frozen=True)
class BodyLandmarks:
    top: float  # top of head
    neck: float
    shoulder: float
    waist: float
    crotch: float
    bottom: float  # soles of the feet
    center_x: float
    shoulder_width: float
    hip_width: float
    body_width: float  # widest row, arms included

    @property
    def height(self) -> float:
        return self.bottom - self.top


def default_landmarks() -> BodyLandmarks:
    """Adult proportions on the 832x1216 canvas, used when a template has no mask."""
    top, bottom = 0.04 * CANVAS_H, 0.97 * CANVAS_H
    height = bottom - top
    return BodyLandmarks(
        top=top,
        neck=top + 0.13 * height,
        shoulder=top + 0.18 * height,
        waist=top + 0.38 * height,
        crotch=top + 0.50 * height,
        bottom=bottom,
        center_x=CANVAS_W / 2,
        shoulder_width=0.25 * height,
        hip_width=0.19 * height,
        body_width=0.30 * height,
    )


def load_mask(path: Path) -> np.ndarray:
    """Body mask as booleans (True = body). Accepts alpha masks and either polarity of grey masks."""
    image = Image.open(path)
    if image.size != (CANVAS_W, CANVAS_H):
        image = image.resize((CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)
    if image.mode in ("RGBA", "LA"):
        alpha = np.asarray(image.getchannel("A"))
        if alpha.min() < 255:
            return alpha > 127
    mask = np.asarray(image.convert("L")) > 127
    # The body never covers most of the canvas; if it seems to, the mask is inverted.
    return ~mask if mask.mean() > 0.5 else mask


def _run_width(row: np.ndarray, x: int) -> int:
    """Width of the contiguous run of True pixels in `row` that contains column x (0 if x is background)."""
    if not row[x]:
        return 0
    left = x
    while left > 0 and row[left - 1]:
        left -= 1
    right = x
    while right < len(row) - 1 and row[right + 1]:
        right += 1
    return right - left + 1


def landmarks_from_mask(mask: np.ndarray) -> BodyLandmarks:
    rows = np.nonzero(mask.any(axis=1))[0]
    cols = np.nonzero(mask.any(axis=0))[0]
    if len(rows) < 50:
        return default_landmarks()
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top
    center_x = int(round(np.nonzero(mask[top + height // 3])[0].mean())) if mask[top + height // 3].any() else int(cols.mean())
    widths = np.array([_run_width(mask[y], center_x) for y in range(mask.shape[0])])

    # Neck: narrowest point below the head (the head is 1/8 of an adult, up to ~1/4 of a toddler).
    lo, hi = top + int(0.08 * height), top + int(0.32 * height)
    neck = lo + int(np.argmin(np.where(widths[lo:hi] > 0, widths[lo:hi], 10_000)))
    neck_width = max(int(widths[neck]), 1)

    # Shoulders: first row below the neck that is clearly wider than it.
    shoulder = next((y for y in range(neck, hi + int(0.1 * height)) if widths[y] >= 2.2 * neck_width), neck + int(0.04 * height))

    # Crotch: top of the gap between the legs, scanning up the centre column from the feet.
    crotch = top + int(0.5 * height)
    y = bottom
    while y > shoulder and not mask[y, center_x]:
        y -= 1
    if bottom - y > 0.2 * height:
        crotch = y

    waist = shoulder + 0.62 * (crotch - shoulder)
    shoulder_row = mask[shoulder]
    shoulder_width = float(np.ptp(np.nonzero(shoulder_row)[0]) + 1) if shoulder_row.any() else 0.25 * height
    hip_width = float(_run_width(mask[int(waist)], center_x)) * 1.25 or 0.19 * height
    return BodyLandmarks(
        top=top,
        neck=neck,
        shoulder=shoulder,
        waist=waist,
        crotch=crotch,
        bottom=bottom,
        center_x=center_x,
        shoulder_width=shoulder_width,
        hip_width=hip_width,
        body_width=float(cols[-1] - cols[0] + 1),
    )


def suggest_placement(crop_w: int, crop_h: int, kind: PlacementKind, body: BodyLandmarks) -> Placement:
    """Fits the crop inside the body region for `kind`, keeping its aspect ratio, anchored at the region top."""
    h = body.height
    if kind == "top":
        y0, y1, width = body.shoulder - 0.04 * h, body.crotch + 0.06 * h, body.shoulder_width * 1.5
    elif kind == "bottom":
        y0, y1, width = body.waist, body.bottom - 0.02 * h, body.hip_width * 1.4
    elif kind == "full":
        y0, y1, width = body.shoulder - 0.04 * h, body.bottom - 0.02 * h, body.shoulder_width * 1.8
    else:  # figure
        y0, y1, width = body.top, body.bottom, body.body_width * 1.1
    scale = min(width / crop_w, (y1 - y0) / crop_h)
    return Placement(cx=body.center_x, cy=y0 + crop_h * scale / 2, scale=scale)
