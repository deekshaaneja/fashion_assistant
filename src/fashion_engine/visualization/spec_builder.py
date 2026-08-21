"""build_visualization_specification: Phase 4, sections 4, 20-24, 47. A pure
rendering PROJECTION of an existing `DesignProposal` + Phase 3
`FabricImageAnalysisResult` -- every field traces back 1:1 to a Phase 1/2/3
field. This module never invents a design decision; it only translates one
that already exists into the shape a `DesignVisualizationProvider` needs."""
from __future__ import annotations

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.domain.models.visualization import (
    BottomVisualSpec,
    ConstructionVisualSpec,
    DecorationTreatmentVisualSpec,
    DecorationVisualSpec,
    DupattaVisualSpec,
    FabricReferenceSelection,
    GarmentSpec,
    MaterialFabricSummary,
    MaterialReference,
    NecklineVisualSpec,
    PaletteVisualSpec,
    PreservationRequirements,
    SleevesVisualSpec,
    SubjectSpec,
    VisualizationOptions,
    VisualizationSpecification,
)


def fabric_preservation_instruction(spec: VisualizationSpecification, has_references: bool) -> list[str]:
    """The ONE canonical fabric-preservation instruction (Phase 4
    finalization, section 8) -- validated on the real organza acceptance
    experiment (see docs/visualization-engine.md). Every visualization
    call site should call this rather than hand-rolling its own fabric
    phrasing, so a future prompt refinement only has to happen in one
    place.

    Two things the spike proved matter concretely:
    - Keep color/motif/embroidery/density/sheen/transparency as ONE
      unified preservation clause -- splitting transparency out into a
      separate "opaque layer" sentence measurably darkened the fabric's
      perceived color as a side effect.
    - State the anti-darkening/neutral-lighting constraint explicitly;
      without it, the model has no signal against reinterpreting color
      for "styling" or dramatic lighting.
    """
    if not has_references:
        return []
    lines = [
        "Use the attached fabric photograph(s) as the ACTUAL fabric -- preserve its dominant and secondary "
        "colors, motif family/scale/density, embroidery or surface work, sheen, and transparency exactly as "
        "shown. Do not substitute a generic or different fabric, do not invent new motifs, and do not "
        "simplify existing embroidery into plain fabric.",
        "Do not darken, deepen, or increase the saturation of the fabric's color, and do not shift it toward "
        "a different hue family. Use neutral, even studio lighting -- no dramatic, warm, low-key, or "
        "high-contrast lighting that would change the fabric's perceived color.",
    ]
    pr = spec.preservation_requirements
    if pr.lined_components or pr.unlined_sheer_components:
        lines.append(
            "Where the fabric is semi-sheer or sheer, it must remain visibly translucent -- only a plain "
            "lining underneath (never the hero fabric itself) may provide body coverage."
        )
    if pr.border_placement:
        lines.append(
            f"The fabric's border belongs at: {', '.join(pr.border_placement)} -- not scattered randomly."
        )
    if pr.motif_directional:
        lines.append(
            "The motif has a clear directional orientation -- keep it consistently oriented, not rotated."
        )
    return lines


def border_placements(design: DesignProposal) -> list[str]:
    """Section 20: state explicitly where a used border belongs -- never
    leave it to the renderer to scatter motifs randomly. Empty means this
    design doesn't call out a specific placement for it."""
    placements: list[str] = []
    if design.dupatta is not None and design.dupatta.included and design.dupatta.border:
        placements.append("dupatta_edge")
    hem = (design.construction.hem_treatment or "").lower()
    if "border" in hem or "bordered" in hem:
        placements.append("hem")
    if any("cuff" in p.lower() for t in design.decoration.treatments for p in t.placement) and "border" in hem:
        placements.append("sleeve_cuff")
    return placements


def material_fabric_summary(image_analysis: FabricImageAnalysisResult) -> MaterialFabricSummary:
    observation = image_analysis.analysis
    properties = image_analysis.fabric_profile.properties
    top_color = observation.dominant_colors[0].name if observation.dominant_colors else None
    top_motif = observation.motifs[0].motif_type if observation.motifs else None
    any_directional = any(m.directional for m in observation.motifs) if observation.motifs else None
    return MaterialFabricSummary(
        dominant_color=top_color,
        transparency=properties.transparency,
        sheen=properties.sheen,
        surface_density=properties.surface_density,
        motif_family=top_motif,
        motif_directional=properties.motif_directional
        if properties.motif_directional is not None
        else any_directional,
        border_present=properties.border_available if properties.border_available is not None else (
            observation.border.present if observation.border else None
        ),
    )


