from __future__ import annotations

import httpx

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.fashion_engine.design.constraints import build_design_constraints
from src.providers.design_generation import (
    OpenAICompatibleDesignGenerationProvider,
    TemplateDesignGenerationProvider,
)
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


def test_template_provider_returns_requested_count_and_respects_constraints():
    request = _request(count=3)
    candidates = TemplateDesignGenerationProvider().generate(request)
    assert len(candidates) == 3
    for candidate in candidates:
        assert candidate.construction.flare_construction == request.constraints.flare_construction


def test_template_provider_produces_structurally_distinct_titles():
    request = _request(count=3)
    candidates = TemplateDesignGenerationProvider().generate(request)
    titles = {c.title for c in candidates}
    assert len(titles) == 3


def test_live_provider_returns_empty_list_on_repeated_network_failure(monkeypatch):
    """Section 22: model failure must never raise -- an unreachable/failing
    endpoint must degrade to an empty list so the orchestrator can fall back
    to the template provider, never crash the caller."""

    def _always_fails(*args, **kwargs):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(httpx, "post", _always_fails)
    provider = OpenAICompatibleDesignGenerationProvider()
    result = provider.generate(_request(count=3))
    assert result == []


def test_live_provider_repairs_and_discards_malformed_items(monkeypatch):
    """A response with some valid and some unrepairable items should keep
    the valid ones without raising."""
    valid_item = {
        "title": "Valid Direction",
        "design_intent": "test",
        "design_dna": {},
        "construction": {
            "bodice_style": "fitted",
            "garment_length": "floor_length",
            "rationale": "r",
        },
        "neckline": {"type": "round", "rationale": "r"},
        "sleeves": {"length": "three_quarter", "rationale": "r"},
        "decoration": {"level": "MINIMAL", "rationale": "r"},
    }

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            import json as _json

            content = _json.dumps({"candidates": [valid_item, {"title": "Broken", "garment": "not a dict"}]})
            return {"choices": [{"message": {"content": content}}]}

    def _fake_post(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)
    provider = OpenAICompatibleDesignGenerationProvider()
    request = _request(count=3)

    result = provider.generate(request)
    assert len(result) == 1
    assert result[0].title == "Valid Direction"
