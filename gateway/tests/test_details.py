"""Sketch details from the vision LLM: parsing, the /api/sketch/details endpoint, and use at render time."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.details import DetailsError, SketchDetails, parse_details
from gateway.tests.conftest import AUTH
from gateway.tests.test_generate import STYLE, clean, generate, submitted_prompts, wait_for_job


def test_parse_plain_json() -> None:
    details = parse_details('{"garment": ["wide-leg trousers"], "front": ["two slant pockets"], "back": []}')
    assert details == SketchDetails(garment=["wide-leg trousers"], front=["two slant pockets"])


def test_parse_fenced_json_after_thinking() -> None:
    content = '<think>hmm {not json}</think>Here you go:\n```json\n{"front": ["Five Buttons."]}\n```'
    assert parse_details(content).front == ["five buttons"]


def test_parse_drops_colours_fabrics_and_drawing_talk() -> None:
    details = parse_details(
        json.dumps({"front": ["black buttons", "pencil outline", "denim yoke", "notched lapels", "handwritten note"]})
    )
    assert details.front == ["notched lapels"]


@pytest.mark.parametrize("content", ["no json here", "{broken", "[1, 2]"])
def test_parse_rejects_non_json(content: str) -> None:
    with pytest.raises(DetailsError):
        parse_details(content)


def test_for_view_puts_shared_details_first_without_repeats() -> None:
    details = SketchDetails(garment=["hood"], front=["kangaroo pocket", "hood"], back=["plain back"])
    assert details.for_view("front") == ["hood", "kangaroo pocket"]
    assert details.for_view("back") == ["hood", "plain back"]
    assert details.for_view("side") == ["hood"]


# --- endpoint ------------------------------------------------------------------------------------------


def test_details_endpoint_reads_both_views_once(llm_client: TestClient, fake_llm: FastAPI) -> None:
    views = {"front": clean(llm_client, "shirt_front_paper.jpeg"), "back": clean(llm_client, "shirt_back_paper.jpeg", view="back")}
    response = llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "shirt", "views": views})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    assert body["details"]["front"] == ["six-button front placket", "two chest flap pockets"]
    assert body["details"]["back"] == ["back yoke", "centre box pleat"]

    request = fake_llm.state.fake.requests[0]
    assert request["authorization"] == "Bearer llm-secret"
    content = request["body"]["messages"][0]["content"]
    assert "button-up shirt" in content[0]["text"] and "the front view and the back view" in content[0]["text"]
    assert [part["type"] for part in content] == ["text", "image_url", "image_url"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert request["body"]["chat_template_kwargs"] == {"enable_thinking": False}

    # Cached: asking again (going back and forth between screens) doesn't call the LLM again.
    again = llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "shirt", "views": views})
    assert again.json() == body and len(fake_llm.state.fake.requests) == 1


def test_details_endpoint_reports_llm_failure_without_failing(llm_client: TestClient, fake_llm: FastAPI) -> None:
    fake_llm.state.fake.status = 503
    views = {"front": clean(llm_client, "hoodie.jpeg")}
    body = llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "hoodie", "views": views}).json()
    assert body["details"] is None and "503" in body["error"]


def test_details_endpoint_when_llm_is_not_set_up(client: TestClient) -> None:
    views = {"front": clean(client, "hoodie.jpeg")}
    body = client.post("/api/sketch/details", headers=AUTH, json={"garment": "hoodie", "views": views}).json()
    assert body["details"] is None and "LLM_URL" in body["error"]


def test_details_endpoint_validates_input(llm_client: TestClient) -> None:
    views = {"front": clean(llm_client, "hoodie.jpeg")}
    assert llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "cape", "views": views}).status_code == 422
    assert llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "shirt", "views": {}}).status_code == 422
    missing = {"front": "0123456789abcdef"}
    assert llm_client.post("/api/sketch/details", headers=AUTH, json={"garment": "shirt", "views": missing}).status_code == 404
    assert llm_client.post("/api/sketch/details", json={"garment": "shirt", "views": views}).status_code == 401


# --- at render time -----------------------------------------------------------------------------------


def _views(client: TestClient) -> dict[str, dict[str, str]]:
    return {
        "front": {"clean_id": clean(client, "shirt_front_paper.jpeg")},
        "back": {"clean_id": clean(client, "shirt_back_paper.jpeg", view="back")},
    }


def test_render_reads_details_itself_when_the_app_sends_none(
    llm_client: TestClient, fake_comfy: FastAPI, fake_llm: FastAPI
) -> None:
    ids = generate(llm_client, views=_views(llm_client))
    status = wait_for_job(llm_client, ids["job_id"])
    assert status["status"] == "done"
    assert status["details"]["front"] == ["six-button front placket", "two chest flap pockets"]

    front, back = (wf["4"]["inputs"]["text"] for wf in submitted_prompts(fake_comfy))
    assert "construction details: pointed shirt collar, long sleeves with buttoned cuffs, six-button front placket" in front
    assert "centre box pleat" in back and "six-button" not in back and "box pleat" not in front

    # New variation of the same design: details come from the design, the LLM is not asked again.
    second = generate(llm_client, design_id=ids["design_id"])
    assert wait_for_job(llm_client, second["job_id"])["details"] == status["details"]
    assert len(fake_llm.state.fake.requests) == 1


def test_details_from_the_app_win_and_skip_the_llm(llm_client: TestClient, fake_comfy: FastAPI, fake_llm: FastAPI) -> None:
    style = {**STYLE, "details": {"front": ["three welt pockets"], "back": []}}
    response = llm_client.post("/api/generate", headers=AUTH, json={"style": style, "views": _views(llm_client)})
    status = wait_for_job(llm_client, response.json()["job_id"])
    assert status["details"]["front"] == ["three welt pockets"]
    assert "three welt pockets" in submitted_prompts(fake_comfy)[0]["4"]["inputs"]["text"]
    assert fake_llm.state.fake.requests == []


def test_render_without_details_when_llm_fails(llm_client: TestClient, fake_comfy: FastAPI, fake_llm: FastAPI) -> None:
    fake_llm.state.fake.answer = "Sorry, I can't see an image."
    ids = generate(llm_client, views=_views(llm_client))
    status = wait_for_job(llm_client, ids["job_id"])
    assert status["status"] == "done"
    assert status["details"] == {"garment": [], "front": [], "back": [], "side": []}
    assert "exact construction details" not in submitted_prompts(fake_comfy)[0]["4"]["inputs"]["text"]


def test_new_sketch_forgets_old_details(llm_client: TestClient, fake_llm: FastAPI) -> None:
    ids = generate(llm_client, views=_views(llm_client))
    wait_for_job(llm_client, ids["job_id"])
    fake_llm.state.fake.answer = json.dumps({"front": ["kangaroo pocket"]})
    second = generate(llm_client, design_id=ids["design_id"], views={"front": {"clean_id": clean(llm_client, "hoodie.jpeg")}})
    assert wait_for_job(llm_client, second["job_id"])["details"]["front"] == ["kangaroo pocket"]
    assert len(fake_llm.state.fake.requests) == 2


def test_render_still_runs_when_reading_details_crashes(
    llm_client: TestClient, fake_comfy: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> str:
        raise OSError("unreadable sketch")

    monkeypatch.setattr("gateway.details._image_url", broken)
    ids = generate(llm_client, views=_views(llm_client))
    status = wait_for_job(llm_client, ids["job_id"])
    assert status["status"] == "done" and status["details"]["front"] == []
