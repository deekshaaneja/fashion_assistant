from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage, generate_design_directions_from_images
from src.providers.settings import get_settings
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch, tmp_path):
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "mock")
    monkeypatch.setenv("VISUALIZATION_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    import src.fashion_engine.visualization.asset_store as asset_store_module

    asset_store_module._store = None
    yield
    get_settings.cache_clear()
    asset_store_module._store = None


@pytest.fixture
def client():
    return TestClient(app)


def _design_and_analysis_json():
    images = [UploadedFabricImage(image_id="img1", data=make_synthetic_fabric_image())]
    result = generate_design_directions_from_images(
        images, fabric_name_hint="organza", selected_garment_id="suit", selected_silhouette_id="anarkali", count=1
    )
    design = result.design_directions.designs[0]
    return design.model_dump_json(), result.image_analysis.model_dump_json(), images


def test_visualize_design_endpoint_success(client):
    design_json, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"design": design_json, "fabric_analysis": analysis_json},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["images"]
    assert body["generation_metadata"]["provider"] == "mock"
    assert "disclaimer" in body


def test_visualize_design_endpoint_requires_design(client):
    _, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"fabric_analysis": analysis_json},
    )
    assert resp.status_code == 422  # missing required form field


def test_visualize_design_endpoint_bad_design_json(client):
    _, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"design": "not valid json", "fabric_analysis": analysis_json},
    )
    assert resp.status_code == 400


def test_visualize_design_endpoint_bad_options_json(client):
    design_json, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"design": design_json, "fabric_analysis": analysis_json, "options": "not json"},
    )
    assert resp.status_code == 400


def test_get_visualization_asset_roundtrip(client):
    design_json, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"design": design_json, "fabric_analysis": analysis_json},
    )
    image = resp.json()["images"][0]
    filename = image["uri"].rsplit("/", 1)[-1]

    asset_resp = client.get(f"/v1/visualizations/{filename}")
    assert asset_resp.status_code == 200
    assert asset_resp.content


def test_get_visualization_asset_missing_returns_404(client):
    resp = client.get("/v1/visualizations/does-not-exist.png")
    assert resp.status_code == 404


def test_visualize_design_endpoint_rejects_count_greater_than_one(client, tmp_path, monkeypatch):
    """Phase 4 finalization, section 6/24: a count>1 request must be
    rejected before any provider call -- confirmed here by asserting no
    asset was ever written to the store."""
    design_json, analysis_json, images = _design_and_analysis_json()
    resp = client.post(
        "/v1/tools/visualize-design",
        files=[("images", (images[0].image_id, images[0].data, "image/jpeg"))],
        data={"design": design_json, "fabric_analysis": analysis_json, "options": json.dumps({"count": 2})},
    )
    assert resp.status_code == 400
    assert "MULTIPLE_VISUALIZATIONS_NOT_SUPPORTED" in resp.json()["detail"]
    assert list(tmp_path.iterdir()) == []  # no provider call was ever made, nothing was stored
