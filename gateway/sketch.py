"""Sketch cleaning: turns photographed or drawn sketches into white-lines-on-black ControlNet images.

Paper pipeline (learned the hard way, see docs/ARCHITECTURE.md):
    grayscale -> divide by a heavy blur to flatten paper lighting -> darkness boost -> drop specks
    -> keep only the garment (largest cluster + everything inside its outline) -> crop.
All paper processing runs at a fixed working size so the pixel parameters mean the same thing for every
photo, whatever the phone's resolution.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

CANVAS_W, CANVAS_H = 832, 1216
LINE_FLOOR = 40  # control-image values below this are set to black
# Line width (px) on the 832x1216 control image. Sketches enlarged ~1.5-2x come out 3.5-4 px wide, and Flux
# then copies them literally as piping or white outlines (the bomber jacket). Thicker lines are thinned to this.
STROKE_TARGET = 2.5
WORK_LONG_SIDE = 1216
MAX_SOURCE_PIXELS = 40_000_000

Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


class SketchError(ValueError):
    """The upload can't be turned into a usable sketch."""


@dataclass(frozen=True)
class PaperParams:
    sigma: float = 25.0  # blur used to estimate the paper's lighting
    boost: float = 1.5  # pencil ~1.5; higher thickens lines and the model loses the hem
    offset: float = 25.0  # subtracted after boosting so paper grain goes to black
    min_area: int = 25  # connected components smaller than this (px) are specks
    cluster_gap: int = 8  # marks closer than ~2x this (px) belong to the same cluster
    margin: int = 30  # px of black kept around the cropped garment


@dataclass
class CleanResult:
    lines: np.ndarray  # uint8, white lines on black, cropped to the garment
    bbox: tuple[int, int, int, int]  # crop box (x0, y0, x1, y1) in source-image pixels


# --- loading ---------------------------------------------------------------------------------------------


