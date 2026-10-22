"""Auto-placement of a cropped paper sketch onto a body template (on-mannequin scenes).

The template body is measured from `<view>_mask.png` at fixed fractions of its height (adult proportions):
    neck 16%, shoulders 20%, waist 38%, hips 50%
The sketch is measured too: where its collar starts and how wide its shoulders are. Then, by garment
`placement`:
    top, full  shoulder width = body shoulder width, collar at the neck. The sketch's own proportions then
               carry the hem down: hip-length shirts end at the hips, dresses and coats further down.
    bottom     waistband width = body waist width (+5% ease), waistband at the waist.
    figure     the sketch shows a whole body: head to feet onto the template's head to feet.
The result is a starting point: the app lets the user drag/pinch it before generating.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

from gateway.sketch import CANVAS_H, CANVAS_W, Placement, SketchError

PlacementKind = Literal["top", "bottom", "full", "figure"]

# Landmarks as a fraction of body height from the top of the head.
NECK, SHOULDER, WAIST, HIP = 0.16, 0.20, 0.38, 0.50
BOTTOM_EASE = 1.05  # trousers and skirts sit slightly wider than the body at the waist
INK = 20


@dataclass(frozen=True)
class BodyLandmarks:
    top: float  # top of the head
    bottom: float  # soles of the feet
    center_x: float
    shoulder_width: float
    waist_width: float
    body_width: float  # widest row, arms included

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def at(self, fraction: float) -> float:
        return self.top + fraction * self.height

    @property
    def neck(self) -> float:
        return self.at(NECK)

    @property
    def shoulder(self) -> float:
        return self.at(SHOULDER)

    @property
    def waist(self) -> float:
        return self.at(WAIST)

    @property
    def hip(self) -> float:
        return self.at(HIP)


def default_landmarks() -> BodyLandmarks:
    """Adult proportions on the 832x1216 canvas, used when a template has no mask."""
    top, bottom = 0.04 * CANVAS_H, 0.97 * CANVAS_H
    height = bottom - top
    return BodyLandmarks(
        top=top,
        bottom=bottom,
        center_x=CANVAS_W / 2,
        shoulder_width=0.25 * height,
        waist_width=0.17 * height,
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
    row_at = lambda fraction: top + int(round(fraction * height))  # noqa: E731

    # Shoulder width: full extent of the body over a few rows around 20% (median, to ignore stray pixels).
    extents = []
    for y in range(row_at(SHOULDER - 0.01), row_at(SHOULDER + 0.01) + 1):
        xs = np.nonzero(mask[y])[0]
        if len(xs):
            extents.append(xs[-1] - xs[0] + 1)
    shoulder_width = float(np.median(extents)) if extents else 0.25 * height

    torso = np.nonzero(mask[row_at(SHOULDER) : row_at(HIP)])[1]
    center_x = float(np.median(torso)) if len(torso) else float(cols.mean())

    # Waist: the torso's own width; if the arms touch it there, fall back to a typical ratio.
    waist_width = float(_run_width(mask[row_at(WAIST)], int(round(center_x))))
    if not 0 < waist_width <= 0.9 * shoulder_width:
        waist_width = 0.7 * shoulder_width

    return BodyLandmarks(
        top=top,
        bottom=bottom,
        center_x=center_x,
        shoulder_width=shoulder_width,
        waist_width=waist_width,
        body_width=float(cols[-1] - cols[0] + 1),
    )


@dataclass(frozen=True)
class SketchMeasure:
    """Measurements of a cleaned sketch crop, in crop pixels."""

    top: int  # first row with ink (collar / waistband)
    bottom: int  # last row with ink (hem)
    shoulder_y: int
    shoulder_width: float
    shoulder_cx: float
    top_width: float  # width of the first few rows (a waistband, for bottoms)
    top_cx: float
    center_x: float  # middle of the ink


def measure_sketch(crop: np.ndarray) -> SketchMeasure:
    """Finds the sketch's shoulder line: going down from the collar, the garment widens quickly along the
    shoulder seams and then slowly along the sleeves. The shoulder is where the fast widening stops."""
    ink = crop > INK
    rows = np.nonzero(ink.any(axis=1))[0]
    cols = np.nonzero(ink.any(axis=0))[0]
    if len(rows) == 0:
        raise SketchError("No lines found in the sketch")
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1

    lefts = np.full(height, np.inf)
    rights = np.full(height, -np.inf)
    ys, xs = np.nonzero(ink[top : bottom + 1])
    np.minimum.at(lefts, ys, xs)
    np.maximum.at(rights, ys, xs)
    # Outermost ink so far on each side, row by row (never moves inward, so gaps between strokes don't
    # matter). Each side is followed separately: sketches are often drawn slightly tilted.
    left_run = np.minimum.accumulate(lefts)
    right_run = np.maximum.accumulate(rights)

    head = ink[top : top + max(3, round(0.03 * height))]
    head_cols = np.nonzero(head.any(axis=0))[0]
    top_cx = (head_cols[0] + head_cols[-1]) / 2
    window = max(3, round(0.02 * height))
    limit = min(max(int(0.35 * height), window + 1), height - window)
    # Skip past the collar, which is narrow but also has near-vertical sides.
    min_reach = 0.175 * (cols[-1] - cols[0] + 1)

    def knee(reach: np.ndarray) -> int:
        """First row where this side stops moving outwards quickly (shoulder seam -> sleeve)."""
        for i in range(limit):
            if reach[i] >= min_reach and (reach[i + window] - reach[i]) / window < 0.6:
                return i
        return limit

    left_i = knee(top_cx - left_run)
    right_i = knee(right_run - top_cx)
    shoulder_left, shoulder_right = float(left_run[left_i]), float(right_run[right_i])
    return SketchMeasure(
        top=top,
        bottom=bottom,
        shoulder_y=top + max(left_i, right_i),
        shoulder_width=shoulder_right - shoulder_left + 1,
        shoulder_cx=(shoulder_left + shoulder_right) / 2,
        top_width=float(head_cols[-1] - head_cols[0] + 1),
        top_cx=top_cx,
        center_x=(cols[0] + cols[-1]) / 2,
    )


def suggest_placement(crop: np.ndarray, kind: PlacementKind, body: BodyLandmarks) -> Placement:
    """Scale and position for the crop so it sits on the body as described in the module docstring."""
    m = measure_sketch(crop)
    if kind in ("top", "full"):
        scale = body.shoulder_width / m.shoulder_width
        anchor_crop, anchor_body = (m.shoulder_cx, m.top), (body.center_x, body.neck)
    elif kind == "bottom":
        scale = body.waist_width * BOTTOM_EASE / m.top_width
        anchor_crop, anchor_body = (m.top_cx, m.top), (body.center_x, body.waist)
    else:  # figure
        scale = body.height / (m.bottom - m.top + 1)
        anchor_crop, anchor_body = (m.center_x, m.top), (body.center_x, body.top)
    scale = min(max(scale, 0.05), 4.0)
    h, w = crop.shape
    return Placement(
        cx=anchor_body[0] + (w / 2 - anchor_crop[0]) * scale,
        cy=anchor_body[1] + (h / 2 - anchor_crop[1]) * scale,
        scale=scale,
    )


def check_image(control: np.ndarray, body: BodyLandmarks | None, background: Path | None = None) -> Image.Image:
    """Debug view of a placement: the control lines (red) over the template photo or outline, with the
    body landmarks the placement aimed for (neck, shoulders + shoulder width, waist, hips)."""
    if background is not None and background.exists():
        base = Image.open(background).convert("RGBA").resize((CANVAS_W, CANVAS_H))
        canvas = Image.alpha_composite(Image.new("RGBA", base.size, (255, 255, 255, 255)), base).convert("RGB")
        canvas = Image.blend(canvas, Image.new("RGB", canvas.size, (255, 255, 255)), 0.45)
    else:
        canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))

    lines = np.clip(control.astype(np.float32) * 2 / 255, 0, 1)[..., None]
    pixels = np.asarray(canvas, np.float32) * (1 - lines) + np.array([215, 30, 30], np.float32) * lines
    canvas = Image.fromarray(pixels.astype(np.uint8))

    if body is not None:
        draw = ImageDraw.Draw(canvas)
        for name, y in (("neck", body.neck), ("shoulders", body.shoulder), ("waist", body.waist), ("hips", body.hip)):
            for x in range(0, CANVAS_W, 16):
                draw.line([(x, y), (x + 8, y)], fill=(30, 90, 200), width=2)
            draw.text((6, y - 14), name, fill=(30, 90, 200))
        half = body.shoulder_width / 2
        y = body.shoulder
        draw.line([(body.center_x - half, y), (body.center_x + half, y)], fill=(20, 150, 70), width=4)
        for x in (body.center_x - half, body.center_x + half):
            draw.line([(x, y - 10), (x, y + 10)], fill=(20, 150, 70), width=4)
    return canvas


def ink_extent(control: np.ndarray) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the ink in a placed control image; used by tests and the CLI."""
    ys, xs = np.nonzero(control > INK)
    if len(xs) == 0:
        raise SketchError("Nothing on the canvas")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

