from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.catalog import load_catalog
from gateway.tests.conftest import AUTH


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_requires_token(client: TestClient) -> None:
    assert client.get("/api/catalog").status_code == 401
    bad = client.get("/api/catalog", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_any_configured_token_works(client: TestClient) -> None:
    response = client.get("/api/catalog", headers={"Authorization": "Bearer second-token"})
    assert response.status_code == 200


def test_catalog_flags_templates(client: TestClient) -> None:
    data = client.get("/api/catalog", headers=AUTH).json()
    bodies = {b["id"]: b for b in data["bodies"]}
    assert len(bodies) == 22
    assert bodies["female_slim"]["available"] is True
    assert bodies["female_slim"]["views"] == ["front", "back"]
    assert bodies["male_slim"]["available"] is False
    assert bodies["male_slim"]["views"] == []
    assert {g["id"] for g in data["garments"]} >= {"shirt", "gomesi", "kanzu", "jumpsuit"}


def test_catalog_yaml_has_one_default_scene_and_finish() -> None:
    catalog = load_catalog()
    assert [s.id for s in catalog.scenes if s.default] == ["light_room"]
    assert [m.id for m in catalog.mannequin_finishes if m.default] == ["matte_dark_grey"]
    for section in ("garments", "fabrics", "colours", "prints", "fits", "buttons", "stitching", "bodies"):
        ids = [item.id for item in getattr(catalog, section)]
        assert len(ids) == len(set(ids)), f"duplicate id in {section}"


def test_guide_png(client: TestClient) -> None:
    response = client.get("/api/templates/female_slim/front/guide.png", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    missing = client.get("/api/templates/male_slim/front/guide.png", headers=AUTH)
    assert missing.status_code == 404


def test_template_photo_thumbnail(client: TestClient) -> None:
    response = client.get("/api/templates/female_slim/front/photo.jpg", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert client.get("/api/templates/male_slim/front/photo.jpg", headers=AUTH).status_code == 404


def test_guide_rejects_unknown_body(client: TestClient) -> None:
    for body in ("%2E%2E", "not_a_body"):
        response = client.get(f"/api/templates/{body}/front/guide.png", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown body type"


def test_cors_allows_capacitor_origin(client: TestClient) -> None:
    response = client.options(
        "/api/catalog",
        headers={"Origin": "https://localhost", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "https://localhost"