def decode_image(data: bytes) -> Image.Image:
    """Opens an upload, applies the phone's EXIF rotation and flattens transparency onto white."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, Image.DecompressionBombError) as exc:
        raise SketchError(f"Not a readable image: {exc}") from exc
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        white = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(white, image)
    return image.convert("L")


def _resize_long_side(gray: np.ndarray, long_side: int) -> tuple[np.ndarray, float]:
    h, w = gray.shape
    scale = long_side / max(h, w)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=interp), scale


# --- paper -----------------------------------------------------------------------------------------------


def paper_region(gray: np.ndarray) -> np.ndarray | None:
    """Mask of the sheet of paper when the photo also shows a darker table, hand or pencil.

    Returns None when the image is all paper (scans, digital drawings), so nothing gets masked.
    """
    smooth = cv2.GaussianBlur(gray, (0, 0), 8)
    threshold, bright = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark_mean = smooth[bright == 0].mean() if (bright == 0).any() else 255.0
    bright_mean = smooth[bright > 0].mean() if (bright > 0).any() else 0.0
    dark_fraction = float((bright == 0).mean())
    if bright_mean - dark_mean < 60 or dark_fraction < 0.02:
        return None
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    if count < 2:
        return None
    sheet = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == sheet).astype(np.uint8)
    # Pencil lines inside the sheet are thin enough that the blur above keeps them "bright";
    # close small holes anyway, then shrink away from the sheet edge where the lighting halo lives.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    mask = cv2.erode(mask, np.ones((15, 15), np.uint8))
    return mask.astype(bool)


def paper_ink(gray: np.ndarray, params: PaperParams) -> np.ndarray:
    """Flattens paper lighting and returns ink strength 0..255 (255 = darkest line)."""
    g = gray.astype(np.float32) + 1.0
    background = cv2.GaussianBlur(g, (0, 0), params.sigma)
    normalized = np.clip(g / background, 0.0, 1.0)
    dark = (1.0 - normalized) * 255.0 * params.boost - params.offset
    return np.clip(dark, 0, 255).astype(np.uint8)


def _components(binary: np.ndarray) -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
    return cv2.connectedComponentsWithStats(binary.astype(np.uint8), connectivity=8)


def remove_specks(ink: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = _components(ink > 20)
    small = np.zeros(count, dtype=bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < min_area
    out = ink.copy()
    out[small[labels]] = 0
    return out


def _disk(radius: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))


def garment_mask(ink: np.ndarray, gap: int, sheet: np.ndarray | None = None) -> np.ndarray:
    """Pixels belonging to the garment.

    Marks are grouped into clusters by dilating them `gap` px. The heaviest cluster is the garment's core;
    it then grows by repeatedly adding clusters that are either
      * mostly inside the garment's convex hull (pockets, seams, buttons drawn inside the outline), or
      * near the garment, tall (>= 10% of the garment and >= 6% of the image, so not a line of
        text) and not cut off by the photo
        or paper edge (neighbouring sketches usually are).
    Labels, notes and neighbouring sketches fail both tests and are dropped.
    """
    marks = ink > 20
    if not marks.any():
        raise SketchError("No lines found in the image")
    h, w = ink.shape
    count, labels, stats, _ = _components(cv2.dilate(marks.astype(np.uint8), _disk(gap)))
    weight = np.bincount(labels[marks], weights=ink[marks].astype(np.float64), minlength=count)
    weight[0] = 0
    main = int(np.argmax(weight))

    # Clusters touching the photo border or the edge of the paper sheet.
    outside = np.zeros((h, w), np.uint8) if sheet is None else (~sheet).astype(np.uint8)
    outside[[0, -1], :] = 1
    outside[:, [0, -1]] = 1
    frame = cv2.dilate(outside, _disk(gap)).astype(bool)
    on_frame = np.zeros(count, dtype=bool)
    on_frame[np.unique(labels[frame & (labels > 0)])] = True

    heights = stats[:, cv2.CC_STAT_HEIGHT]
    marks_per_cluster = np.maximum(np.bincount(labels[marks], minlength=count), 1)
    keep = np.zeros(count, dtype=bool)
    keep[main] = True
    for _ in range(6):
        kept_marks = keep[labels] & marks
        hull = cv2.convexHull(np.argwhere(kept_marks)[:, ::-1].astype(np.int32))
        inside = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(inside, hull, 1)
        within = np.bincount(labels[marks & inside.astype(bool)], minlength=count)
        mostly_inside = within >= 0.6 * marks_per_cluster

        kept_height = np.ptp(np.nonzero(kept_marks)[0]) + 1
        near_zone = cv2.dilate(kept_marks.astype(np.uint8), _disk(3 * gap)).astype(bool)
        near = np.zeros(count, dtype=bool)
        near[np.unique(labels[near_zone & (labels > 0)])] = True
        # The absolute floor matters early on, while the core is still small: a 50 px line of
        # handwriting next to a 300 px core would otherwise pass the 10% test.
        min_height = max(0.1 * kept_height, 0.06 * max(h, w))
        structural = near & (heights >= min_height) & ~on_frame

        add = (mostly_inside | structural) & ~keep
        add[0] = False
        if not add.any():
            break
        keep |= add

    result = keep[labels] & marks
    # Re-attach the faint anti-aliased edge of kept strokes.
    return cv2.dilate(result.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def bounding_box(mask: np.ndarray, margin: int = 0) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise SketchError("No lines found in the image")
    h, w = mask.shape
    return (
        max(int(xs.min()) - margin, 0),
        max(int(ys.min()) - margin, 0),
        min(int(xs.max()) + 1 + margin, w),
        min(int(ys.max()) + 1 + margin, h),
    )


def clean_paper(image: Image.Image, params: PaperParams = PaperParams()) -> CleanResult:
    """Paper photo (or any uploaded line art) -> white garment lines on black, cropped to the garment."""
    if image.width * image.height > MAX_SOURCE_PIXELS:
        raise SketchError("Image is too large")
    gray, scale = _resize_long_side(np.asarray(image.convert("L")), WORK_LONG_SIDE)
    ink = paper_ink(gray, params)
    sheet = paper_region(gray)
    if sheet is not None:
        ink[~sheet] = 0
    ink = remove_specks(ink, params.min_area)
    keep = garment_mask(ink, params.cluster_gap, sheet)
    ink[~keep] = 0
    x0, y0, x1, y1 = bounding_box(keep, params.margin)
    source_box = (round(x0 / scale), round(y0 / scale), round(x1 / scale), round(y1 / scale))
    return CleanResult(lines=ink[y0:y1, x0:x1].copy(), bbox=source_box)


# --- drawn in app ----------------------------------------------------------------------------------------


def clean_drawn(image: Image.Image) -> np.ndarray:
    """Black-on-white canvas export -> white-on-black lines, same 832x1216 frame (stays aligned to the guide)."""
    gray = np.asarray(image.convert("L"))
    if gray.shape != (CANVAS_H, CANVAS_W):
        gray = cv2.resize(gray, (CANVAS_W, CANVAS_H), interpolation=cv2.INTER_AREA)
    lines = 255 - gray
    if not (lines > 20).any():
        raise SketchError("The sketch is empty")
    return lines


def crop_to_content(lines: np.ndarray, margin: int = 30) -> np.ndarray:
    x0, y0, x1, y1 = bounding_box(lines > 20, margin)
    return lines[y0:y1, x0:x1].copy()


# --- composing the 832x1216 control image ----------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """Where a cropped sketch goes on the canvas: centre point and scale (canvas px per crop px)."""

    cx: float
    cy: float
    scale: float


def stroke_width(lines: np.ndarray) -> float:
    """Typical line width in px: for thin strokes, area ~ length x width and perimeter ~ 2 x length."""
    ink = (lines > 127).astype(np.uint8)
    area = int(ink.sum())
    if area == 0:
        return 0.0
    edge = int((ink - cv2.erode(ink, np.ones((3, 3), np.uint8))).sum())
    return 2.0 * area / max(edge, 1)


def normalize_strokes(lines: np.ndarray, target: float = STROKE_TARGET) -> np.ndarray:
    """Thins lines wider than `target` by eroding (a 3x3 erosion takes ~2 px off, a 2x2 one ~1 px).
    Never thickens: thin pencil lines are left as they are."""
    excess = stroke_width(lines) - target
    if excess < 0.5:
        return lines
    full = min(int(excess // 2), 4)
    out = cv2.erode(lines, np.ones((3, 3), np.uint8), iterations=full) if full else lines
    if excess - 2 * full >= 0.5:
        out = cv2.erode(out, np.ones((2, 2), np.uint8))
    return out


def place_on_canvas(crop: np.ndarray, placement: Placement, stroke_target: float | None = STROKE_TARGET) -> np.ndarray:
    """Scales the crop and pastes it centred at (cx, cy) on a black canvas; anything off-canvas is clipped.
    Lines wider than `stroke_target` after scaling are thinned (None keeps them as they are)."""
    if placement.scale <= 0:
        raise SketchError("Placement scale must be positive")
    h, w = crop.shape
    new_w, new_h = max(round(w * placement.scale), 1), max(round(h * placement.scale), 1)
    # Linear, not cubic, when enlarging: cubic overshoots and leaves a faint ring around every line.
    interp = cv2.INTER_AREA if placement.scale < 1 else cv2.INTER_LINEAR
    scaled = cv2.resize(crop, (new_w, new_h), interpolation=interp)
    if stroke_target is not None:
        scaled = normalize_strokes(scaled, stroke_target)
    # Only clear lines reach the ControlNet: faint grey (paper texture, soft pencil edges) is dropped.
    scaled[scaled < LINE_FLOOR] = 0

    canvas = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    left, top = round(placement.cx - new_w / 2), round(placement.cy - new_h / 2)
    cx0, cy0 = max(left, 0), max(top, 0)
    cx1, cy1 = min(left + new_w, CANVAS_W), min(top + new_h, CANVAS_H)
    if cx1 <= cx0 or cy1 <= cy0:
        raise SketchError("The sketch was placed entirely off the canvas")
    canvas[cy0:cy1, cx0:cx1] = scaled[cy0 - top : cy1 - top, cx0 - left : cx1 - left]
    return canvas


def product_shot_placement(crop_w: int, crop_h: int, fill: float = 0.94) -> Placement:
    """Scale the garment to fill ~94% of the canvas. Without this the model invents a mannequin and
    extends the garment below the drawn hem."""
    scale = min(CANVAS_W * fill / crop_w, CANVAS_H * fill / crop_h)
    return Placement(cx=CANVAS_W / 2, cy=CANVAS_H / 2, scale=scale)


# --- encoding --------------------------------------------------------------------------------------------


def to_png(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()
