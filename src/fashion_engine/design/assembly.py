"""assemble_candidate: the single deterministic assembly step shared by
every `DesignGenerationProvider` (Phase 2 performance fix, section 3/7;
Phase 3.1, sections 2-9 preserve creative intent within this same step).

A provider's only job is to produce a `GeneratedDesignContent` -- the
creative subset of a design. Everything genuinely deterministic or
derivable from `DesignConstraints`/the resolved (fabric, garment,
silhouette) is forced here, never trusted from the model:
neckline.lining_required, lining, finishing, fabric_usage.consumption, and
the garment/silhouette reference block.

flare_level/flare_construction, decoration treatments, and dupatta
weight/transparency/border/embellishment/ombre_direction are, by contrast,
genuine creative proposals (Phase 3.1) -- a provider MAY leave them unset
(DEFAULT: filled deterministically), but a valid, in-bounds proposal always
survives assembly rather than being silently overwritten. Structural
ceilings (the fabric's flare-level capacity, its decoration/embellishment
ceiling) are still enforced -- HARD for what a fabric structurally cannot
support, never for a merely non-default creative choice.
"""
from __future__ import annotations

from src.domain.enums import DecorationLevel, EmbellishmentTolerance, EmbellishmentType, FlareLevel
from src.domain.models.design_generation import DesignConstraints
from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
    DecorationTreatment,
    DesignCandidate,
    DesignGarment,
    DupattaSpec,
    FabricRole,
    FabricUsageSpec,
    FinishingSpec,
    GeneratedDesignContent,
    LiningSpec,
    NecklineSpec,
)
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment, Silhouette
from src.domain.models.recommendation import GarmentRef, SilhouetteRef
from src.fashion_engine.design.coherence import normalize_coherence
from src.fashion_engine.design.decoration import treatments_for_level
from src.rules.repository import get_embellishment_repository

_LEVEL_ORDER = [
    DecorationLevel.NO_ADDITIONAL_DECORATION,
    DecorationLevel.MINIMAL,
    DecorationLevel.MODERATE,
    DecorationLevel.STATEMENT,
]

_FLARE_LEVEL_ORDER = [FlareLevel.MINIMAL, FlareLevel.MODERATE, FlareLevel.HIGH, FlareLevel.DRAMATIC]
_TOLERANCE_ORDER = [EmbellishmentTolerance.LOW, EmbellishmentTolerance.MEDIUM, EmbellishmentTolerance.HIGH]

# Techniques with no catalog entry (finishing details, not surface
# embellishment density -- piping, buttons, tassels, latkans, "none") carry
# no tolerance requirement of their own; anything else is checked against the
# fabric's own embellishment_tolerance via the embellishment repository.
_NO_TOLERANCE_REQUIREMENT = {"piping", "buttons", "tassels", "latkans", "none"}


def _supporting_fabric(content: GeneratedDesignContent, component: str):
    return next((sf for sf in content.supporting_fabrics if sf.component == component), None)


def _assemble_lining(
    fabric: Fabric, constraints: DesignConstraints, content: GeneratedDesignContent
) -> LiningSpec:
    if not constraints.requires_lining:
        return LiningSpec(
            required=False, fabric_description=None, rationale="No lining needed at this transparency."
        )
    supporting = _supporting_fabric(content, "lining")
    fabric_description = supporting.fabric_description if supporting else "soft crepe lining"
    return LiningSpec(
        required=True,
        fabric_description=fabric_description,
        rationale=f"{fabric.name}'s transparency needs a lining for coverage integrity.",
    )


def _assemble_dupatta(fabric: Fabric, content: GeneratedDesignContent) -> DupattaSpec | None:
    """Phase 3.1, section 8: preserves whatever the creative source (model
    or archetype) proposed -- weight/transparency/border/embellishment/
    ombre_direction are no longer forced to None; assembly only fills in a
    DEFAULT for a field the proposal genuinely left unset."""
    if content.dupatta is None:
        return None
    if not content.dupatta.included:
        # Excluded means excluded -- any attribute the model still attached
        # is a bookkeeping slip, not a creative decision.
        return DupattaSpec(included=False, rationale=content.dupatta.rationale)

    fabric_description = content.dupatta.fabric_description
    if fabric_description is None:
        supporting = _supporting_fabric(content, "dupatta")
        if supporting is not None:
            fabric_description = supporting.fabric_description

    heavy_or_dense = fabric.properties.weight_class == "heavy" or fabric.properties.surface_density == "dense"
    fabric_role = content.dupatta.fabric_role or ("supporting" if heavy_or_dense else "main")

    weight = content.dupatta.weight
    if weight is None:
        weight = "light" if fabric_role == "supporting" else None
    transparency = content.dupatta.transparency
    if transparency is None:
        transparency = "semi_sheer" if fabric_role == "supporting" else fabric.properties.transparency

    return DupattaSpec(
        included=True,
        fabric_role=fabric_role,
        fabric_description=fabric_description,
        weight=weight,
        transparency=transparency,
        color_strategy=content.dupatta.color_strategy,
        border=content.dupatta.border,
        embellishment=content.dupatta.embellishment,
        ombre_direction=content.dupatta.ombre_direction,
        rationale=content.dupatta.rationale,
    )


