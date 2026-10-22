from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from gateway.placement import (
    HIP,
    NECK,
    SHOULDER,
    WAIST,
    check_image,
    default_landmarks,
    ink_extent,
    landmarks_from_mask,
    load_mask,
    measure_sketch,
    suggest_placement,
)
from gateway.sketch import CANVAS_H, CANVAS_W, clean_paper, decode_image, place_on_canvas

SAMPLES = Path(__file__).parent / "samples"


def figure_mask(arms_apart: bool = False) -> np.ndarray:
    """Standing figure 55..1170 px tall: head, neck, torso, arms, legs."""
    mask = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    cv2.circle(mask, (416, 110), 55, 1, -1)  # head 55..165
    cv2.rectangle(mask, (396, 160), (436, 230), 1, -1)  # neck
    cv2.rectangle(mask, (316, 230), (516, 640), 1, -1)  # torso, 201 wide at the shoulders
    gap = 12 if arms_apart else 0
    cv2.rectangle(mask, (276 - gap, 240), (315 - gap, 620), 1, -1)  # arms
    cv2.rectangle(mask, (517 + gap, 240), (556 + gap, 620), 1, -1)
    cv2.rectangle(mask, (346, 640), (410, 1170), 1, -1)  # legs
    cv2.rectangle(mask, (422, 640), (486, 1170), 1, -1)
    return mask.astype(bool)


def cleaned(name: str) -> np.ndarray:
    return clean_paper(decode_image((SAMPLES / name).read_bytes())).lines


def synthetic_shirt(shoulder_width: int = 300) -> np.ndarray:
    """Collar, gently sloping shoulders, sleeves flaring out to the elbow, hip-length body."""
    crop = np.zeros((700, 700), np.uint8)
    cx, half = 350, shoulder_width // 2
    pts = [
        (cx - 40, 40), (cx - half, 70), (cx - half - 90, 300), (cx - half - 30, 320), (cx - half + 20, 160),
        (cx - half + 20, 640), (cx + half - 20, 640), (cx + half - 20, 160), (cx + half + 30, 320),
        (cx + half + 90, 300), (cx + half, 70), (cx + 40, 40),
    ]
    cv2.polylines(crop, [np.array(pts, np.int32)], isClosed=False, color=255, thickness=4)
    cv2.line(crop, (cx - 40, 40), (cx, 90), 255, 4)  # collar
    cv2.line(crop, (cx + 40, 40), (cx, 90), 255, 4)
    return crop


# --- body landmarks ------------------------------------------------------------------------------------


def test_landmarks_use_fractions_of_body_height() -> None:
    body = landmarks_from_mask(figure_mask())
    assert (body.top, body.bottom) == (55, 1170)
    assert body.neck == pytest.approx(55 + NECK * 1115)
    assert body.shoulder == pytest.approx(55 + SHOULDER * 1115)
    assert body.waist == pytest.approx(55 + WAIST * 1115)
    assert body.hip == pytest.approx(55 + HIP * 1115)
    assert body.center_x == pytest.approx(416, abs=2)


def test_shoulder_width_is_measured_at_20_percent() -> None:
    # Row 278 crosses torso + arms touching it: 276..556.
    assert landmarks_from_mask(figure_mask()).shoulder_width == pytest.approx(281, abs=2)


def test_waist_width_is_the_torso_when_arms_hang_apart() -> None:
    assert landmarks_from_mask(figure_mask(arms_apart=True)).waist_width == pytest.approx(201, abs=2)
    # Arms touching the torso: fall back to 70% of the shoulders rather than measuring arms too.
    body = landmarks_from_mask(figure_mask())
    assert body.waist_width == pytest.approx(0.7 * body.shoulder_width)


def test_empty_mask_falls_back_to_defaults() -> None:
    assert landmarks_from_mask(np.zeros((CANVAS_H, CANVAS_W), bool)) == default_landmarks()


@pytest.mark.parametrize("variant", ["white_body", "black_body", "alpha"])
def test_load_mask_handles_polarity_and_alpha(tmp_path: Path, variant: str) -> None:
    body = figure_mask()
    if variant == "white_body":
        image = Image.fromarray(body.astype(np.uint8) * 255)
    elif variant == "black_body":
        image = Image.fromarray((~body).astype(np.uint8) * 255)
    else:
        rgba = np.zeros((CANVAS_H, CANVAS_W, 4), np.uint8)
        rgba[..., 3] = body.astype(np.uint8) * 255
        image = Image.fromarray(rgba)
    path = tmp_path / "mask.png"
    image.save(path)
    assert (load_mask(path) == body).all()


