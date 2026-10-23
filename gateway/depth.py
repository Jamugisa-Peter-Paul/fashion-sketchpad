"""Garment-shaped body depth for on-mannequin renders.

The template depth map is the bare mannequin. Fed to the depth ControlNet as is, it tells Flux "the surface
is exactly here", so wide trousers, flared skirts and loose sleeves get pulled in onto the body (skinny
trousers, bodysuits, sheer veils). The lines ControlNet says the opposite, and the body usually wins.

So before rendering, the area the garment covers is cut out of the depth map:
    fill   the garment's drawn silhouette becomes a smooth solid (body depth inside it, blurred, and a
           little in front of the body where the garment stands away from it). Depth and lines now agree.
    blank  the garment area is set to "nothing here", so only the lines shape the garment.
    off    the raw template depth.
Head, arms and legs the garment does not cover keep the mannequin's depth, so the body still comes through.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from gateway.sketch import CANVAS_H, CANVAS_W

DepthMode = str  # "fill" | "blank" | "off"

OUTLINE = 12  # control values above this count as outline; faint pencil included (see Control.outline)
# Radius (px) of the "ball" rolled in from outside: gaps in the outline narrower than twice this are
# bridged. The shape grows with the ball until the gaps are bridged, then levels off; the smallest ball
# within LEVEL of the largest shape wins, so tidy drawings keep their exact shape and gappy pencil closes.
BALL_RADII = (4, 8, 12, 16, 20, 24, 28, 32, 40)
LEVEL = 0.95
MIN_FILL = 0.5  # a found shape must cover at least this share of the lines' convex hull, else no shape
GROW = 3  # px the region is grown past the lines (half a line's width plus a little)
FEATHER = 1.0  # gaussian sigma of the edge. Keep it crisp: a soft depth edge renders as smoky, sheer fabric
SMOOTH = 18.0  # gaussian sigma that smooths the body's depth inside the garment
BODY = 10  # depth values above this are the mannequin, below are background


def _disk(radius: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))


def _unreachable(ink: np.ndarray, radius: int) -> np.ndarray:
    """Everything a ball of `radius` rolled in from outside the canvas can't reach without touching ink:
    the garment, with gaps in its outline narrower than the ball bridged. Concave corners (armpits, the
    crotch) get rounded by the ball's radius, which is harmless at these sizes."""
    h, w = ink.shape
    free = np.ones((h + 2, w + 2), np.uint8)
    free[1:-1, 1:-1] = (~ink).astype(np.uint8)
    room = cv2.distanceTransform(free, cv2.DIST_L2, 5) > radius
    room[[0, -1], :] = True  # the ball starts anywhere outside the canvas
    room[:, [0, -1]] = True
    room = room.astype(np.uint8)
    cv2.floodFill(room, None, (0, 0), 2)
    reached = cv2.dilate((room == 2).astype(np.uint8), _disk(radius))
    return reached[1:-1, 1:-1] == 0


