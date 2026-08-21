from __future__ import annotations

import base64
import json

import httpx
import pytest

from src.domain.models.visualization import (
    ConstructionVisualSpec,
    DecorationVisualSpec,
    GarmentSpec,
    NecklineVisualSpec,
    PresentationMode,
    SleevesVisualSpec,
    SubjectSpec,
    ViewAngle,
    VisualizationSpecification,
)
from src.providers.settings import get_settings
from src.providers.visualization import (
    FalKontextVisualizationProvider,
    GeminiVisualizationProvider,
    MockDesignVisualizationProvider,
    MockGeneratedImageValidator,
    OpenAICompatibleDesignVisualizationProvider,
    OpenAICompatibleGeneratedImageValidator,
    ReferenceImage,
    VisualizationProviderRequest,
    estimated_cost_per_image_usd,
    get_design_visualization_provider,
    get_generated_image_validator,
)


def _spec() -> VisualizationSpecification:
    return VisualizationSpecification(
        design_id="test-design",
        subject=SubjectSpec(presentation=PresentationMode.MANNEQUIN, view=ViewAngle.FRONT),
        garment=GarmentSpec(category="suit", category_name="Suit", silhouette="anarkali", silhouette_name="Anarkali"),
        construction=ConstructionVisualSpec(
            bodice="fitted", waist="natural", flare_level="high", flare_construction="gathered", length="floor_length"
        ),
        neckline=NecklineVisualSpec(type="round"),
        sleeves=SleevesVisualSpec(length="three_quarter", style="straight"),
        decoration=DecorationVisualSpec(level="MINIMAL"),
    )


def _reference() -> ReferenceImage:
    return ReferenceImage(image_id="img1", data=b"fake-jpeg-bytes")


def test_mock_provider_returns_images():
    result = MockDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=1)
    )
    assert len(result.images) == 1
    assert result.error is None


def test_mock_provider_respects_count():
    result = MockDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=2)
    )
    assert len(result.images) == 2