# --- sketch measurement --------------------------------------------------------------------------------


def test_measure_finds_shoulders_not_sleeve_span() -> None:
    m = measure_sketch(synthetic_shirt(shoulder_width=300))
    assert m.shoulder_width == pytest.approx(304, rel=0.08)  # 300 + line thickness, not the ~480 sleeve span
    assert m.top == 38 and m.shoulder_cx == pytest.approx(350, abs=3)


def test_measure_on_paper_sample() -> None:
    crop = cleaned("shirt_front_paper.jpeg")
    m = measure_sketch(crop)
    sleeve_span = ink_extent(crop)[2] - ink_extent(crop)[0]
    assert m.shoulder_width < 0.75 * sleeve_span
    assert (m.shoulder_y - m.top) < 0.2 * (m.bottom - m.top)


# --- placement -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("sample", ["shirt_front_paper.jpeg", "shirt_back_paper.jpeg"])
def test_shirt_covers_the_shoulders_after_placement(sample: str) -> None:
    """Regression: a hip-length shirt was shrunk onto the upper chest and rendered as a tiny cape."""
    body = landmarks_from_mask(figure_mask())
    crop = cleaned(sample)
    control = place_on_canvas(crop, suggest_placement(crop, "top", body))
    x0, y0, x1, y1 = ink_extent(control)
    assert x1 - x0 + 1 >= 0.9 * body.shoulder_width
    assert y0 == pytest.approx(body.neck, abs=0.02 * body.height)  # collar at the neck
    # The hem follows the sketch's proportions: this sample is a long shirt-jacket, so hips to upper thigh.
    assert body.hip - 0.05 * body.height <= y1 <= body.hip + 0.15 * body.height


def test_top_placement_matches_shoulder_width_exactly() -> None:
    body = default_landmarks()
    crop = synthetic_shirt(shoulder_width=300)
    placement = suggest_placement(crop, "top", body)
    assert measure_sketch(crop).shoulder_width * placement.scale == pytest.approx(body.shoulder_width)
    control = place_on_canvas(crop, placement)
    x0, _, x1, _ = ink_extent(control)
    assert (x0 + x1) / 2 == pytest.approx(body.center_x, abs=3)


def test_full_length_garment_continues_down_the_body() -> None:
    body = default_landmarks()
    dress = np.zeros((1400, 600), np.uint8)
    cv2.polylines(dress, [np.array([(260, 20), (150, 60), (170, 500), (60, 1350), (540, 1350), (430, 500), (450, 60), (340, 20)], np.int32)], False, 255, 4)
    control = place_on_canvas(dress, suggest_placement(dress, "full", body))
    _, y0, _, y1 = ink_extent(control)
    assert y0 == pytest.approx(body.neck, abs=0.02 * body.height)
    assert y1 > body.at(0.75)  # below the knees


def test_bottom_placement_puts_waistband_at_waist() -> None:
    body = default_landmarks()
    trousers = np.zeros((900, 400), np.uint8)
    cv2.rectangle(trousers, (100, 30), (300, 60), 255, 4)  # waistband 200 wide
    cv2.line(trousers, (100, 60), (80, 880), 255, 4)
    cv2.line(trousers, (300, 60), (320, 880), 255, 4)
    placement = suggest_placement(trousers, "bottom", body)
    control = place_on_canvas(trousers, placement)
    assert ink_extent(control)[1] == pytest.approx(body.waist, abs=2)
    assert 204 * placement.scale == pytest.approx(body.waist_width * 1.05, rel=0.03)


def test_figure_placement_spans_the_body() -> None:
    body = default_landmarks()
    figure = np.zeros((1200, 300), np.uint8)
    cv2.rectangle(figure, (100, 0), (200, 1199), 255, 3)
    control = place_on_canvas(figure, suggest_placement(figure, "figure", body))
    _, y0, _, y1 = ink_extent(control)
    assert y0 == pytest.approx(body.top, abs=2) and y1 == pytest.approx(body.bottom, abs=3)


def test_check_image_draws_lines_and_landmarks(tmp_path: Path) -> None:
    body = landmarks_from_mask(figure_mask())
    control = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    control[400:402, 300:500] = 255
    photo = tmp_path / "photo.png"
    Image.new("RGB", (CANVAS_W, CANVAS_H), (120, 120, 120)).save(photo)
    image = np.asarray(check_image(control, body, photo))
    assert image.shape == (CANVAS_H, CANVAS_W, 3)
    assert tuple(image[401, 400]) == (215, 30, 30)  # sketch in red
    assert image[int(body.shoulder), int(body.center_x)][1] > 100  # green shoulder-width bar
