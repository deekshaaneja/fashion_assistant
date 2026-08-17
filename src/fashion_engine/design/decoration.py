"""recommend_decoration: Phase 2, section 13-14. Must be genuinely capable of
returning NO_ADDITIONAL_DECORATION -- occasion never automatically implies
heavy decoration (preserving the Phase 1.1 principle, section 13 of this
brief). Reuses Phase 1's EmbellishmentRepository rather than duplicating
embellishment-technique knowledge."""
from __future__ import annotations

from src.domain.enums import DecorationLevel
from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import DecorationSpec, DecorationTreatment
from src.domain.models.fabric import Fabric
from src.rules.repository import get_embellishment_repository

_LEVEL_ORDER = [
    DecorationLevel.NO_ADDITIONAL_DECORATION,
    DecorationLevel.MINIMAL,
    DecorationLevel.MODERATE,
    DecorationLevel.STATEMENT,
]

_PHILOSOPHY_LEVEL = {
    "restrained_frame": DecorationLevel.MINIMAL,
    "clean_minimal_or_none": DecorationLevel.NO_ADDITIONAL_DECORATION,
    "none_or_barely_there": DecorationLevel.NO_ADDITIONAL_DECORATION,
    "rich_traditional": DecorationLevel.MODERATE,
    "focal_statement": DecorationLevel.MODERATE,
    "selective_on_overlay": DecorationLevel.MINIMAL,
}

_PLACEMENT_BY_LEVEL = {
    DecorationLevel.MINIMAL: ["neckline edge", "sleeve cuff"],
    DecorationLevel.MODERATE: ["neckline", "hemline", "sleeve cuff"],
    DecorationLevel.STATEMENT: ["bodice focal panel", "hemline"],
}


def max_embellishment_intensity(fabric: Fabric) -> DecorationLevel:
    """The CEILING this fabric's own surface can carry -- a dense or
    low-tolerance fabric lowers the ceiling; it never raises it just because
    the occasion is formal."""
    if fabric.properties.surface_density == "dense" or fabric.properties.embellishment_tolerance == "low":
        return DecorationLevel.MINIMAL
    if fabric.properties.embellishment_tolerance == "high" and fabric.properties.surface_density in (
        "none",
        "sparse",
    ):
        return DecorationLevel.STATEMENT
    return DecorationLevel.MODERATE


def treatments_for_level(fabric: Fabric, level: DecorationLevel) -> list[DecorationTreatment]:
    """Deterministically derive decoration treatments for an (already
    clamped) level -- shared by `recommend_decoration` and
    `assemble_candidate` so treatment selection never has to be duplicated
    or, worse, asked of the generation model."""
    if level == DecorationLevel.NO_ADDITIONAL_DECORATION:
        return []

    tolerance = fabric.properties.embellishment_tolerance or "low"
    techniques = get_embellishment_repository().suitable_for_tolerance(tolerance)
    if not techniques:
        return []

    return [
        DecorationTreatment(
            material=techniques[0].type,
            intensity=level.value.lower(),
            placement=_PLACEMENT_BY_LEVEL[level],
            reason=f"{fabric.name} comfortably supports {level.value.lower()} work.",
        )
    ]


def recommend_decoration(
    fabric: Fabric,
    archetype_decoration_philosophy: str,
    client_brief: ClientBrief,
) -> DecorationSpec:
    reasons: list[str] = []
    ceiling = max_embellishment_intensity(fabric)

    if fabric.properties.surface_density == "dense":
        reasons.append(
            f"{fabric.name} already carries dense surface work -- additional decoration should frame rather "
            "than compete with it."
        )
    if fabric.properties.embellishment_tolerance == "low":
        reasons.append(f"{fabric.name} has low embellishment tolerance -- keep any added work minimal, edge-only.")

    level = _PHILOSOPHY_LEVEL.get(archetype_decoration_philosophy, DecorationLevel.MINIMAL)

    if client_brief.embellishment_preference == "none":
        level = DecorationLevel.NO_ADDITIONAL_DECORATION
        reasons.append("Client asked for no additional embellishment.")
    elif client_brief.embellishment_preference == "heavy":
        level = DecorationLevel.STATEMENT if ceiling == DecorationLevel.STATEMENT else DecorationLevel.MODERATE
        reasons.append("Client asked for a statement level of embellishment.")

    capped_idx = min(_LEVEL_ORDER.index(level), _LEVEL_ORDER.index(ceiling))
    final_level = _LEVEL_ORDER[capped_idx]
    if final_level != level:
        reasons.append(f"Capped to {final_level.value.lower()} -- the fabric's surface can't take more.")

    if final_level == DecorationLevel.NO_ADDITIONAL_DECORATION:
        return DecorationSpec(
            level=final_level,
            treatments=[],
            rationale=" ".join(reasons) or "The fabric and cut carry this design on their own.",
        )

    treatments = treatments_for_level(fabric, final_level)

    return DecorationSpec(
        level=final_level,
        treatments=treatments,
        rationale=" ".join(reasons) or f"{final_level.value.title()} decoration suits this direction.",
    )