def test_gemini_generate_never_duplicates_one_image_for_count_greater_than_one(monkeypatch):
    """Phase 4 finalization, section 5-6: one real generation must never be
    reported as N distinct visualizations. `VisualizationOptions` already
    rejects count>1 before reaching a provider, but the provider itself
    must be correct in isolation too (e.g. against a bare
    `VisualizationProviderRequest`, which has no such guard)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()

    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    b64 = base64.b64encode(png_bytes).decode()

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": b64}}]}}
                ]
            }

    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse())
    try:
        result = GeminiVisualizationProvider().generate(
            VisualizationProviderRequest(
                specification=_spec(), reference_images=[_reference()], prompt="p", count=3
            )
        )
    finally:
        get_settings.cache_clear()
    assert len(result.images) == 1


def test_fal_generate_never_duplicates_one_image_for_count_greater_than_one(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-key")
    get_settings.cache_clear()

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"images": [{"url": "https://example.com/out.jpg", "content_type": "image/jpeg"}]}

    class _FakeImageResponse:
        content = b"fake-image-bytes"

        def raise_for_status(self):
            return None

    def _fake_post(url, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", _fake_post)
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeImageResponse())
    try:
        result = FalKontextVisualizationProvider().generate(
            VisualizationProviderRequest(
                specification=_spec(), reference_images=[_reference()], prompt="p", count=3
            )
        )
    finally:
        get_settings.cache_clear()
    assert len(result.images) == 1


def test_estimated_cost_per_image_known_providers():
    assert estimated_cost_per_image_usd("gemini") is not None
    assert estimated_cost_per_image_usd("fal") is not None
    assert estimated_cost_per_image_usd("mock") is None
    assert estimated_cost_per_image_usd("unknown") is None


def test_live_provider_returns_error_on_repeated_network_failure(monkeypatch):
    def _always_fails(*args, **kwargs):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(httpx, "post", _always_fails)
    result = OpenAICompatibleDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=1)
    )
    assert result.images == []
    assert result.error_code == "VISUALIZATION_PROVIDER_ERROR"


def test_live_provider_times_out_cleanly(monkeypatch):
    def _hangs(*args, **kwargs):
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(httpx, "post", _hangs)
    result = OpenAICompatibleDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=1)
    )
    assert result.images == []
    assert result.error_code == "VISUALIZATION_PROVIDER_TIMEOUT"


def test_live_provider_treats_empty_response_as_structured_failure(monkeypatch):
    """Empirically, this is exactly what this account's image-capable
    models returned (section 9) -- HTTP 200, no image payload."""

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"role": "assistant"}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse())
    result = OpenAICompatibleDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=1)
    )
    assert result.images == []
    assert result.error_code == "VISUALIZATION_OUTPUT_EMPTY"


def test_live_provider_extracts_image_from_data_url_content_list(monkeypatch):
    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    b64 = base64.b64encode(png_bytes).decode()

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}],
                        }
                    }
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse())
    result = OpenAICompatibleDesignVisualizationProvider().generate(
        VisualizationProviderRequest(specification=_spec(), reference_images=[_reference()], prompt="p", count=1)
    )
    assert len(result.images) == 1
    assert result.images[0].data == png_bytes


@pytest.mark.parametrize("mode", ["mock"])
def test_get_design_visualization_provider_mock_mode(monkeypatch, mode):
    monkeypatch.setenv("VISUALIZATION_PROVIDER", mode)
    get_settings.cache_clear()
    try:
        assert isinstance(get_design_visualization_provider(), MockDesignVisualizationProvider)
    finally:
        get_settings.cache_clear()


def test_get_design_visualization_provider_auto_disabled_is_mock(monkeypatch):
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "auto")
    monkeypatch.setenv("VISUALIZATION_ENABLED", "false")
    # "auto" prefers Gemini/fal over Aliyun when either is configured (the
    # MVP default) -- clear both so this test genuinely exercises the
    # no-provider-configured-at-all fallback, regardless of this machine's
    # own .env.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("FAL_KEY", "")
    get_settings.cache_clear()
    try:
        assert isinstance(get_design_visualization_provider(), MockDesignVisualizationProvider)
    finally:
        get_settings.cache_clear()


def test_get_design_visualization_provider_live_mode(monkeypatch):
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "live")
    get_settings.cache_clear()
    try:
        assert isinstance(get_design_visualization_provider(), OpenAICompatibleDesignVisualizationProvider)
    finally:
        get_settings.cache_clear()


# --- GeneratedImageValidator -------------------------------------------------


def test_mock_validator_returns_unknown_observation():
    result = MockGeneratedImageValidator().analyze(b"fake-bytes")
    assert result.observation is not None
    assert result.observation.garment_subject is None
    assert result.error is None


def test_live_validator_parses_valid_json(monkeypatch):
    payload = {
        "garment_subject": "anarkali suit",
        "neckline": "round",
        "sleeve_length": "three_quarter",
        "sleeve_style": "straight",
        "dupatta_present": True,
        "dominant_color": "wine",
        "surface_density": "moderate",
        "border_present": False,
        "transparency": "semi_sheer",
        "reason": "clearly visible",
    }

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse())
    result = OpenAICompatibleGeneratedImageValidator().analyze(b"fake-bytes")
    assert result.observation is not None
    assert result.observation.dominant_color == "wine"
    assert result.observation.dupatta_present is True


def test_live_validator_bounded_attempts_on_invalid_json(monkeypatch):
    call_count = 0

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    def _fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)
    result = OpenAICompatibleGeneratedImageValidator().analyze(b"fake-bytes")
    assert result.observation is None
    assert call_count == 2  # _MAX_VALIDATION_ATTEMPTS


@pytest.mark.parametrize("mode", ["mock"])
def test_get_generated_image_validator_mock_mode(monkeypatch, mode):
    monkeypatch.setenv("VISUALIZATION_PROVIDER", mode)
    get_settings.cache_clear()
    try:
        assert isinstance(get_generated_image_validator(), MockGeneratedImageValidator)
    finally:
        get_settings.cache_clear()
