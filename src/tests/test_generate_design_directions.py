from __future__ import annotations

import pytest

import src.fashion_engine.design.generate as generate_module
from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.fashion_engine.design.generate import generate_design_directions
from src.providers.design_generation import TemplateDesignGenerationProvider
from src.rules.repository import get_fabric_repository


@pytest.fixture(autouse=True)
def _use_template_provider(monkeypatch):
    """These tests exercise the orchestrator's own logic (validation,
    diversity, ranking, fallback) -- they must never depend on network
    access or a live model's non-determinism, regardless of this machine's
    LLM_ENABLED setting. Only `test_falls_back_to_template_provider_when_live_provider_fails`
    overrides this further, to inject its own failing stub."""
    monkeypatch.setattr(generate_module, "get_design_generation_provider", TemplateDesignGenerationProvider)


def test_generates_requested_count_of_valid_ranked_designs():
    fabric = get_fabric_repository().resolve("organza").profile
    context = RecommendationContext(occasion="engagement", wear_category_preference="indian", size="L")
    brief = ClientBrief(desired_aesthetic=["elegant", "contemporary"])

    result = generate_design_directions(
        fabric, context, brief, selected_garment_id="suit", selected_silhouette_id="anarkali", count=3
    )
    assert len(result.designs) == 3
    ranks = [d.rank for d in result.designs]
    assert ranks == [1, 2, 3]
    assert result.validation.candidates_rejected == []


def test_designs_are_structurally_diverse():
    fabric = get_fabric_repository().resolve("organza").profile
    context = RecommendationContext(occasion="engagement")
    result = generate_design_directions(
        fabric, context, ClientBrief(), selected_garment_id="suit", selected_silhouette_id="anarkali", count=3
    )
    titles = {d.title for d in result.designs}
    assert len(titles) == 3


def test_respects_selected_silhouette():
    fabric = get_fabric_repository().resolve("georgette").profile
    result = generate_design_directions(
        fabric,
        RecommendationContext(occasion="wedding_guest"),
        ClientBrief(),
        selected_garment_id="lehenga",
        selected_silhouette_id="flared",
        count=2,
    )
    for design in result.designs:
        assert design.garment.garment.id == "lehenga"
        assert design.garment.silhouette.id == "flared"


def test_unknown_silhouette_raises_clear_error():
    fabric = get_fabric_repository().resolve("organza").profile
    with pytest.raises(ValueError, match="Unknown silhouette"):
        generate_design_directions(fabric, selected_silhouette_id="not_a_real_silhouette")


def test_falls_back_to_template_provider_when_live_provider_fails(monkeypatch):
    """Section 22: a failing generative provider must never prevent design
    generation -- the deterministic template provider is always available."""
    from src.providers.design_generation import DesignGenerationProvider

    class _AlwaysFailingProvider(DesignGenerationProvider):
        def generate(self, request):
            return []

    monkeypatch.setattr(generate_module, "get_design_generation_provider", lambda: _AlwaysFailingProvider())

    fabric = get_fabric_repository().resolve("organza").profile
    result = generate_design_directions(
        fabric,
        RecommendationContext(occasion="engagement"),
        ClientBrief(),
        selected_garment_id="suit",
        selected_silhouette_id="anarkali",
        count=3,
    )
    assert len(result.designs) == 3
    assert result.generation_metadata.fallback_to_template is True
