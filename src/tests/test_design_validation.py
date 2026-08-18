from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import DesignGenerationRequest
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
from src.fashion_engine.design.validation import validate_candidate
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository


def _base_request(**brief_kwargs) -> DesignGenerationRequest:
    fabric = get_fabric_repository().resolve("organza").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    context = RecommendationContext(occasion="engagement")
    brief = ClientBrief(**brief_kwargs)
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
        count=3,
    )


def _base_candidate(request: DesignGenerationRequest, **overrides) -> DesignCandidate:
    consumption = calculate_consumption(request.garment_id, request.silhouette_id, size="M")
    defaults = dict(
        title="Test Direction",
        design_intent="A test direction.",
        garment=DesignGarment(
            garment=GarmentRef(id=request.garment_id, name=request.garment_name),
            silhouette=SilhouetteRef(id=request.silhouette_id, name=request.silhouette_name),
        ),
        design_dna={},
        construction=ConstructionSpec(
            bodice_style="fitted",
            flare_level=request.constraints.effective_flare_level,
            flare_construction=request.constraints.flare_construction,
            garment_length="floor_length",
            rationale="r",
        ),
        neckline=NecklineSpec(type="round", rationale="r"),
        sleeves=SleeveSpec(length="three_quarter", rationale="r"),
        decoration=DecorationSpec(level="MINIMAL", rationale="r"),
        finishing=FinishingSpec(seams="clean"),
        fabric_usage=FabricUsageSpec(main_fabric_id=request.fabric.id, consumption=consumption),
    )
    defaults.update(overrides)
    return DesignCandidate(**defaults)


def test_valid_candidate_passes():
    request = _base_request()
    candidate = _base_candidate(request)
    assert validate_candidate(candidate, request) == []


def test_rejects_hallucinated_garment_silhouette():
    request = _base_request()
    candidate = _base_candidate(
        request,
        garment=DesignGarment(
            garment=GarmentRef(id="lehenga", name="Lehenga"),
            silhouette=SilhouetteRef(id="flared", name="Flared"),
        ),
    )
    issues = validate_candidate(candidate, request)
    assert any("mismatch" in issue for issue in issues)


def test_rejects_flare_construction_incoherent_with_flare_level():
    """Phase 3.1, section 5: a HARD-invalid construction -- 'dramatic'
    (max-volume circular/godet) construction paired with a much lower flare
    amount is structurally nonsensical regardless of who proposed it."""
    request = _base_request()
    candidate = _base_candidate(request)
    candidate.construction.flare_construction = "dramatic"  # flare_level stays at the base "moderate" ceiling
    issues = validate_candidate(candidate, request)
    assert any("flare_construction" in issue for issue in issues)


def test_accepts_flare_construction_deviation_that_stays_coherent():
    """Phase 3.1, section 2-5: a non-default flare_construction is a
    legitimate creative deviation from the silhouette's own PREFERRED
    construction, not a violation -- only genuine incoherence (checked
    above) is rejected."""
    request = _base_request()
    candidate = _base_candidate(request)
    assert request.constraints.flare_construction == "controlled"
    candidate.construction.flare_construction = "gathered"  # deviates from the silhouette's own default
    issues = validate_candidate(candidate, request)
    assert issues == []


def test_rejects_flare_level_above_the_fabric_ceiling():
    request = _base_request()
    candidate = _base_candidate(request)
    assert request.constraints.effective_flare_level == "moderate"
    candidate.construction.flare_level = "dramatic"
    issues = validate_candidate(candidate, request)
    assert any("flare_level" in issue and "ceiling" in issue for issue in issues)


def test_accepts_flare_level_below_the_fabric_ceiling():
    """Phase 3.1, section 2: a lower flare level than the ceiling is a valid
    creative restraint, never forced back up to the ceiling."""
    request = _base_request()
    candidate = _base_candidate(request)
    assert request.constraints.effective_flare_level == "moderate"
    candidate.construction.flare_level = "minimal"
    issues = validate_candidate(candidate, request)
    assert issues == []


def test_rejects_decoration_above_the_fabric_ceiling():
    # organza (declared low-tolerance, dense) has a MINIMAL ceiling
    fabric_props = {
        "drape": "crisp",
        "embellishment_tolerance": "low",
        "surface_density": "dense",
    }
    from src.domain.models.fabric import FabricProperties
    from src.fashion_engine.fabric.analyze import merge_fabric_properties

    fabric = get_fabric_repository().resolve("organza").profile
    fabric = fabric.model_copy(
        update={"properties": merge_fabric_properties(fabric.properties, FabricProperties(**fabric_props))}
    )
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    context = RecommendationContext(occasion="engagement")
    brief = ClientBrief()
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)
    request = DesignGenerationRequest(
        fabric=fabric,
        fashion_context=context,
        client_brief=brief,
        constraints=constraints,
        garment_id=garment.id,
        garment_name=garment.name,
        silhouette_id=silhouette.id,
        silhouette_name=silhouette.name,
        count=3,
    )
    candidate = _base_candidate(request, decoration=DecorationSpec(level="STATEMENT", rationale="r"))
    issues = validate_candidate(candidate, request)
    assert any("ceiling" in issue for issue in issues)


def test_rejects_sleeveless_marked_sheer():
    request = _base_request()
    candidate = _base_candidate(request, sleeves=SleeveSpec(length="sleeveless", sheer=True, rationale="r"))
    issues = validate_candidate(candidate, request)
    assert any("sleeveless" in issue for issue in issues)


def test_rejects_neckline_conflicting_with_explicit_client_preference():
    request = _base_request(preferred_neckline="v_neck")
    candidate = _base_candidate(request, neckline=NecklineSpec(type="boat", rationale="r"))
    issues = validate_candidate(candidate, request)
    assert any("neckline" in issue for issue in issues)


def test_rejects_embellishment_when_client_asked_for_none():
    request = _base_request(embellishment_preference="none")
    candidate = _base_candidate(request, decoration=DecorationSpec(level="MODERATE", rationale="r"))
    issues = validate_candidate(candidate, request)
    assert any("embellishment" in issue for issue in issues)


def test_validator_is_deterministic():
    request = _base_request()
    candidate = _base_candidate(request)
    first = validate_candidate(candidate, request)
    second = validate_candidate(candidate, request)
    assert first == second