def _palette_spec(design: DesignProposal, image_analysis: FabricImageAnalysisResult) -> PaletteVisualSpec:
    if design.palette is not None:
        return PaletteVisualSpec(
            harmony_strategy=design.palette.harmony_strategy,
            colors={component: color.hex for component, color in design.palette.colors.items()},
        )
    # Section 24: no colorway selected -- default to the observed/reference
    # fabric color rather than inventing one.
    observation = image_analysis.analysis
    if observation.dominant_colors:
        top = observation.dominant_colors[0]
        colors = {"main_garment": top.hex_estimate or top.name}
        return PaletteVisualSpec(harmony_strategy=None, colors=colors)
    return PaletteVisualSpec()


def build_visualization_specification(
    design: DesignProposal,
    image_analysis: FabricImageAnalysisResult,
    references: FabricReferenceSelection,
    options: VisualizationOptions,
) -> VisualizationSpecification:
    hero_image_ids = [r.image_id for r in references.selected]
    hero_summary = material_fabric_summary(image_analysis)

    materials = []
    for component in design.fabric_usage.components:
        fallback_description = design.fabric_usage.main_fabric_id if component.use_main_fabric else None
        materials.append(
            MaterialReference(
                role=component.component,
                use_hero_fabric=component.use_main_fabric,
                source_image_ids=hero_image_ids if component.use_main_fabric else [],
                fabric_description=component.fabric_description or fallback_description,
                fabric_summary=hero_summary if component.use_main_fabric else None,
            )
        )

    placements = border_placements(design)
    properties = image_analysis.fabric_profile.properties

    preservation = PreservationRequirements(
        border_placement=placements,
        motif_directional=bool(hero_summary.motif_directional),
        lined_components=["main_garment"] if design.lining.required else [],
        unlined_sheer_components=["sleeves"] if design.sleeves.sheer else [],
    )
    # preserve_border is only meaningfully actionable when the fabric
    # actually has one AND this design calls it out somewhere.
    preservation = preservation.model_copy(
        update={"preserve_border": bool(properties.border_available) and bool(placements)}
    )

    return VisualizationSpecification(
        design_id=design.id,
        subject=SubjectSpec(presentation=options.presentation, view=options.view),
        garment=GarmentSpec(
            category=design.garment.garment.id,
            category_name=design.garment.garment.name,
            silhouette=design.garment.silhouette.id,
            silhouette_name=design.garment.silhouette.name,
        ),
        construction=ConstructionVisualSpec(
            bodice=design.construction.bodice_style,
            panelling=design.construction.panelling,
            waist=design.construction.waist_placement,
            flare_level=design.construction.flare_level,
            flare_construction=design.construction.flare_construction,
            length=design.construction.garment_length,
            hem=design.construction.hem_treatment,
            slit=design.construction.slit,
        ),
        neckline=NecklineVisualSpec(type=design.neckline.type, depth=design.neckline.depth),
        sleeves=SleevesVisualSpec(
            length=design.sleeves.length,
            style=design.sleeves.style,
            sheer=design.sleeves.sheer,
            cuff_treatment=design.sleeves.cuff_treatment,
        ),
        bottom=BottomVisualSpec(type=design.bottom.type, fabric_role=design.bottom.fabric_role)
        if design.bottom
        else None,
        dupatta=DupattaVisualSpec(
            included=design.dupatta.included,
            fabric_role=design.dupatta.fabric_role,
            transparency=design.dupatta.transparency,
            color_strategy=design.dupatta.color_strategy,
            border=design.dupatta.border,
            embellishment=design.dupatta.embellishment,
            ombre_direction=design.dupatta.ombre_direction,
        )
        if design.dupatta
        else None,
        decoration=DecorationVisualSpec(
            level=design.decoration.level,
            treatments=[
                DecorationTreatmentVisualSpec(material=t.material, intensity=t.intensity, placement=t.placement)
                for t in design.decoration.treatments
            ],
        ),
        materials=materials,
        palette=_palette_spec(design, image_analysis),
        preservation_requirements=preservation,
    )
