from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_fabric_endpoint(client):
    resp = client.post("/v1/tools/analyze-fabric", json={"fabric_name": "organza"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["resolved_fabric_id"] == "organza"


def test_recommend_silhouettes_endpoint(client):
    resp = client.post(
        "/v1/tools/recommend-silhouettes",
        json={"fabric_name": "georgette", "context": {"occasion": "festive", "top_n": 3}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["candidates"]) == 3


def test_recommend_fabrics_endpoint(client):
    resp = client.post(
        "/v1/tools/recommend-fabrics",
        json={"silhouette_id": "a_line", "garment_id": "suit", "context": {"top_n": 5}},
    )
    assert resp.status_code == 200
    assert len(resp.json()["candidates"]) == 5


def test_recommend_fabrics_endpoint_unknown_silhouette_is_400(client):
    resp = client.post("/v1/tools/recommend-fabrics", json={"silhouette_id": "not_real"})
    assert resp.status_code == 400


def test_recommend_styling_endpoint(client):
    resp = client.post(
        "/v1/tools/recommend-styling",
        json={"garment_id": "suit", "silhouette_id": "a_line", "fabric_name": "organza"},
    )
    assert resp.status_code == 200
    assert resp.json()["sleeve"] == "three_quarter"


def test_calculate_consumption_endpoint(client):
    resp = client.post(
        "/v1/tools/calculate-consumption",
        json={"garment_id": "suit", "silhouette_id": "anarkali", "size": "M"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["min_metres"] < body["max_metres"]


def test_check_fabric_feasibility_endpoint(client):
    resp = client.post(
        "/v1/tools/check-fabric-feasibility",
        json={"available_metres": 3.0, "required_range": {"min": 4.8, "max": 5.2}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "INSUFFICIENT"


def test_generate_colorways_endpoint(client):
    resp = client.post(
        "/v1/tools/generate-colorways",
        json={"fabric_name": "georgette", "context": {"occasion": "wedding_guest"}},
    )
    assert resp.status_code == 200
    assert resp.json()["main_colors"]


def test_unknown_fields_are_rejected(client):
    resp = client.post("/v1/tools/analyze-fabric", json={"fabric_name": "silk", "not_a_field": True})
    assert resp.status_code == 422