def _technique_min_tolerance(material: EmbellishmentType) -> EmbellishmentTolerance | None:
    """None means no tolerance requirement applies -- either a finishing
    detail rather than a surface-density embellishment (piping, buttons,
    tassels, latkans, "none"), or a technique with no catalog entry, treated
    permissively since incompatibility can't be honestly claimed either."""
    if material in _NO_TOLERANCE_REQUIREMENT:
        return None
    technique = next((e for e in get_embellishment_repository().all() if e.type == material), None)
    return technique.min_fabric_embellishment_tolerance if technique is not None else None


def _intensity_exceeds(intensity: str, ceiling: DecorationLevel) -> bool:
    normalized = intensity.strip().upper()
    if normalized not in DecorationLevel.__members__:
        return False  # can't evaluate an unrecognized intensity string -- don't reject on it alone
    return _LEVEL_ORDER.index(DecorationLevel[normalized]) > _LEVEL_ORDER.index(ceiling)


def _treatment_is_compatible(fabric: Fabric, treatment: DecorationTreatment, ceiling: DecorationLevel) -> bool:
    if _intensity_exceeds(treatment.intensity, ceiling):
        return False
    min_tolerance = _technique_min_tolerance(treatment.material)
    if min_tolerance is None:
        return True
    fabric_tolerance = fabric.properties.embellishment_tolerance
    if fabric_tolerance is None:
        return False
    fabric_idx = _TOLERANCE_ORDER.index(EmbellishmentTolerance(fabric_tolerance))
    return fabric_idx >= _TOLERANCE_ORDER.index(min_tolerance)


def _assemble_decoration(
    fabric: Fabric, constraints: DesignConstraints, content: GeneratedDesignContent
) -> DecorationSpec:
    """Phase 3.1, sections 6-7: a creative treatment proposal is validated
    against the fabric's own ceiling/tolerance and preserved as-is when
    compatible. The deterministic treatment is used only as a fallback --
    no proposal at all, or every proposed treatment fails validation -- and
    that fallback is always recorded (`source`), never silent."""
    ceiling = DecorationLevel(constraints.max_embellishment_intensity)
    requested = DecorationLevel(content.decoration.level)
    capped_idx = min(_LEVEL_ORDER.index(requested), _LEVEL_ORDER.index(ceiling))
    final_level = _LEVEL_ORDER[capped_idx]
    level_capped = final_level != requested

    rationale = content.decoration.rationale
    if level_capped:
        rationale = f"{rationale} Capped to {final_level.value.lower()} -- the fabric's surface can't take more."

    if final_level == DecorationLevel.NO_ADDITIONAL_DECORATION:
        return DecorationSpec(
            level=final_level, treatments=[], rationale=rationale, source="model", level_capped=level_capped
        )

    proposed = content.decoration.treatments or []
    valid_treatments = [t for t in proposed if _treatment_is_compatible(fabric, t, final_level)]
    dropped = len(proposed) - len(valid_treatments)

    if valid_treatments:
        return DecorationSpec(
            level=final_level,
            treatments=valid_treatments,
            rationale=rationale,
            source="model",
            level_capped=level_capped,
            invalid_treatments_dropped=dropped,
        )

    fallback_rationale = rationale
    if dropped:
        fallback_rationale = (
            f"{rationale} The proposed treatment(s) didn't suit this fabric's tolerance -- substituted a "
            "deterministic treatment within its ceiling instead."
        )
    return DecorationSpec(
        level=final_level,
        treatments=treatments_for_level(fabric, final_level),
        rationale=fallback_rationale,
        source="deterministic_fallback",
        level_capped=level_capped,
        invalid_treatments_dropped=dropped,
    )


