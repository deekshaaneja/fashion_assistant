from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
    DesignCandidate,
    DesignGarment,
    FabricUsageSpec,
    FinishingSpec,
    NecklineSpec,
    SleeveSpec,
)
from src.domain.models.recommendation import GarmentRef, SilhouetteRef
from src.fashion_engine.consumption.calculate import calculate_consumption
from src.fashion_engine.design.constraints import build_design_constraints
from src.fashion_engine.design.scoring import _SCORE_WEIGHTS, score_candidate
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository


def _setup():
    fabric = get_fabric_repository().resolve("organza").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    context = RecommendationContext(occasion="engagement")
    brief = ClientBrief()
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)
    return fabric, garment, silhouette, context, brief, constraints


def _candidate(constraints, **decoration_overrides) -> DesignCandidate:
    consumption = calculate_consumption("suit", "a_line", size="M")
    decoration_kwargs = dict(level="MINIMAL", rationale="r")
    decoration_kwargs.update(decoration_overrides)
    return DesignCandidate(
        title="Test",
        design_intent="A test direction.",
        garment=DesignGarment(garment=GarmentRef(id="suit", name="Suit"), silhouette=SilhouetteRef(id="a_line", name="A-Line")),
        design_dna={},
        construction=ConstructionSpec(
            bodice_style="fitted",
            flare_level=constraints.effective_flare_level,
            flare_construction=constraints.flare_construction,
            garment_length="floor_length",
            rationale="r",
        ),
        neckline=NecklineSpec(type="round", rationale="r"),
        sleeves=SleeveSpec(length="three_quarter", rationale="r"),
        decoration=DecorationSpec(**decoration_kwargs),
        finishing=FinishingSpec(seams="clean"),
        fabric_usage=FabricUsageSpec(main_fabric_id="organza", consumption=consumption),
    )


def test_color_coherence_is_not_evaluated():
    fabric, garment, silhouette, context, brief, constraints = _setup()
    candidate = _candidate(constraints)
    scores = score_candidate(candidate, constraints, context, brief, sibling_dna_distances=[])
    assert scores.color_coherence is None
    assert "color_coherence" in scores.not_evaluated


def test_overall_renormalizes_over_evaluated_dimensions_only():
    """Section 12: `overall` must exclude color_coherence's weight from the
    denominator entirely rather than treating the missing dimension as a
    zero contribution."""
    fabric, garment, silhouette, context, brief, constraints = _setup()
    candidate = _candidate(constraints)
    scores = score_candidate(candidate, constraints, context, brief, sibling_dna_distances=[])

    present = {
        "fabric_design_fit": scores.fabric_design_fit,
        "aesthetic_coherence": scores.aesthetic_coherence,
        "occasion_fit": scores.occasion_fit,
        "client_brief_fit": scores.client_brief_fit,
        "construction_coherence": scores.construction_coherence,
        "surface_design_coherence": scores.surface_design_coherence,
        "originality": scores.originality,
    }
    total_weight = sum(weight for key, weight in _SCORE_WEIGHTS.items() if key in present)
    expected = sum(present[key] * _SCORE_WEIGHTS[key] for key in present) / total_weight
    assert scores.overall == round(expected, 1)


def test_surface_design_coherence_reflects_genuine_decoration_adjustment():
    """A decoration that needed capping/fallback scores lower than one that
    didn't -- a real signal, not a constant."""
    fabric, garment, silhouette, context, brief, constraints = _setup()
    clean = _candidate(constraints, level="MINIMAL", level_capped=False, invalid_treatments_dropped=0)
    adjusted = _candidate(constraints, level="MINIMAL", level_capped=True, invalid_treatments_dropped=1)

    clean_scores = score_candidate(clean, constraints, context, brief, sibling_dna_distances=[])
    adjusted_scores = score_candidate(adjusted, constraints, context, brief, sibling_dna_distances=[])
    assert clean_scores.surface_design_coherence > adjusted_scores.surface_design_coherence
