from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.providers.settings import get_settings
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _mock_vision(monkeypatch):
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_analyze_fabric_image_endpoint_success(client):
    resp = client.post(
        "/v1/tools/analyze-fabric-image",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"fabric_name_hint": "organza"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fabric_profile"]["fabric_name"] == "organza"
    assert body["generation_metadata"]["provider"] == "mock"
    assert "evidence" in body and isinstance(body["evidence"], list)


def test_analyze_fabric_image_endpoint_multiple_files(client):
    resp = client.post(
        "/v1/tools/analyze-fabric-image",
        files=[
            ("images", ("full.jpg", make_synthetic_fabric_image(), "image/jpeg")),
            ("images", ("closeup.jpg", make_synthetic_fabric_image(background=(10, 200, 10), accent=(10, 10, 10)), "image/jpeg")),
        ],
    )
    assert resp.status_code == 200
    assert resp.json()["generation_metadata"]["images_submitted"] == 2


def test_analyze_fabric_image_endpoint_invalid_user_confirmed_properties(client):
    resp = client.post(
        "/v1/tools/analyze-fabric-image",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"user_confirmed_properties": "not valid json"},
    )
    assert resp.status_code == 400


def test_analyze_fabric_image_endpoint_applies_user_confirmed_name(client):
    resp = client.post(
        "/v1/tools/analyze-fabric-image",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"user_confirmed_fabric_name": "tissue silk"},
    )
    assert resp.status_code == 200
    assert resp.json()["fabric_profile"]["fabric_name"] == "tissue silk"


def test_analyze_fabric_image_endpoint_bad_image_roles_json(client):
    resp = client.post(
        "/v1/tools/analyze-fabric-image",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"image_roles": "{not json"},
    )
    assert resp.status_code == 400


def test_fabric_image_recommend_silhouettes_endpoint_success(client):
    resp = client.post(
        "/v1/tools/fabric-image/recommend-silhouettes",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"fabric_name_hint": "organza", "context": json.dumps({"occasion": "festive"})},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "silhouette_recommendation" in body
    assert body["silhouette_recommendation"]["candidates"]
    assert body["image_analysis"]["fabric_profile"]["fabric_name"] == "organza"


def test_fabric_image_recommend_silhouettes_endpoint_bad_context(client):
    resp = client.post(
        "/v1/tools/fabric-image/recommend-silhouettes",
        files=[("images", ("swatch.jpg", make_synthetic_fabric_image(), "image/jpeg"))],
        data={"context": "definitely not json"},
    )
    assert resp.status_code == 400
