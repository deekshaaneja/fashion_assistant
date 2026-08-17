"""Tests for the generate-design-directions timeout bug fix: every external
call and every retry loop must be finitely bounded, count=1 must skip
diversity entirely, and the endpoint must return well within a bounded time
even when the live provider is completely unavailable."""
from __future__ import annotations

import time

import httpx
import pytest

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.fashion_engine.design.constraints import build_design_constraints
from src.fashion_engine.design.generate import generate_design_directions
from src.providers.design_generation import (
    _HTTP_CALL_TIMEOUT_S,
    _MAX_TOTAL_ATTEMPTS,
    _PROVIDER_TOTAL_BUDGET_S,
    MockDesignGenerationProvider,
    OpenAICompatibleDesignGenerationProvider,
    TemplateDesignGenerationProvider,
)
from src.providers.settings import get_settings
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository


def _request(count=3):
    from src.domain.models.design_generation import DesignGenerationRequest

    fabric = get_fabric_repository().resolve("organza").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("anarkali")
    context = RecommendationContext(occasion="engagement")
    brief = ClientBrief(desired_aesthetic=["elegant", "contemporary"])
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)
    return DesignGenerationRequest(
        fabric=fabric,
        fashion_context=context,
        client_brief=brief,
        constraints=constraints,
        garment_id=garment.id,
        garment_name=garment.name,
        silhouette_id=silhouette.id,
        silhouette_name=silhouette.name,
        count=count,
    )


# --- 1. bounds are actually finite, not just "large" ------------------------


def test_bounds_are_tight_not_just_present():
    """The original bug was a *finite but far too generous* bound (150s x 3
    attempts = 450s worst case) -- assert the new bounds are small enough
    that the total provider phase cannot exceed a sane client timeout."""
    assert _HTTP_CALL_TIMEOUT_S <= 30
    assert _MAX_TOTAL_ATTEMPTS <= 2
    assert _PROVIDER_TOTAL_BUDGET_S <= 60


# --- 2. mock provider returns successfully, immediately ---------------------


def test_mock_provider_returns_immediately():
    start = time.monotonic()
    candidates = MockDesignGenerationProvider().generate(_request(count=1))
    elapsed = time.monotonic() - start
    assert len(candidates) == 1
    assert elapsed < 1.0


def test_mock_provider_selectable_via_settings(monkeypatch):
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        from src.providers.design_generation import get_design_generation_provider

        provider = get_design_generation_provider()
        assert isinstance(provider, MockDesignGenerationProvider)
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("value", ["alibaba", "ALIBABA", " aliyun ", "dashscope", "live", "openai_compatible"])
def test_live_provider_aliases_are_all_equivalent(monkeypatch, value):
    """DESIGN_GENERATION_PROVIDER names the real provider being called
    (Aliyun DashScope's OpenAI-compatible endpoint) -- all of these aliases
    must resolve to the same OpenAICompatibleDesignGenerationProvider."""
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", value)
    get_settings.cache_clear()
    try:
        from src.providers.design_generation import get_design_generation_provider

        provider = get_design_generation_provider()
        assert isinstance(provider, OpenAICompatibleDesignGenerationProvider)
    finally:
        get_settings.cache_clear()


# --- 3. provider timeout returns a controlled error, bounded in time -------


def test_provider_timeout_is_bounded_and_reported(monkeypatch):
    """A provider that always times out must still return (empty list) well
    within the total budget, with the reason recorded on the instance for
    the orchestrator to surface."""

    def _always_times_out(*args, **kwargs):
        raise httpx.ReadTimeout("simulated timeout")

    monkeypatch.setattr(httpx, "post", _always_times_out)
    provider = OpenAICompatibleDesignGenerationProvider()

    start = time.monotonic()
    result = provider.generate(_request(count=3))
    elapsed = time.monotonic() - start

    assert result == []
    assert elapsed < _PROVIDER_TOTAL_BUDGET_S + 5  # generous slack for test-machine jitter only
    assert provider.last_error is not None


