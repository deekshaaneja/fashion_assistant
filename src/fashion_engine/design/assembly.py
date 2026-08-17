"""assemble_candidate: the single deterministic assembly step shared by
every `DesignGenerationProvider` (Phase 2 performance fix, section 3/7).

A provider's only job is to produce a `GeneratedDesignContent` -- the
creative subset of a design. Everything deterministic or derivable from
`DesignConstraints`/the resolved (fabric, garment, silhouette) is forced
here, never trusted from the model: flare_level/flare_construction,
neckline.lining_required, decoration.treatments (and the decoration level
itself is clamped to the fabric's ceiling, never just validated after the
fact), lining, finishing, fabric_usage.consumption, and the garment/
silhouette reference block.
"""
from __future__ import annotations

from src.domain.enums import DecorationLevel
from src.domain.models.design_generation import DesignConstraints
from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
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
from src.fashion_engine.design.decoration import treatments_for_level

_LEVEL_ORDER = [
    DecorationLevel.NO_ADDITIONAL_DECORATION,
    DecorationLevel.MINIMAL,
    DecorationLevel.MODERATE,
    DecorationLevel.STATEMENT,
]


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


def _assemble_dupatta(content: GeneratedDesignContent) -> DupattaSpec | None:
    if content.dupatta is None:
        return None
    fabric_description = content.dupatta.fabric_description
    if fabric_description is None:
        supporting = _supporting_fabric(content, "dupatta")
        if supporting is not None:
            fabric_description = supporting.fabric_description
    return DupattaSpec(
        included=content.dupatta.included,
        fabric_role=content.dupatta.fabric_role,
        fabric_description=fabric_description,
        weight=None,
        transparency=None,
        color_strategy=content.dupatta.color_strategy,
        border=None,
        embellishment=None,
        ombre_direction=None,
        rationale=content.dupatta.rationale,
    )


def _assemble_decoration(
    fabric: Fabric, constraints: DesignConstraints, content: GeneratedDesignContent
) -> DecorationSpec:
    ceiling = DecorationLevel(constraints.max_embellishment_intensity)
    requested = DecorationLevel(content.decoration.level)
    capped_idx = min(_LEVEL_ORDER.index(requested), _LEVEL_ORDER.index(ceiling))
    final_level = _LEVEL_ORDER[capped_idx]

    rationale = content.decoration.rationale
    if final_level != requested:
        rationale = f"{rationale} Capped to {final_level.value.lower()} -- the fabric's surface can't take more."

    treatments = treatments_for_level(fabric, final_level)
    return DecorationSpec(level=final_level, treatments=treatments, rationale=rationale)


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
        dupatta_properties = {"weight_class": "light", "transparency": dupatta.transparency or "semi_sheer"}
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

    construction = ConstructionSpec(
        bodice_style=content.construction.bodice_style,
        panelling=content.construction.panelling,
        waist_placement=content.construction.waist_placement,
        flare_level=constraints.effective_flare_level,
        flare_construction=constraints.flare_construction,
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
    dupatta = _assemble_dupatta(content)
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
    if fabric.properties.transparency == "sheer" and not lining.required:
        risks.append(f"{fabric.name} is sheer -- confirm coverage is adequate without lining here.")

    return DesignCandidate(
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
