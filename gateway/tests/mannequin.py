"""A synthetic mannequin depth map + mask for tests (the real templates live on the server)."""

from __future__ import annotations

import cv2
import numpy as np

from gateway.placement import default_landmarks
from gateway.sketch import CANVAS_H, CANVAS_W


def mannequin_depth() -> np.ndarray:
    """Standing figure in the default landmark proportions: head, torso, arms down, two legs. Brighter = nearer."""
    body = default_landmarks()
    depth = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    cx, top, h = int(body.center_x), body.top, body.height
    y = lambda f: int(top + f * h)  # noqa: E731
    half_shoulder, half_waist = int(body.shoulder_width / 2), int(body.waist_width / 2)
    cv2.ellipse(depth, (cx, y(0.07)), (int(0.045 * h), int(0.065 * h)), 0, 0, 360, 200, -1)  # head
    cv2.rectangle(depth, (cx - 18, y(0.12)), (cx + 18, y(0.17)), 190, -1)  # neck
    torso = np.array(
        [
            (cx - half_shoulder, y(0.19)), (cx + half_shoulder, y(0.19)), (cx + half_waist, y(0.38)),
            (cx + half_waist + 25, y(0.50)), (cx - half_waist - 25, y(0.50)), (cx - half_waist, y(0.38)),
        ],
        np.int32,
    )
    cv2.fillPoly(depth, [torso], 220)
    for side in (-1, 1):
        shoulder = cx + side * (half_shoulder - 12)
        cv2.line(depth, (shoulder, y(0.20)), (shoulder + side * 30, y(0.48)), 170, 34)  # arm
        cv2.line(depth, (cx + side * 40, y(0.50)), (cx + side * 45, y(0.97)), 180, 52)  # leg
    return cv2.GaussianBlur(depth, (0, 0), 3)
