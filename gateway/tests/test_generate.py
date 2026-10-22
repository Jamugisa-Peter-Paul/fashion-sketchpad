"""End-to-end: clean -> generate -> queue -> fake ComfyUI -> results -> gallery."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from gateway.config import Settings
from gateway.main import create_app
from gateway.models import Design, Render, RenderView
from gateway.sketch import CANVAS_H, CANVAS_W
from gateway.storage import write_json
from gateway.tests.conftest import AUTH
from gateway.tests.workflow_checks import assert_pure_text_to_image

SAMPLES = Path(__file__).parent / "samples"
STYLE = {"garment": "shirt", "body": "female_slim", "colour": "camel", "fabric": "cotton_twill"}


def clean(client: TestClient, sample: str, view: str = "front", **form: str) -> str:
    response = client.post(
        "/api/sketch/clean",
        headers=AUTH,
        files={"image": (sample, (SAMPLES / sample).read_bytes(), "image/jpeg")},
        data={"view": view, **form},
    )
    assert response.status_code == 200, response.text
    return response.json()["clean_id"]


def wait_for_job(client: TestClient, job_id: str, timeout: float = 15) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if status["status"] in ("done", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {status}")


def generate(client: TestClient, **payload: Any) -> dict[str, str]:
    response = client.post("/api/generate", headers=AUTH, json={"style": STYLE, **payload})
    assert response.status_code == 202, response.text
    return response.json()


def submitted_prompts(fake: FastAPI) -> list[dict[str, Any]]:
    return [p.workflow for p in fake.state.fake.prompts.values()]


def test_front_and_back_render_with_same_seed(client: TestClient, fake_comfy: FastAPI, settings: Settings) -> None:
    views = {
        "front": {"clean_id": clean(client, "shirt_front_paper.jpeg")},
        "back": {"clean_id": clean(client, "shirt_back_paper.jpeg", view="back")},
    }
    ids = generate(client, views=views, title="Utility shirt")
    status = wait_for_job(client, ids["job_id"])
    assert status["status"] == "done", status
    assert status["position"] is None and status["eta_seconds"] is None

    for view in ("front", "back"):
        image = client.get(status["views"][view]["image_url"], headers=AUTH)
        assert image.status_code == 200
        assert Image.open(io.BytesIO(image.content)).size == (CANVAS_W, CANVAS_H)

    workflows = submitted_prompts(fake_comfy)
    assert len(workflows) == 2
    assert workflows[0]["11"]["inputs"]["seed"] == workflows[1]["11"]["inputs"]["seed"] == status["seed"]
    front_prompt, back_prompt = (wf["4"]["inputs"]["text"] for wf in workflows)
    assert back_prompt == "Back view. " + front_prompt
    assert "15" in workflows[0]  # body depth ControlNet is used on the template

    # Pure text-to-image with paper-sketch strengths; the exact workflow and prompt are kept per job.
    for view, workflow in zip(("front", "back"), workflows):
        assert_pure_text_to_image(workflow)
        assert (workflow["9"]["inputs"]["strength"], workflow["9"]["inputs"]["end_percent"]) == (0.7, 0.6)
        assert (workflow["15"]["inputs"]["strength"], workflow["15"]["inputs"]["end_percent"]) == (0.6, 0.7)
        saved = client.get(f"/api/jobs/{ids['job_id']}/{view}/workflow.json", headers=AUTH)
        assert saved.status_code == 200 and saved.json() == workflow
        design_dir = settings.data_dir / "designs" / ids["design_id"]
        prompt_file = design_dir / f"prompt_{ids['job_id']}_{view}.txt"
        assert prompt_file.read_text(encoding="utf-8").strip() == workflow["4"]["inputs"]["text"]

    # A placement check image is written for every job and view.
    for view in ("front", "back"):
        check = client.get(f"/api/jobs/{ids['job_id']}/{view}/check.png", headers=AUTH)
        assert check.status_code == 200
        assert Image.open(io.BytesIO(check.content)).size == (CANVAS_W, CANVAS_H)


def test_variation_and_colour_change_reuse_the_design(client: TestClient, fake_comfy: FastAPI) -> None:
    first = generate(client, views={"front": {"clean_id": clean(client, "shirt_front_paper.jpeg")}}, seed=42)
    wait_for_job(client, first["job_id"])

    variation = generate(client, design_id=first["design_id"])
    recolour = generate(client, design_id=first["design_id"], seed=42, style={**STYLE, "colour": "navy"})
    assert wait_for_job(client, variation["job_id"])["status"] == "done"
    assert wait_for_job(client, recolour["job_id"])["status"] == "done"

    seeds = [wf["11"]["inputs"]["seed"] for wf in submitted_prompts(fake_comfy)]
    assert seeds[0] == 42 and seeds[2] == 42
    assert "navy blue (#1F2A44)" in submitted_prompts(fake_comfy)[2]["4"]["inputs"]["text"]

    design = client.get(f"/api/designs/{first['design_id']}", headers=AUTH).json()
    assert len(design["renders"]) == 3
    assert design["style"]["colour"] == "navy"
    assert set(design["renders"][0]["image_urls"]) == {"front"}
    assert client.get(design["sketch_urls"]["front"], headers=AUTH).status_code == 200


def test_product_shot_skips_depth_and_fills_canvas(client: TestClient, fake_comfy: FastAPI, settings: Settings) -> None:
    clean_id = clean(client, "shirt_back_paper.jpeg", scene="product_shot")
    ids = generate(client, views={"front": {"clean_id": clean_id}}, style={**STYLE, "scene": "product_shot"})
    wait_for_job(client, ids["job_id"])
    workflow = submitted_prompts(fake_comfy)[0]
    assert "15" not in workflow
    control = np.asarray(Image.open(settings.data_dir / "designs" / ids["design_id"] / "control_front.png"))
    ys, xs = np.nonzero(control > 20)
    # Whichever side limits the scale fills ~94% of the canvas (minus the crop margin).
    assert max((xs.max() - xs.min()) / CANVAS_W, (ys.max() - ys.min()) / CANVAS_H) > 0.85


def test_user_placement_is_used(client: TestClient, settings: Settings) -> None:
    clean_id = clean(client, "shirt_front_paper.jpeg")
    placement = {"cx": 300, "cy": 400, "scale": 0.3}
    ids = generate(client, views={"front": {"clean_id": clean_id, "placement": placement}})
    wait_for_job(client, ids["job_id"])
    control = np.asarray(Image.open(settings.data_dir / "designs" / ids["design_id"] / "control_front.png"))
    _, xs = np.nonzero(control > 20)
    assert abs((xs.min() + xs.max()) / 2 - 300) < 15


def test_comfy_error_is_reported_per_view(client: TestClient) -> None:
    ids = generate(client, views={"front": {"clean_id": clean(client, "hoodie.jpeg")}}, style={**STYLE, "notes": "FAIL"})
    status = wait_for_job(client, ids["job_id"])
    assert status["status"] == "error"
    assert "Simulated failure" in status["views"]["front"]["error"]


def test_generate_validation(client: TestClient) -> None:
    def post(payload: dict[str, Any]) -> int:
        return client.post("/api/generate", headers=AUTH, json=payload).status_code

    assert post({"style": STYLE}) == 422  # no views for a new design
    assert post({"style": {**STYLE, "fabric": "velvet"}, "views": {"front": {"clean_id": "0" * 16}}}) == 422
    assert post({"style": STYLE, "views": {"front": {"clean_id": "0" * 16}}}) == 422  # expired upload
    assert post({"style": STYLE, "design_id": "f" * 16}) == 404
    assert client.get("/api/jobs/nope", headers=AUTH).status_code == 404


def test_gallery_list_rename_delete(client: TestClient) -> None:
    ids = generate(client, views={"front": {"clean_id": clean(client, "hoodie.jpeg")}})
    wait_for_job(client, ids["job_id"])
    designs = client.get("/api/designs", headers=AUTH).json()
    assert [d["id"] for d in designs] == [ids["design_id"]]
    assert designs[0]["thumbnail_url"] == f"/api/jobs/{ids['job_id']}/front.png"

    renamed = client.patch(f"/api/designs/{ids['design_id']}", headers=AUTH, json={"title": "Hoodie"})
    assert renamed.json()["title"] == "Hoodie"

    assert client.delete(f"/api/designs/{ids['design_id']}", headers=AUTH).status_code == 204
    assert client.get("/api/designs", headers=AUTH).json() == []
    assert client.get(f"/api/jobs/{ids['job_id']}", headers=AUTH).status_code == 404


def test_unfinished_jobs_resume_after_restart(settings: Settings, fake_comfy: FastAPI) -> None:
    """A job saved as queued (gateway stopped before running it) is picked up at startup."""
    design_id, job_id = "a" * 16, "b" * 16
    folder = settings.data_dir / "designs" / design_id
    folder.mkdir(parents=True)
    lines = np.zeros((CANVAS_H, CANVAS_W), np.uint8)
    lines[300:900, 300:302] = 255
    Image.fromarray(lines).save(folder / "lines_front.png")
    Image.fromarray(255 - lines).save(folder / "sketch_front.png")
    style = {**STYLE}
    design = Design(
        id=design_id,
        style=style,  # type: ignore[arg-type]
        views={"front": {"source": "drawn", "width": CANVAS_W, "height": CANVAS_H}},  # type: ignore[dict-item]
        renders=[Render(id=job_id, seed=7, style=style, views={"front": RenderView()})],  # type: ignore[arg-type]
    )
    write_json(folder / "design.json", design.model_dump(mode="json"))

    app = create_app(settings, comfy_transport=httpx.ASGITransport(app=fake_comfy))
    with TestClient(app) as client:
        status = wait_for_job(client, job_id)
    assert status["status"] == "done"
    assert (folder / f"render_{job_id}_front.png").exists()


def test_health_reports_comfy(client: TestClient) -> None:
    assert client.get("/api/health").json()["comfy"] == "ok"


def test_drawn_sketch_uses_drawn_strengths(client: TestClient, fake_comfy: FastAPI) -> None:
    drawing = np.full((CANVAS_H, CANVAS_W), 255, np.uint8)
    drawing[300:302, 300:520] = 0
    drawing[300:800, 300:302] = 0
    buffer = io.BytesIO()
    Image.fromarray(drawing).save(buffer, format="PNG")
    response = client.post(
        "/api/sketch/clean", headers=AUTH, files={"image": ("d.png", buffer.getvalue(), "image/png")}, data={"source": "drawn"}
    )
    ids = generate(client, views={"front": {"clean_id": response.json()["clean_id"]}})
    wait_for_job(client, ids["job_id"])
    workflow = submitted_prompts(fake_comfy)[0]
    assert_pure_text_to_image(workflow)
    assert (workflow["9"]["inputs"]["strength"], workflow["9"]["inputs"]["end_percent"]) == (0.8, 0.7)


def test_workflow_json_404_before_submission(client: TestClient) -> None:
    assert client.get("/api/jobs/0123456789abcdef/front/workflow.json", headers=AUTH).status_code == 404
