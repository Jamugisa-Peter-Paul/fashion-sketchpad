from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from gateway.sketch import (
    CANVAS_H,
    CANVAS_W,
    WORK_LONG_SIDE,
    CleanResult,
    Placement,
    SketchError,
    clean_drawn,
    clean_paper,
    crop_to_content,
    decode_image,
    place_on_canvas,
    product_shot_placement,
    to_png,
)

SAMPLES = Path(__file__).parent / "samples"


def ink_in_source_region(result: CleanResult, source_size: tuple[int, int], region: tuple[int, int, int, int]) -> int:
    """Max ink kept inside `region` (x0, y0, x1, y1 in source pixels)."""
    scale = WORK_LONG_SIDE / max(source_size)
    bx0, by0 = (round(v * scale) for v in result.bbox[:2])
    x0, y0, x1, y1 = (round(v * scale) for v in region)
    window = result.lines[max(y0 - by0, 0) : max(y1 - by0, 0), max(x0 - bx0, 0) : max(x1 - bx0, 0)]
    return int(window.max()) if window.size else 0


def synthetic_paper(with_table: bool = False) -> Image.Image:
    """Uneven paper lighting, a garment with a pocket well inside it, a label, specks and a cut-off neighbour."""
    h, w = 1000, 800
    img = np.linspace(150, 235, w)[None, :].repeat(h, axis=0).astype(np.uint8)
    dark = 70
    cv2.rectangle(img, (250, 300), (550, 800), dark, 3)  # garment outline
    cv2.rectangle(img, (330, 550), (420, 650), dark, 3)  # pocket, 80 px inside the outline
    cv2.putText(img, "Version 2", (240, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.9, dark, 2)  # label above
    cv2.rectangle(img, (760, 200), (820, 700), dark, 3)  # neighbouring sketch cut off by the edge
    rng = np.random.default_rng(0)
    for x, y in rng.integers(20, 780, size=(40, 2)):
        if not (230 < x < 570 and 230 < y < 820):
            img[y : y + 2, x : x + 2] = dark  # specks
    if with_table:
        img[:, :90] = 35  # table showing at the left
        img[:60, :] = 35
    return Image.fromarray(img)


def test_synthetic_paper_keeps_garment_and_pocket_only() -> None:
    image = synthetic_paper()
    result = clean_paper(image)
    x0, y0, x1, y1 = result.bbox
    # Garment spans 250..550 x 300..800; the crop adds a 30 px (working size) margin.
    assert 210 <= x0 <= 250 and 560 <= x1 <= 590
    assert 260 <= y0 <= 300 and 800 <= y1 <= 840
    assert ink_in_source_region(result, image.size, (325, 590, 336, 610)) > 50  # pocket left edge (x=330) kept
    assert ink_in_source_region(result, image.size, (230, 225, 420, 262)) == 0  # label dropped


def test_synthetic_paper_with_table_ignores_table_edge() -> None:
    image = synthetic_paper(with_table=True)
    result = clean_paper(image)
    x0, y0, _, _ = result.bbox
    assert x0 >= 200 and y0 >= 250


def test_paper_samples_produce_lines() -> None:
    for path in sorted(SAMPLES.glob("*.jp*g")):
        result = clean_paper(decode_image(path.read_bytes()))
        assert result.lines.dtype == np.uint8
        assert (result.lines > 20).mean() > 0.005, path.name


def test_front_sample_drops_label_and_note() -> None:
    image = decode_image((SAMPLES / "shirt_front_paper.jpeg").read_bytes())
    result = clean_paper(image)
    # "Collar-Version" label sits just above-left of the collar; the "N:B design" note bottom-right.
    assert ink_in_source_region(result, image.size, (110, 280, 300, 325)) == 0
    assert ink_in_source_region(result, image.size, (610, 945, 762, 1016)) == 0
    # Both cuffs are part of the garment.
    assert result.bbox[0] <= 130 and result.bbox[2] >= 712


def test_back_sample_drops_neighbour_and_note_box() -> None:
    image = decode_image((SAMPLES / "shirt_back_paper.jpeg").read_bytes())
    result = clean_paper(image)
    assert ink_in_source_region(result, image.size, (0, 800, 120, 1016)) == 0  # note box
    assert ink_in_source_region(result, image.size, (0, 250, 20, 540)) == 0  # neighbouring sketch


def test_hoodie_sample_drops_handwritten_label() -> None:
    result = clean_paper(decode_image((SAMPLES / "hoodie.jpeg").read_bytes()))
    assert result.bbox[0] > 55  # "girl" is written in the top-left corner


def test_blank_page_raises() -> None:
    with pytest.raises(SketchError):
        clean_paper(Image.new("L", (600, 800), 230))


def test_decode_rejects_garbage_and_flattens_alpha() -> None:
    with pytest.raises(SketchError):
        decode_image(b"not an image")
    rgba = np.zeros((10, 10, 4), np.uint8)  # fully transparent -> white
    assert np.asarray(decode_image(to_png(rgba))).min() == 255


def test_clean_drawn_inverts_and_keeps_alignment() -> None:
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    array = np.asarray(canvas).copy()
    array[100:110, 200:600] = 0
    lines = clean_drawn(Image.fromarray(array))
    assert lines.shape == (CANVAS_H, CANVAS_W)
    assert lines[105, 300] == 255 and lines[500, 500] == 0
    with pytest.raises(SketchError):
        clean_drawn(Image.new("L", (CANVAS_W, CANVAS_H), 255))


def test_crop_to_content_adds_margin() -> None:
    lines = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    lines[400:500, 300:400] = 255
    assert crop_to_content(lines, margin=30).shape == (160, 160)


def test_product_shot_fills_94_percent() -> None:
    crop = np.full((400, 200), 255, np.uint8)
    placement = product_shot_placement(200, 400)
    canvas = place_on_canvas(crop, placement)
    ys, xs = np.nonzero(canvas)
    assert ys.max() - ys.min() + 1 == pytest.approx(0.94 * CANVAS_H, abs=2)
    assert (xs.min() + xs.max()) / 2 == pytest.approx(CANVAS_W / 2, abs=1)


def test_place_on_canvas_clips_off_canvas_parts() -> None:
    crop = np.full((100, 100), 255, np.uint8)
    canvas = place_on_canvas(crop, Placement(cx=0, cy=0, scale=1.0))
    assert canvas.shape == (CANVAS_H, CANVAS_W)
    assert canvas[:50, :50].all() and not canvas[60:, 60:].any()
    with pytest.raises(SketchError):
        place_on_canvas(crop, Placement(cx=-500, cy=-500, scale=1.0))


def test_place_on_canvas_keeps_lines_crisp() -> None:
    """Enlarging must not ring (cubic overshoot) and faint grey must not reach the ControlNet."""
    crop = np.zeros((60, 60), np.uint8)
    crop[28:32, 10:50] = 255  # a line
    crop[5:8, 5:55] = 25  # faint paper texture
    canvas = place_on_canvas(crop, Placement(cx=416, cy=608, scale=4.0))
    values = np.unique(canvas)
    assert values.min() == 0 and values.max() == 255
    assert not ((canvas > 0) & (canvas < 40)).any()
    ys, _ = np.nonzero(canvas)
    assert ys.min() > 608 - 120 + 5 * 4  # the faint strip at the top was dropped