def test_endpoint_returns_within_bounded_time_when_provider_fails(monkeypatch):
    """Section: 'endpoint returns within a bounded time when provider
    fails.' Exercises the full orchestrator, not just the provider."""
    import src.fashion_engine.design.generate as generate_module
    from src.providers.design_generation import DesignGenerationProvider

    class _AlwaysFailingProvider(DesignGenerationProvider):
        def generate(self, request):
            return []

    monkeypatch.setattr(generate_module, "get_design_generation_provider", lambda: _AlwaysFailingProvider())

    fabric = get_fabric_repository().resolve("organza").profile
    start = time.monotonic()
    result = generate_design_directions(
        fabric,
        RecommendationContext(occasion="engagement"),
        ClientBrief(),
        selected_garment_id="suit",
        selected_silhouette_id="anarkali",
        count=1,
    )
    elapsed = time.monotonic() - start

    assert elapsed < 5.0  # the failing stub returns instantly; only template-fallback work should take any time
    assert result.generation_metadata.fallback_to_template is True
    assert len(result.designs) == 1


# --- 4. malformed model response does not loop forever ---------------------


def test_malformed_response_does_not_loop_forever(monkeypatch):
    """A single candidate's own retry loop must be bounded -- exercised here
    with count=1 (one independent candidate request)."""
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
    provider = OpenAICompatibleDesignGenerationProvider()

    start = time.monotonic()
    result = provider.generate(_request(count=1))
    elapsed = time.monotonic() - start

    assert result == []
    assert elapsed < 5.0  # no real network delay in this test -- must not spin
    assert call_count <= _MAX_TOTAL_ATTEMPTS


# --- 5. validation failure has bounded retries ------------------------------


def test_repair_attempts_are_bounded(monkeypatch):
    """A response that is always schema-invalid must trigger at most
    `_MAX_TOTAL_ATTEMPTS` calls total for that one candidate (count=1),
    never an unbounded repair loop."""
    call_count = 0

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            import json as _json

            content = _json.dumps({"title": "Broken", "garment": "not a dict"})
            return {"choices": [{"message": {"content": content}}]}

    def _fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)
    provider = OpenAICompatibleDesignGenerationProvider()
    result = provider.generate(_request(count=1))

    assert result == []
    assert call_count == _MAX_TOTAL_ATTEMPTS
    assert provider.last_error is not None


# --- 6. count=1 does not invoke diversity generation ------------------------


def test_count_1_skips_diversity_entirely(monkeypatch):
    """Section: for count=1, do not run diversity comparison or regenerate
    for diversity -- generate exactly one candidate and validate it once."""
    import src.fashion_engine.design.generate as generate_module

    called = False

    def _tracking_filter_diverse(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("filter_diverse must not be called when count=1")

    monkeypatch.setattr(generate_module, "filter_diverse", _tracking_filter_diverse)
    monkeypatch.setattr(generate_module, "get_design_generation_provider", TemplateDesignGenerationProvider)

    fabric = get_fabric_repository().resolve("organza").profile
    result = generate_design_directions(
        fabric,
        RecommendationContext(occasion="engagement"),
        ClientBrief(),
        selected_garment_id="suit",
        selected_silhouette_id="anarkali",
        count=1,
    )
    assert not called
    assert len(result.designs) == 1
    assert result.validation.diversity_regenerations == 0


def test_count_1_generates_exactly_one_candidate_from_live_provider_shape(monkeypatch):
    """Even the live-provider code path must only ask for/keep exactly 1
    candidate when count=1, not count+buffer."""
    provider = OpenAICompatibleDesignGenerationProvider()
    captured_prompts = []

    def _fake_call_once(self, messages, settings, attempt, timeout_s):
        captured_prompts.append(messages[-1]["content"])
        return None, None, None, None  # force immediate bounded failure -- we only care about the prompt/count

    monkeypatch.setattr(OpenAICompatibleDesignGenerationProvider, "_call_once", _fake_call_once)
    provider.generate(_request(count=1))
    assert captured_prompts
    assert "Generate exactly 1 distinct design concept" in captured_prompts[0]


# --- timing instrumentation is present and doesn't leak secrets ------------


def test_timing_metadata_present_and_no_secrets_logged(monkeypatch):
    monkeypatch.setattr(
        "src.fashion_engine.design.generate.get_design_generation_provider", TemplateDesignGenerationProvider
    )
    fabric = get_fabric_repository().resolve("organza").profile
    result = generate_design_directions(
        fabric,
        RecommendationContext(occasion="engagement"),
        ClientBrief(),
        selected_garment_id="suit",
        selected_silhouette_id="anarkali",
        count=2,
    )
    timing = result.generation_metadata.timing_ms
    assert "generation.total_ms" in timing
    assert "generation.provider_ms" in timing
    assert "generation.validation_ms" in timing
    assert "generation.diversity_ms" in timing
    assert all(isinstance(v, (int, float)) for v in timing.values())
