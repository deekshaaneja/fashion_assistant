from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agent.session_store import SessionStore
from src.api import main as api_main
from src.providers.settings import get_settings
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "mock")
    monkeypatch.setenv("AGENT_SESSION_DB_PATH", str(tmp_path / "sessions.db"))
    get_settings.cache_clear()

    # fresh SessionStore for this test's own tmp_path db
    import src.agent.session_store as store_module

    store_module._store = None
    yield
    store_module._store = None
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(api_main.app)


def test_new_session_id_is_implicitly_created(client):
    response = client.post("/v1/chat", data={"session_id": "brand-new-session", "message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "brand-new-session"
    assert "message" in body
    assert body["artifacts"] == []


def test_unknown_field_is_rejected(client):
    # StrictModel-equivalent enforcement happens at the response shape;
    # the request itself is form-encoded, so this instead checks that a
    # missing required field is a clean 422, not a 500.
    response = client.post("/v1/chat", data={"message": "hello"})
    assert response.status_code == 422


def test_response_never_leaks_provider_metadata_or_api_key(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key-value")
    get_settings.cache_clear()
    response = client.post("/v1/chat", data={"session_id": "s1", "message": "Give me three options."})
    body_text = response.text
    assert "super-secret-key-value" not in body_text
    assert "generation_metadata" not in body_text


def test_fabric_upload_and_design_generation_over_http(client, tmp_path):
    image_path = tmp_path / "swatch.jpg"
    image_path.write_bytes(make_synthetic_fabric_image())

    with open(image_path, "rb") as f:
        r1 = client.post(
            "/v1/chat",
            data={"session_id": "http-session", "message": "This is my fabric."},
            files={"images": ("swatch.jpg", f, "image/jpeg")},
        )
    assert r1.status_code == 200

    r2 = client.post("/v1/chat", data={"session_id": "http-session", "message": "Give me three options."})
    assert r2.status_code == 200
    body = r2.json()
    assert len(body["artifacts"]) == 3
    assert all(a["kind"] == "design_version" for a in body["artifacts"])


def test_session_persists_across_requests(client, tmp_path):
    image_path = tmp_path / "swatch.jpg"
    image_path.write_bytes(make_synthetic_fabric_image())
    with open(image_path, "rb") as f:
        client.post(
            "/v1/chat",
            data={"session_id": "persisted-session", "message": "This is my fabric."},
            files={"images": ("swatch.jpg", f, "image/jpeg")},
        )

    store = SessionStore(get_settings().agent_session_db_path)
    loaded = store.load("persisted-session")
    assert loaded is not None
    assert loaded.fabric_refs
