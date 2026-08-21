"""apply_design_transformation: Phase 4.1, Stage 3 (sections 10-14).
`DesignProposal` remains authoritative -- this stage never derives the
design from a prior visual state, it only describes the target design (or,
for an isolated follow-up edit, the specific delta) and asks the provider
to transform the CURRENT image toward it, preserving everything else
(section 11-12)."""
from __future__ import annotations

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.visualization import VisualizationImage, VisualizationOptions, VisualizationStage
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store, new_image_id
from src.fashion_engine.visualization.base_composition import content_type_for
from src.providers.visualization import ImageEditCapableProvider, ReferenceImage, VisualizationProviderResult

# Section 14: don't accumulate unbounded image edits -- past this many
# edits from the same lineage, the caller should rebuild from the material
# reference + latest DesignProposal instead of editing further.
MAX_EDIT_DEPTH = 5


def describe_full_design(design: DesignProposal) -> str:
    """The target-design description used for the FIRST transformation
    (base garment -> full DesignProposal, section 10) -- not a delta,
    since there is no prior design state yet."""
    lines = [
        f"Transform this garment into a {design.garment.silhouette.name} silhouette "
        f"({design.garment.garment.name}).",
        f"Construction: {design.construction.bodice_style} bodice, {design.construction.waist_placement} waist, "
        f"{design.construction.flare_level} flare via {design.construction.flare_construction} construction, "
        f"{design.construction.garment_length} length.",
        f"Neckline: {design.neckline.type}"
        + (f", {design.neckline.depth}" if design.neckline.depth else "") + ".",
        f"Sleeves: {design.sleeves.length}, {design.sleeves.style} style"
        + (", sheer" if design.sleeves.sheer else "")
        + (f", {design.sleeves.cuff_treatment} cuff" if design.sleeves.cuff_treatment else "")
        + ".",
    ]
    if design.bottom:
        lines.append(f"Bottom: {design.bottom.type}.")
    if design.dupatta and design.dupatta.included:
        lines.append(
            "Add a dupatta"
            + (f", {design.dupatta.color_strategy} color story" if design.dupatta.color_strategy else "")
            + (f", border: {design.dupatta.border}" if design.dupatta.border else "")
            + "."
        )
    if design.decoration.treatments:
        for t in design.decoration.treatments:
            lines.append(f"Add {t.intensity} {t.material} decoration at {', '.join(t.placement) or 'as shown'}.")
    lines.append(
        "Keep the exact same fabric print, color, and surface texture, the same mannequin/pose, and the "
        "same background -- change only what's described above."
    )
    return "\n".join(lines)


def describe_targeted_change(change_instruction: str) -> str:
    """For an isolated follow-up edit (section 12, 22) -- ONE change, with
    an explicit instruction to leave everything else untouched."""
    return (
        f"Change ONLY the following: {change_instruction}. Keep the exact same fabric print, color, "
        "silhouette, and every other garment attribute, the same mannequin/pose, and the same background "
        "unchanged."
    )


def apply_design_transformation(
    base_image_uri: str,
    instruction: str,
    options: VisualizationOptions,
    provider: ImageEditCapableProvider,
    edit_depth: int,
) -> tuple[VisualizationImage | None, VisualizationProviderResult]:
    """Applies ONE transformation (the full target design, or a single
    isolated change) to an existing visual state. `edit_depth` is the
    depth of the image being edited; the returned image's own depth is
    `edit_depth + 1` -- callers should rebuild from Stage 1 rather than
    calling this again once `MAX_EDIT_DEPTH` is reached (section 14)."""
    store = get_visualization_asset_store()
    data = store.read(base_image_uri)
    reference = ReferenceImage(image_id="base", data=data, content_type=content_type_for(base_image_uri))

    result = provider.edit_image(reference, instruction)
    if not result.images:
        return None, result

    generated = result.images[0]
    asset_id = new_image_id()
    uri = store.save(asset_id, generated.data, generated.content_type)
    image = VisualizationImage(
        id=asset_id,
        uri=uri,
        view=options.view,
        presentation=options.presentation,
        stage=VisualizationStage.DESIGN_TRANSFORMATION,
        parent_asset_id=base_image_uri,
        edit_depth=edit_depth + 1,
    )
    return image, result