def _hull(mask: np.ndarray) -> np.ndarray:
    points = np.argwhere(mask)[:, ::-1].astype(np.int32)
    hull = np.zeros(mask.shape, np.uint8)
    cv2.fillConvexPoly(hull, cv2.convexHull(points), 1)
    return hull.astype(bool)


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) of each run of True in a 1-D boolean array, end inclusive."""
    padded = np.concatenate([[False], row, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b) - 1) for a, b in zip(edges[::2], edges[1::2])]


def close_cut_edges(ink: np.ndarray, legs: bool = False) -> np.ndarray:
    """Long garments placed on the mannequin often run off the canvas (a maxi dress past the feet). Their
    outline is then open along that edge, and filling it would leak. Closes it by drawing the edge between
    the outermost lines. With `legs` (trousers, shorts, jumpsuits), the bottom edge is closed per leg, so the
    gap between the legs stays open."""
    ink = ink.copy()
    edges = {"top": ink[0, :], "bottom": ink[-1, :], "left": ink[:, 0], "right": ink[:, -1]}  # views into ink
    for name, edge in edges.items():
        runs = _runs(edge)
        if len(runs) < 2:
            continue
        if legs and name == "bottom" and len(runs) >= 4:
            # The gap between the legs is the one nearest the middle (pleats and seams make more runs).
            middle = (runs[0][0] + runs[-1][1]) / 2
            gap = min(range(len(runs) - 1), key=lambda i: abs((runs[i][1] + runs[i + 1][0]) / 2 - middle))
            edge[runs[0][0] : runs[gap][1] + 1] = True
            edge[runs[gap + 1][0] : runs[-1][1] + 1] = True
        else:
            edge[runs[0][0] : runs[-1][1] + 1] = True
    return ink


def garment_region(lines: np.ndarray, legs: bool = False, threshold: int = OUTLINE) -> np.ndarray:
    """Boolean mask of the area the sketched garment covers on the canvas, or all False if no closed shape
    can be found (the depth is then left as it is: a slightly tight fit beats a smoky blob).

    Edges cut off by the canvas are closed first (for trousers, per leg, so the gap between the legs stays
    open). Then the smallest ball that bridges the outline's gaps decides the shape (see BALL_RADII).
    """
    ink = lines > threshold
    if ink.sum() < 50:
        return np.zeros_like(ink)
    ink = close_cut_edges(cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool), legs)
    hull = int(_hull(ink).sum())
    regions = [_unreachable(ink, radius) for radius in BALL_RADII]
    largest = max(int(r.sum()) for r in regions)
    if largest < MIN_FILL * hull:
        return np.zeros_like(ink)
    return next(r for r in regions if r.sum() >= LEVEL * largest)


def soft_region(lines: np.ndarray, legs: bool = False, grow: int = GROW, feather: float = FEATHER) -> np.ndarray:
    """garment_region grown by `grow` px with a slightly softened edge, as float 0..1."""
    region = garment_region(lines, legs).astype(np.uint8)
    if grow > 0:
        region = cv2.dilate(region, _disk(grow))
    soft = region.astype(np.float32)
    if feather > 0:
        soft = cv2.GaussianBlur(soft, (0, 0), feather)
    return np.clip(soft, 0.0, 1.0)


def load_depth(path: Path) -> np.ndarray:
    image = Image.open(path).convert("L")
    if image.size != (CANVAS_W, CANVAS_H):
        image = image.resize((CANVAS_W, CANVAS_H), Image.Resampling.BILINEAR)
    return np.asarray(image)


def garment_depth(depth: np.ndarray, lines: np.ndarray, mode: DepthMode = "fill", legs: bool = False) -> np.ndarray:
    """The template depth with the garment cut in (see the module docstring). uint8, same shape."""
    if mode == "off":
        return depth.copy()
    d = depth.astype(np.float32)
    mask = soft_region(lines, legs)
    if not mask.any():
        return depth.copy()
    if mode == "blank":
        return np.clip(d * (1 - mask), 0, 255).astype(np.uint8)

    # fill: inside the garment, keep the body's depth where there is body, and put the garment a little in
    # front of the mannequin's typical depth where it stands away from it (flared skirt, wide trouser legs).
    inside = mask > 0.5
    body = d > BODY
    under = d[inside & body]
    level = float(np.median(under)) if under.size else (float(np.median(d[body])) if body.any() else 128.0)
    solid = np.where(body, np.maximum(d, 0.85 * level), 0.85 * level)
    # Normalised blur within the region, so the background outside does not darken the edges.
    weight = inside.astype(np.float32)
    smooth = cv2.GaussianBlur(solid * weight, (0, 0), SMOOTH) / np.maximum(cv2.GaussianBlur(weight, (0, 0), SMOOTH), 1e-3)
    out = d * (1 - mask) + smooth * mask
    return np.clip(out, 0, 255).astype(np.uint8)
