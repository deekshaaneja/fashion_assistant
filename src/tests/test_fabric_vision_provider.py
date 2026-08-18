from __future__ import annotations

import json

import httpx
import pytest

from src.domain.models.fabric_vision import ImageRole
from src.providers.settings import get_settings
from src.providers.vision import (
    MockFabricVisionProvider,
    OpenAICompatibleFabricVisionProvider,
    ProviderImage,
    get_fabric_vision_provider,
)
from src.tests.conftest import make_synthetic_fabric_image

_VALID_OUTPUT = {
    "image_subject": "fabric_swatch",
    "subject_reason": "Looks like a flat swatch.",
    "dominant_colors": [{"name": "maroon", "hex_estimate": "#6d2438", "proportion": 0.7, "role": "dominant"}],
    "transparency": {"value": "semi_sheer", "certainty": "medium", "reason": "some background visible"},
    "sheen": {"value": "subtle_sheen", "certainty": "low", "reason": "slight shine"},
    "drape": {"value": "fluid", "certainty": "medium", "reason": "appears to fall softly"},
    "stiffness": {"certainty": "unknown"},
    "structure": {"value": "semi_structured", "certainty": "low"},
    "surface_density": {"value": "sparse", "certainty": "high", "reason": "a little visible surface work"},
    "weight_class": {"value": "light", "certainty": "medium"},
    "embellishment_tolerance": {"certainty": "unknown"},
    "fabric_family": {"value": "organza", "certainty": "medium", "reason": "crisp sheer appearance"},
    "motifs": [],
    "border": {"present": False},
    "embellishment_types": [],
    "wear_potential_indian": 0.7,
    "wear_potential_western": 0.4,
    "wear_potential_fusion": 0.6,
    "wear_potential_reason": "Traditional silhouette-friendly but adaptable.",
    "design_potential_signals": ["STRUCTURED_OCCASIONWEAR"],
    "warnings": [],
    "suggested_additional_photos": [],
}


def _image() -> ProviderImage:
    return ProviderImage(image_id="img1", data=make_synthetic_fabric_image(), role=ImageRole.FULL_VIEW)


def test_mock_provider_returns_output_immediately():
    result = MockFabricVisionProvider().analyze([_image()])
    assert result.output is not None
    assert result.error is None


def test_mock_provider_flags_itself_as_mock():
    result = MockFabricVisionProvider().analyze([_image()], fabric_name_hint="organza")
    assert any("mock" in w.lower() for w in result.output.warnings)


def test_live_provider_returns_none_on_repeated_network_failure(monkeypatch):
    def _always_fails(*args, **kwargs):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(httpx, "post", _always_fails)
    result = OpenAICompatibleFabricVisionProvider().analyze([_image()])
    assert result.output is None
    assert result.error is not None
    assert result.error_code == "VISION_PROVIDER_ERROR"


def test_live_provider_bounded_attempts_on_malformed_json(monkeypatch):
    call_count = 0

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json at all"}}]}

    def _fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)
    result = OpenAICompatibleFabricVisionProvider().analyze([_image()])
    assert result.output is None
    assert call_count == 2  # _MAX_TOTAL_ATTEMPTS


def test_live_provider_repairs_schema_invalid_then_succeeds(monkeypatch):
    responses = [
        {"choices": [{"message": {"content": json.dumps({"title": "not the right shape"})}}]},
        {"choices": [{"message": {"content": json.dumps(_VALID_OUTPUT)}}], "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
    ]

    class _FakeResponse:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    def _fake_post(*args, **kwargs):
        return _FakeResponse(responses.pop(0))

    monkeypatch.setattr(httpx, "post", _fake_post)
    result = OpenAICompatibleFabricVisionProvider().analyze([_image()])
    assert result.output is not None
    assert result.attempts == 2
    assert result.output.fabric_family.value == "organza"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_live_provider_succeeds_on_first_valid_response(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(_VALID_OUTPUT)}}], "usage": {}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse())
    result = OpenAICompatibleFabricVisionProvider().analyze([_image()])
    assert result.output is not None
    assert result.attempts == 1


@pytest.mark.parametrize("value", ["mock"])
def test_get_fabric_vision_provider_mock_mode(monkeypatch, value):
    monkeypatch.setenv("VISION_PROVIDER", value)
    get_settings.cache_clear()
    try:
        assert isinstance(get_fabric_vision_provider(), MockFabricVisionProvider)
    finally:
        get_settings.cache_clear()


def test_get_fabric_vision_provider_auto_mode_disabled_is_mock(monkeypatch):
    monkeypatch.setenv("VISION_PROVIDER", "auto")
    monkeypatch.setenv("VISION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert isinstance(get_fabric_vision_provider(), MockFabricVisionProvider)
    finally:
        get_settings.cache_clear()


def test_get_fabric_vision_provider_live_mode(monkeypatch):
    monkeypatch.setenv("VISION_PROVIDER", "live")
    get_settings.cache_clear()
    try:
        assert isinstance(get_fabric_vision_provider(), OpenAICompatibleFabricVisionProvider)
    finally:
        get_settings.cache_clear()