def _assemble_fabric_usage(
    fabric: Fabric,
    constraints: DesignConstraints,
    dupatta: DupattaSpec | None,
    lining: LiningSpec,
    content: GeneratedDesignContent,
) -> FabricUsageSpec:
    components = [
        FabricRole(component="main_garment", use_main_fabric=True, rationale=f"{fabric.name} is the hero fabric.")
    ]
    handled = {"main_garment"}

    if dupatta is not None and dupatta.included and dupatta.fabric_role == "supporting":
        dupatta_properties = {
            "weight_class": dupatta.weight or "light",
            "transparency": dupatta.transparency or "semi_sheer",
        }
        components.append(
            FabricRole(
                component="dupatta",
                use_main_fabric=False,
                fabric_description=dupatta.fabric_description,
                recommended_properties=dupatta_properties,
                rationale=dupatta.rationale,
            )
        )
        handled.add("dupatta")
    elif dupatta is not None and dupatta.included:
        components.append(FabricRole(component="dupatta", use_main_fabric=True, rationale=dupatta.rationale))
        handled.add("dupatta")

    if lining.required:
        components.append(
            FabricRole(
                component="lining",
                use_main_fabric=False,
                fabric_description=lining.fabric_description or "soft, breathable lining fabric",
                recommended_properties={"weight_class": "light"},
                rationale=lining.rationale,
            )
        )
        handled.add("lining")

    for suggestion in content.supporting_fabrics:
        if suggestion.component in handled:
            continue
        handled.add(suggestion.component)
        components.append(
            FabricRole(
                component=suggestion.component,
                use_main_fabric=False,
                fabric_description=suggestion.fabric_description,
                rationale=suggestion.rationale,
            )
        )

    return FabricUsageSpec(main_fabric_id=fabric.id, components=components, consumption=constraints.consumption)


def assemble_candidate(
    content: GeneratedDesignContent,
    fabric: Fabric,
    garment: Garment,
    silhouette: Silhouette,
    constraints: DesignConstraints,
) -> DesignCandidate:
    """Combines model/archetype-generated creative content with everything
    deterministic into a full `DesignCandidate` -- the one place that split
    happens, shared by every `DesignGenerationProvider`."""

    ceiling = FlareLevel(constraints.effective_flare_level)
    flare_level = content.construction.flare_level
    flare_capped = False
    if flare_level is None:
        flare_level = ceiling  # DEFAULT -- no creative preference stated
    elif _FLARE_LEVEL_ORDER.index(flare_level) > _FLARE_LEVEL_ORDER.index(ceiling):
        flare_capped = True
        flare_level = ceiling  # HARD -- the fabric's own body sets this ceiling, never just a validation reject

    flare_construction = content.construction.flare_construction or constraints.flare_construction

    construction = ConstructionSpec(
        bodice_style=content.construction.bodice_style,
        panelling=content.construction.panelling,
        waist_placement=content.construction.waist_placement,
        flare_level=flare_level,
        flare_construction=flare_construction,
        garment_length=content.construction.garment_length,
        hem_treatment=content.construction.hem_treatment,
        slit=content.construction.slit,
        rationale=content.construction.rationale,
    )
    neckline = NecklineSpec(
        type=content.neckline.type,
        depth=content.neckline.depth,
        lining_required=constraints.requires_lining,
        rationale=content.neckline.rationale,
    )
    lining = _assemble_lining(fabric, constraints, content)
    dupatta = _assemble_dupatta(fabric, content)
    decoration = _assemble_decoration(fabric, constraints, content)
    fabric_usage = _assemble_fabric_usage(fabric, constraints, dupatta, lining, content)
    finishing = FinishingSpec(
        seams=(
            "clean finished seams with piped edges"
            if fabric.properties.transparency in ("sheer", "semi_sheer")
            else "clean finished seams"
        )
    )

    risks = list(content.risks)
    if constraints.hard_avoid:
        avoided = ", ".join(constraints.hard_avoid)
        risks.append(f"Toned down from {avoided} -- the fabric's own body sets the ceiling.")
    if flare_capped:
        risks.append(
            f"Requested flare level was capped to '{flare_level.value}' -- the fabric's own body sets this "
            "ceiling."
        )
    if fabric.properties.transparency == "sheer" and not lining.required:
        risks.append(f"{fabric.name} is sheer -- confirm coverage is adequate without lining here.")

    candidate = DesignCandidate(
        title=content.title,
        design_intent=content.design_intent,
        garment=DesignGarment(
            garment=GarmentRef(id=garment.id, name=garment.name),
            silhouette=SilhouetteRef(id=silhouette.id, name=silhouette.name),
        ),
        design_dna=content.design_dna,
        construction=construction,
        neckline=neckline,
        sleeves=content.sleeves,
        bottom=content.bottom,
        dupatta=dupatta,
        lining=lining,
        decoration=decoration,
        finishing=finishing,
        fabric_usage=fabric_usage,
        rationale=list(content.rationale),
        risks=risks,
    )

    candidate, coherence_notes = normalize_coherence(candidate)
    if coherence_notes:
        candidate = candidate.model_copy(update={"risks": [*candidate.risks, *coherence_notes]})
    return candidate
