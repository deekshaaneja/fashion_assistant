"""Phase 3.1: proves that a valid, non-default creative proposal survives
`assemble_candidate` unchanged (sections 2-3, 6, 8), rather than being
silently overwritten by a deterministic default."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import (
    ConstructionCreative,
    DecorationCreative,
    DecorationTreatment,
    DupattaCreative,
    GeneratedDesignContent,
    NecklineCreative,
    SleeveSpec,
)
from src.fashion_engine.design.assembly import assemble_candidate
from src.fashion_engine.design.constraints import build_design_constraints
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository


def _setup(fabric_name="georgette", garment_id="suit", silhouette_id="anarkali"):
    fabric = get_fabric_repository().resolve(fabric_name).profile
    garment = get_garment_repository().get(garment_id)
    silhouette = get_silhouette_repository().get(silhouette_id)
    context = RecommendationContext(occasion="engagement")
    brief = ClientBrief()
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)
    return fabric, garment, silhouette, constraints


def _content(**overrides) -> GeneratedDesignContent:
    defaults = dict(
        title="Architectural Panelled Anarkali",
        design_intent="A controlled, architectural reading of the Anarkali.",
        construction=ConstructionCreative(
            bodice_style="structured, clean-seamed",
            panelling="vertical princess-line panels, tailored",
            garment_length="floor_length",
            rationale="A restrained, architectural read of this silhouette.",
        ),
        neckline=NecklineCreative(type="boat", rationale="r"),
        sleeves=SleeveSpec(length="three_quarter", rationale="r"),
        decoration=DecorationCreative(level="MINIMAL", rationale="r"),
        design_dna=DesignDNA(),
        rationale=["r"],
        risks=[],
    )
    defaults.update(overrides)
    return GeneratedDesignContent(**defaults)


def test_non_default_flare_level_and_construction_survive_assembly():
    """A lower flare level than the ceiling, and a flare_construction that
    deviates from the silhouette's own default, are both valid creative
    choices that must survive assembly (section 2-3) -- not get silently
    forced back to the fabric's ceiling / this silhouette's default."""
    fabric, garment, silhouette, constraints = _setup()
    assert constraints.effective_flare_level == "high"  # georgette's own ceiling for an anarkali
    assert constraints.flare_construction == "gathered"  # the silhouette's own default

    content = _content(
        construction=ConstructionCreative(
            bodice_style="structured, clean-seamed",
            panelling="vertical princess-line panels, tailored",
            garment_length="floor_length",
            flare_level="moderate",  # below the "high" ceiling -- restrained by choice
            flare_construction="controlled",  # deviates from this silhouette's own "gathered"
            rationale="A restrained, architectural read of this silhouette.",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)

    assert candidate.construction.flare_level == "moderate"
    assert candidate.construction.flare_construction == "controlled"
    assert candidate.construction.panelling == "vertical princess-line panels, tailored"
    assert not any("capped" in risk.lower() for risk in candidate.risks)


def test_flare_level_exceeding_ceiling_is_clamped_not_silently_rejected():
    fabric, garment, silhouette, constraints = _setup()
    content = _content(
        construction=ConstructionCreative(
            bodice_style="fitted",
            garment_length="floor_length",
            flare_level="dramatic",  # above the "high" ceiling
            rationale="r",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)
    assert candidate.construction.flare_level == constraints.effective_flare_level
    assert any("capped" in risk.lower() for risk in candidate.risks)


def test_unset_flare_fields_default_to_constraints():
    fabric, garment, silhouette, constraints = _setup()
    content = _content()  # flare_level/flare_construction left unset
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)
    assert candidate.construction.flare_level == constraints.effective_flare_level
    assert candidate.construction.flare_construction == constraints.flare_construction


def test_valid_model_proposed_decoration_treatment_survives_assembly():
    """Section 6-7: georgette has medium embellishment_tolerance and a
    MODERATE ceiling here -- a moderate-intensity zari treatment is
    compatible and must be preserved verbatim, not replaced by
    `treatments_for_level`'s own generic pick."""
    fabric, garment, silhouette, constraints = _setup()
    assert constraints.max_embellishment_intensity == "MODERATE"

    content = _content(
        decoration=DecorationCreative(
            level="MODERATE",
            treatments=[
                DecorationTreatment(
                    material="zari",
                    intensity="moderate",
                    placement=["princess seams"],
                    reason="Reinforces the architectural panel lines without competing with the fabric.",
                )
            ],
            rationale="Tonal threadwork along the panel lines.",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)

    assert candidate.decoration.source == "model"
    assert candidate.decoration.invalid_treatments_dropped == 0
    assert len(candidate.decoration.treatments) == 1
    assert candidate.decoration.treatments[0].material == "zari"
    assert candidate.decoration.treatments[0].placement == ["princess seams"]


def test_incompatible_decoration_treatment_falls_back_deterministically():
    """cutdana requires HIGH embellishment tolerance -- georgette only has
    MEDIUM, so this proposal cannot be honored; assembly must fall back to a
    deterministic, in-bounds treatment and record that it did so."""
    fabric, garment, silhouette, constraints = _setup()
    content = _content(
        decoration=DecorationCreative(
            level="MODERATE",
            treatments=[
                DecorationTreatment(material="cutdana", intensity="moderate", placement=["hem"], reason="r")
            ],
            rationale="r",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)

    assert candidate.decoration.source == "deterministic_fallback"
    assert candidate.decoration.invalid_treatments_dropped == 1
    assert candidate.decoration.treatments != []


def test_no_proposal_falls_back_to_deterministic_decoration():
    fabric, garment, silhouette, constraints = _setup()
    content = _content(decoration=DecorationCreative(level="MODERATE", rationale="r"))
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)
    assert candidate.decoration.source == "deterministic_fallback"
    assert candidate.decoration.invalid_treatments_dropped == 0
    assert candidate.decoration.treatments != []


def test_dupatta_visual_attributes_survive_into_final_proposal():
    """Section 8: weight/transparency/border/embellishment/ombre_direction
    are genuine creative proposals now -- they must reach the final
    `DesignProposal`, never nulled out."""
    fabric, garment, silhouette, constraints = _setup()
    content = _content(
        dupatta=DupattaCreative(
            included=True,
            fabric_role="main",
            fabric_description="georgette, tonal to the main garment",
            color_strategy="ombre",
            weight=None,
            transparency="semi_sheer",
            border="narrow antique-gold edge",
            embellishment="tonal threadwork edge",
            ombre_direction="wine-to-rose",
            rationale="A soft ombre drape completes the architectural silhouette.",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)

    assert candidate.dupatta.included is True
    assert candidate.dupatta.transparency == "semi_sheer"
    assert candidate.dupatta.border == "narrow antique-gold edge"
    assert candidate.dupatta.embellishment == "tonal threadwork edge"
    assert candidate.dupatta.ombre_direction == "wine-to-rose"


def test_excluded_dupatta_cannot_retain_contradictory_attributes():
    fabric, garment, silhouette, constraints = _setup()
    content = _content(
        dupatta=DupattaCreative(
            included=False,
            border="heavy contrast border",
            embellishment="zardozi edge",
            rationale="Omitted to keep the architectural line clean.",
        )
    )
    candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)
    assert candidate.dupatta.included is False
    assert candidate.dupatta.border is None
    assert candidate.dupatta.embellishment is None
