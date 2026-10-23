"""Regression set: the 10 test garments (front + back) from samples/garments/.

Each one is cleaned, placed (product shot and on the mannequin) and turned into a garment-shaped depth map,
checking the things that went wrong in real renders: lines too thick (copied as white piping), garments
pulled onto the body (depth fighting the lines), one-piece garments split from behind, hoods placed as
shoulders. Run `python -m gateway.tools.regression` against a live gateway to render them all.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from gateway.catalog import load_catalog
from gateway.depth import BODY, close_cut_edges, garment_depth, garment_region
from gateway.placement import default_landmarks, measure_sketch, suggest_placement
from gateway.prompts import StyleOptions, build_prompt
from gateway.sketch import CANVAS_H, CANVAS_W, LINE_FLOOR, clean_paper, place_on_canvas, product_shot_placement, stroke_width
from gateway.tests.mannequin import mannequin_depth
from gateway.tools.regression import GARMENTS, GARMENTS_DIR

CATALOG = load_catalog()

SAMPLES = [(stem, view) for stem in GARMENTS for view in ("front", "back")]
IDS = [f"{stem}_{view}" for stem, view in SAMPLES]


def cleaned(stem: str, view: str) -> np.ndarray:
    return clean_paper(Image.open(GARMENTS_DIR / f"{stem}_{view}.png")).lines


def on_mannequin(stem: str, view: str) -> np.ndarray:
    crop = cleaned(stem, view)
    garment = CATALOG.garment(GARMENTS[stem])
    return place_on_canvas(crop, suggest_placement(crop, garment.placement, default_landmarks()))


def test_all_samples_are_present() -> None:
    assert sorted(p.name for p in GARMENTS_DIR.glob("*.png")) == sorted(f"{s}_{v}.png" for s, v in SAMPLES)


@pytest.mark.parametrize(("stem", "view"), SAMPLES, ids=IDS)
def test_product_shot_lines_are_thin_and_fill_the_frame(stem: str, view: str) -> None:
    crop = cleaned(stem, view)
    h, w = crop.shape
    control = place_on_canvas(crop, product_shot_placement(w, h))
    ys, xs = np.nonzero(control > LINE_FLOOR)
    fill = max((xs.max() - xs.min()) / CANVAS_W, (ys.max() - ys.min()) / CANVAS_H)
    assert fill > 0.8  # 94% of the frame, less the crop's margin
    # Enlarged pencil lines are thinned back (the bomber's lines came out as white piping at ~3.5 px).
    assert stroke_width(control) < 3.3
    # ...but never erased: the garment keeps most of its lines.
    raw = place_on_canvas(crop, product_shot_placement(w, h), stroke_target=None)
    assert (control > LINE_FLOOR).sum() > 0.5 * (raw > LINE_FLOOR).sum()


@pytest.mark.parametrize(("stem", "view"), SAMPLES, ids=IDS)
def test_garment_region_is_the_filled_silhouette(stem: str, view: str) -> None:
    lines = on_mannequin(stem, view)
    legs = CATALOG.garment(GARMENTS[stem]).legs
    region = garment_region(lines, legs)
    ink = lines > LINE_FLOOR
    ys, xs = np.nonzero(ink)
    box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    # Filled, not just the outline: a garment covers a good part of its bounding box.
    assert region.sum() > 0.35 * box
    assert region[ink].mean() > 0.9


@pytest.mark.parametrize("stem", ["06_belted_jumpsuit", "08_cargo_shorts"])
def test_gap_between_the_legs_stays_open(stem: str) -> None:
    lines = on_mannequin(stem, "front")
    region = garment_region(lines, legs=True)
    ys, xs = np.nonzero(lines > LINE_FLOOR)
    bottom = ys.max() - 2
    middle = int(round((xs[ys >= bottom - 10].min() + xs[ys >= bottom - 10].max()) / 2))
    assert not region[bottom, middle - 2 : middle + 3].any()


def test_cut_edges_are_closed_per_leg() -> None:
    ink = np.zeros((10, 40), bool)
    ink[:, [2, 8, 17, 22, 30, 37]] = True  # left leg: outseam, pleat, inseam | right leg: inseam, pleat, outseam
    closed = close_cut_edges(ink, legs=True)[-1]
    assert closed[2:18].all() and closed[22:38].all() and not closed[18:22].any()
    assert close_cut_edges(ink)[-1, 2:38].all()  # no legs: closed straight across
    assert close_cut_edges(ink, legs=True)[0, 2:38].all()  # only the bottom edge is split


@pytest.mark.parametrize(("stem", "view"), SAMPLES, ids=IDS)
def test_garment_depth_is_solid_under_the_garment(stem: str, view: str) -> None:
    """The bug: the raw body depth said 'background' wherever a wide garment stands off the body, so
    trousers came out skinny and skirts as bodysuits. Inside the garment the depth must now be solid."""
    depth = mannequin_depth()
    lines = on_mannequin(stem, view)
    legs = CATALOG.garment(GARMENTS[stem]).legs
    region = garment_region(lines, legs)
    filled = garment_depth(depth, lines, "fill", legs)
    assert (filled[region] > BODY).mean() > 0.97
    # The mannequin below the garment (bare legs) is untouched.
    hem = int(np.nonzero((lines > LINE_FLOOR).any(axis=1))[0].max())
    below = hem + 40
    if below < CANVAS_H:
        assert np.array_equal(filled[below:], depth[below:])

    blank = garment_depth(depth, lines, "blank", legs)
    assert blank[region].max() < 40
    assert np.array_equal(garment_depth(depth, lines, "off", legs), depth)


def test_hood_is_not_mistaken_for_the_shoulders() -> None:
    hood = measure_sketch(cleaned("04_hoodie", "front"))
    shirt = measure_sketch(cleaned("02_short_sleeve_shirt", "front"))
    assert hood.hood and not shirt.hood
    body = default_landmarks()
    lines = on_mannequin("04_hoodie", "front")
    xs = np.nonzero((lines > LINE_FLOOR).any(axis=0))[0]
    # Sleeves hang by the body, so the whole hoodie is about the body's width, not twice it.
    assert xs.max() - xs.min() < 1.5 * body.shoulder_width
    # The hood goes up around the head.
    ys = np.nonzero((lines > LINE_FLOOR).any(axis=1))[0]
    assert ys.min() < body.neck - 0.04 * body.height


@pytest.mark.parametrize("stem", ["06_belted_jumpsuit", "01_aline_dress", "09_wrap_maxi_dress", "07_kaftan"])
def test_one_piece_garments_are_one_piece_from_behind(stem: str) -> None:
    style = StyleOptions(garment=GARMENTS[stem], body="female_slim")
    back = build_prompt(CATALOG, style, "back")
    assert "one-piece" in back and "one continuous" in back


@pytest.mark.parametrize("sample", ["shirt_front_paper.jpeg", "shirt_back_paper.jpeg"])
def test_faint_pencil_outline_still_closes(sample: str) -> None:
    """Real pencil: after cleaning, the outline is broken into dashes (hem, sleeve edges). The garment shape
    must still come out whole, not a convex-hull blob (rendered as smoke around the arms) or fragments."""
    from gateway.depth import _hull

    crop = clean_paper(Image.open(GARMENTS_DIR.parent / sample)).lines
    placement = suggest_placement(crop, "top", default_landmarks())
    outline = place_on_canvas(crop, placement, stroke_target=None, floor=0)
    region = garment_region(outline)
    hull = _hull(outline > 12)
    assert region.sum() > 0.85 * hull.sum()
    # Crisp edge: the depth jumps from body/garment to background within a few pixels.
    depth = garment_depth(mannequin_depth(), outline, "fill")
    row = depth[int(region.nonzero()[0].mean())]
    edge = np.nonzero(row > BODY)[0][0]
    assert row[edge + 3] > 100


def test_no_closed_shape_leaves_the_depth_alone() -> None:
    lines = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    for x in range(150, 700, 150):  # scattered dashes, far apart: no outline
        lines[300:330, x : x + 3] = 255
    depth = mannequin_depth()
    assert not garment_region(lines).any()
    assert np.array_equal(garment_depth(depth, lines, "fill"), depth)
