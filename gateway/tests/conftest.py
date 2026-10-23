from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from gateway.config import LlmSettings, RenderSettings, Settings
from gateway.main import create_app
from gateway.tools.fake_comfy import create_fake_comfy
from gateway.tools.fake_llm import create_fake_llm

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def write_template(templates_dir: Path, body: str, view: str) -> None:
    """Creates the four files the template generator writes for one view."""
    folder = templates_dir / body
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (832, 1216), (0, 0, 0, 0)).save(folder / f"{view}_guide.png")
    Image.new("L", (832, 1216), 0).save(folder / f"{view}_mask.png")
    Image.new("RGB", (832, 1216), (90, 90, 90)).save(folder / f"{view}_depth_00001_.png")
    Image.new("RGB", (832, 1216), (200, 200, 200)).save(folder / f"{view}_photo_00001_.png")


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    path = tmp_path / "templates"
    for view in ("front", "back"):
        write_template(path, "female_slim", view)
    return path


@pytest.fixture
def settings(tmp_path: Path, templates_dir: Path) -> Settings:
    return Settings(
        comfy_url="http://comfy.test",
        templates_dir=templates_dir,
        data_dir=tmp_path / "data",
        app_tokens=[TOKEN, "second-token"],
        render=RenderSettings(poll_interval_s=0.01, view_timeout_s=10),
    )


@pytest.fixture
def fake_comfy() -> FastAPI:
    return create_fake_comfy(seconds=0.0)


@pytest.fixture
def fake_llm() -> FastAPI:
    return create_fake_llm()


@pytest.fixture
def client(settings: Settings, fake_comfy: FastAPI) -> TestClient:
    """Detail reading off (no LLM_URL), like a server without the LLM set up."""
    app = create_app(settings, comfy_transport=httpx.ASGITransport(app=fake_comfy))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def llm_client(settings: Settings, fake_comfy: FastAPI, fake_llm: FastAPI) -> TestClient:
    """Detail reading on, answered by the fake LLM."""
    settings.llm = LlmSettings(url="http://llm.test/v1", api_key="llm-secret", timeout_s=5)
    app = create_app(
        settings,
        comfy_transport=httpx.ASGITransport(app=fake_comfy),
        llm_transport=httpx.ASGITransport(app=fake_llm),
    )
    with TestClient(app) as test_client:
        yield test_client
