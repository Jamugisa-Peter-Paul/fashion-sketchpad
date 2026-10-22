from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from gateway.placement import default_landmarks, landmarks_from_mask, load_mask, suggest_placement
from gateway.sketch import CANVAS_H, CANVAS_W


def figure_mask() -> np.ndarray:
    """Simple standing figure: head, neck, torso with arms, two legs with a gap from y=640."""
    mask = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    cv2.circle(mask, (416, 110), 55, 1, -1)  # head 55..165
    cv2.rectangle(mask, (396, 160), (436, 200), 1, -1)  # neck
    cv2.rectangle(mask, (306, 200), (526, 640), 1, -1)  # torso + arms, 220 wide
    cv2.rectangle(mask, (346, 640), (410, 1170), 1, -1)  # left leg
    cv2.rectangle(mask, (422, 640), (486, 1170), 1, -1)  # right leg
    return mask.astype(bool)


def test_landmarks_from_simple_figure() -> None:
    body = landmarks_from_mask(figure_mask())
    assert body.top == 55 and body.bottom == 1170
    assert 160 <= body.neck <= 200
    assert 198 <= body.shoulder <= 204
    assert 635 <= body.crotch <= 645
    assert body.shoulder < body.waist < body.crotch
    assert body.shoulder_width == pytest.approx(221, abs=2)
    assert body.center_x == pytest.approx(416, abs=2)


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


def test_top_placement_starts_near_shoulders_and_fits_width() -> None:
    body = landmarks_from_mask(figure_mask())
    placement = suggest_placement(600, 650, "top", body)
    top_edge = placement.cy - 650 * placement.scale / 2
    assert top_edge == pytest.approx(body.shoulder - 0.04 * body.height, abs=1)
    assert 600 * placement.scale <= body.shoulder_width * 1.5 + 1
    assert placement.cx == body.center_x


def test_bottom_placement_starts_at_waist() -> None:
    body = default_landmarks()
    placement = suggest_placement(300, 900, "bottom", body)
    assert placement.cy - 900 * placement.scale / 2 == pytest.approx(body.waist, abs=1)


def test_figure_placement_spans_the_body() -> None:
    body = default_landmarks()
    placement = suggest_placement(300, 1200, "figure", body)
    assert 1200 * placement.scale == pytest.approx(body.height, rel=0.01)
