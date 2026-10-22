from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from gateway.config import Settings
from gateway.main import create_app
from gateway.sketch import CANVAS_H, CANVAS_W
from gateway.tests.conftest import AUTH

SAMPLES = Path(__file__).parent / "samples"


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def post_clean(client: TestClient, data: bytes, **form: str):
    return client.post(
        "/api/sketch/clean",
        headers=AUTH,
        files={"image": ("sketch.jpg", data, "image/jpeg")},
        data=form,
    )


def test_clean_paper_sample_and_fetch_previews(client: TestClient) -> None:
    response = post_clean(client, (SAMPLES / "shirt_front_paper.jpeg").read_bytes(), source="paper", garment="shirt")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "paper"
    assert 0 < body["placement"]["scale"] < 1
    assert 0 < body["placement"]["cy"] < CANVAS_H / 2  # a shirt sits in the upper half

    lines = client.get(body["lines_url"], headers=AUTH)
    assert lines.status_code == 200
    assert Image.open(io.BytesIO(lines.content)).size == (body["width"], body["height"])
    overlay = Image.open(io.BytesIO(client.get(body["overlay_url"], headers=AUTH).content))
    assert overlay.mode == "RGBA"


def test_clean_product_shot_is_centred(client: TestClient) -> None:
    response = post_clean(client, (SAMPLES / "shirt_back_paper.jpeg").read_bytes(), scene="product_shot")
    placement = response.json()["placement"]
    assert placement["cx"] == CANVAS_W / 2 and placement["cy"] == CANVAS_H / 2


def test_clean_drawn_keeps_canvas_alignment(client: TestClient) -> None:
    drawing = np.full((CANVAS_H, CANVAS_W), 255, np.uint8)
    drawing[300:700, 300:302] = 0
    response = post_clean(client, png_bytes(Image.fromarray(drawing)), source="drawn")
    body = response.json()
    assert (body["width"], body["height"]) == (CANVAS_W, CANVAS_H)
    assert body["placement"] == {"cx": CANVAS_W / 2, "cy": CANVAS_H / 2, "scale": 1.0}


def test_clean_rejects_bad_input(client: TestClient) -> None:
    assert post_clean(client, b"garbage").status_code == 422
    assert post_clean(client, png_bytes(Image.new("L", (400, 400), 255))).status_code == 422
    sample = (SAMPLES / "hoodie.jpeg").read_bytes()
    assert post_clean(client, sample, garment="ballgown").status_code == 422
    assert post_clean(client, sample, source="crayon").status_code == 422


def test_clean_requires_token(client: TestClient) -> None:
    response = client.post("/api/sketch/clean", files={"image": ("a.png", b"x", "image/png")})
    assert response.status_code == 401


def test_upload_size_limit(settings: Settings) -> None:
    settings.max_upload_mb = 1
    with TestClient(create_app(settings)) as client:
        response = post_clean(client, b"0" * (1024 * 1024 + 1))
    assert response.status_code == 413


def test_unknown_or_malformed_clean_id_is_404(client: TestClient) -> None:
    assert client.get("/api/sketch/0123456789abcdef/lines.png", headers=AUTH).status_code == 404
    assert client.get("/api/sketch/..%2F..%2Fx/lines.png", headers=AUTH).status_code == 404
