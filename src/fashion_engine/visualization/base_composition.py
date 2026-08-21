"""compose_base_garment: Phase 4.1, Stage 2 (sections 7-9). Puts the
prepared fabric onto a deliberately SIMPLE garment/mannequin representation
-- never the final design. This isolates "can the model apply THIS fabric
to clothing" from "can the model invent THIS complex fashion design"
(section 8): if Stage 2 cannot preserve the textile, Stage 3 will not fix
it, so Stage 2 must be judged on textile transfer alone, not aesthetics."""
from __future__ import annotations

from src.domain.models.visualization import (
    FabricMaterialReference,
    PresentationMode,
    ViewAngle,
    VisualizationImage,
    VisualizationOptions,
    VisualizationStage,
)
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store, new_image_id
from src.providers.visualization import ImageEditCapableProvider, ReferenceImage, VisualizationProviderResult

_CONTENT_TYPE_BY_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def content_type_for(uri: str) -> str:
    ext = uri.rsplit(".", 1)[-1].lower()
    return _CONTENT_TYPE_BY_EXT.get(ext, "image/jpeg")


def _hero_reference(material_reference: FabricMaterialReference):
    """Prefer FULL_VIEW for overall pattern/color (matches the reference
    selector's own priority, section 11) -- fall back to whatever is
    available rather than failing outright."""
    for ref in material_reference.references:
        if ref.role == "full_view":
            return ref
    return material_reference.references[0] if material_reference.references else None


def build_base_garment_prompt(garment_family: str, options: VisualizationOptions) -> str:
    presentation = "neutral mannequin" if options.presentation == PresentationMode.MANNEQUIN else str(
        options.presentation
    )
    view = "front" if options.view == ViewAngle.FRONT else str(options.view)
    return (
        f"Using this exact fabric, show it made into a simple {garment_family} on a {presentation}, "
        f"{view} view, plain studio background. Preserve the fabric's color, motif, embroidery/print, "
        "surface texture, and transparency exactly as shown -- do not invent a different fabric or "
        "additional embroidery/motifs not present in the reference."
    )


def compose_base_garment(
    material_reference: FabricMaterialReference,
    garment_family: str,
    options: VisualizationOptions,
    provider: ImageEditCapableProvider,
) -> tuple[VisualizationImage | None, VisualizationProviderResult]:
    """Returns `(image, provider_result)` -- `image` is None on failure,
    with the failure detail available on `provider_result`. Never raises."""
    hero = _hero_reference(material_reference)
    if hero is None:
        return None, VisualizationProviderResult(
            images=[], error="no fabric material reference available", error_code="NO_USABLE_REFERENCES"
        )

    store = get_visualization_asset_store()
    data = store.read(hero.asset_id)
    reference = ReferenceImage(
        image_id=hero.source_image_id, data=data, content_type=content_type_for(hero.asset_id)
    )

    prompt = build_base_garment_prompt(garment_family, options)
    result = provider.edit_image(reference, prompt)
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
        stage=VisualizationStage.BASE_GARMENT,
        parent_asset_id=hero.asset_id,
        edit_depth=0,
    )
    return image, result
