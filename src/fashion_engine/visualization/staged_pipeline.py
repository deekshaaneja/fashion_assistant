"""run_staged_visualization: EXPERIMENTAL / FUTURE CAPABILITY -- NOT the
MVP default path. `src.fashion_engine.visualization.pipeline.visualize_design()`
is the canonical Phase 4 rendering path (fresh rebuild from the original
`FabricMaterialReference` + current `DesignProposal`, see
docs/visualization-engine.md). Nothing on the default path calls into this
module.

This module implements the alternative localized-edit-in-place pipeline
(section 2's diagram) --

    fabric photo(s) -> Stage 1 (material reference, deterministic)
    -> Stage 2 (base garment composition)
    -> Stage 3 (design transformation)
    -> VisualizationResult

The real Gemini acceptance experiment found that in-place editing of a
previously generated image does not reliably execute precise design-
geometry changes (see docs/visualization-engine.md's "Why rebuild instead
of edit"). This code is kept -- clean, tested, isolated -- for a future
provider/use case that specifically needs true in-place editing; it should
not be revived as the default without new evidence a specific provider can
do that reliably.

Each stage has a narrow responsibility (section 2); this module only
sequences them and builds the final result with full lineage (section 13,
48). It does not implement fashion logic (section 32) or fabric
reinterpretation (section 33) -- both remain Phase 1/2/3's job upstream.

Reuses the EXISTING Phase 4 abstractions where they remain useful (section
0): `reference_selector`, `spec_builder`, `asset_store`, `visual_validate`,
and the one-shot `VisualizationResult`/`VisualValidationResult` domain
models -- this is a new orchestration path, not a new set of result types.
"""
from __future__ import annotations

import time
import uuid

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric_vision import FabricImageAnalysisResult, ImageRole
from src.domain.models.visualization import (
    ProviderCapability,
    ValidationVerdict,
    VisualizationGenerationMetadata,
    VisualizationOptions,
    VisualizationResult,
    VisualValidationResult,
)
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store
from src.fashion_engine.visualization.base_composition import compose_base_garment
from src.fashion_engine.visualization.design_transformation import (
    apply_design_transformation,
    describe_full_design,
)
from src.fashion_engine.visualization.material_reference import prepare_fabric_reference
from src.fashion_engine.visualization.pipeline import uses_drape_reference
from src.fashion_engine.visualization.reference_selector import CandidateFabricImage, select_fabric_references
from src.fashion_engine.visualization.spec_builder import border_placements, build_visualization_specification
from src.fashion_engine.visualization.visual_validate import compare_observation_to_specification
from src.providers.settings import get_settings
from src.providers.visualization import (
    get_edit_capable_provider,
    get_generated_image_validator,
)
from src.providers.visualization import (
    provider_label as resolve_provider_label,
)

_DEFAULT_GARMENT_FAMILY = "simple long kurta"


def _build_candidates(image_analysis: FabricImageAnalysisResult, fabric_images: list[UploadedFabricImage]):
    role_by_id = {img.image_id: img.role for img in fabric_images}
    return [
        CandidateFabricImage(
            image_id=q.image_id,
            role=role_by_id.get(q.image_id) or ImageRole.UNKNOWN,
            usable=q.usable,
            duplicate_of=q.duplicate_of,
        )
        for q in image_analysis.image_quality
    ]


def _failure(design, spec, selection, timing_ms, total_start, error, error_code, fabric_name, provider_label):
    timing_ms["visualization.total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
    return VisualizationResult(
        id=uuid.uuid4().hex,
        design_id=design.id,
        fabric_name=fabric_name,
        images=[],
        specification=spec,
        fabric_references=selection,
        validation=VisualValidationResult(overall=ValidationVerdict.UNKNOWN, warnings=[error]),
        generation_metadata=VisualizationGenerationMetadata(
            provider=provider_label,
            strategy="staged",
            timing_ms=timing_ms,
            provider_error=error,
            provider_error_code=error_code,
        ),
    )


def run_staged_visualization(
    design: DesignProposal,
    image_analysis: FabricImageAnalysisResult,
    fabric_images: list[UploadedFabricImage],
    options: VisualizationOptions | None = None,
    garment_family: str = _DEFAULT_GARMENT_FAMILY,
) -> VisualizationResult:
    options = options or VisualizationOptions()
    settings = get_settings()
    timing_ms: dict[str, float] = {}
    total_start = time.monotonic()

    candidates = _build_candidates(image_analysis, fabric_images)
    uses_border = bool(border_placements(design))
    selection = select_fabric_references(
        candidates,
        max_references=settings.visualization_max_reference_images,
        uses_border=uses_border,
        flare_construction_uses_drape=uses_drape_reference(design),
    )
    spec = build_visualization_specification(design, image_analysis, selection, options)
    fabric_name = image_analysis.fabric_profile.fabric_name
    provider = get_edit_capable_provider()
    provider_label = resolve_provider_label(provider)

    if not selection.selected:
        return _failure(
            design, spec, selection, timing_ms, total_start,
            "no usable fabric reference images", "NO_USABLE_REFERENCES", fabric_name, provider_label,
        )

    # --- Stage 1: material reference (deterministic) ------------------
    t0 = time.monotonic()
    material_reference = prepare_fabric_reference(image_analysis, fabric_images, selection)
    timing_ms["visualization.stage1_material_reference_ms"] = round((time.monotonic() - t0) * 1000, 1)
    if not material_reference.references:
        return _failure(
            design, spec, selection, timing_ms, total_start,
            "no fabric image could be prepared as a material reference", "NO_USABLE_REFERENCES",
            fabric_name, provider_label,
        )

    # --- Stage 2: base garment composition -----------------------------
    t0 = time.monotonic()
    base_image, base_result = compose_base_garment(material_reference, garment_family, options, provider)
    timing_ms["visualization.stage2_base_garment_ms"] = round((time.monotonic() - t0) * 1000, 1)
    if base_image is None:
        return _failure(
            design, spec, selection, timing_ms, total_start,
            base_result.error or "base garment composition failed",
            base_result.error_code or "VISUALIZATION_PROVIDER_ERROR",
            fabric_name, provider_label,
        )

    # --- Stage 3: design transformation ---------------------------------
    t0 = time.monotonic()
    instruction = describe_full_design(design)
    final_image, design_result = apply_design_transformation(
        base_image.uri, instruction, options, provider, edit_depth=base_image.edit_depth
    )
    timing_ms["visualization.stage3_design_transformation_ms"] = round((time.monotonic() - t0) * 1000, 1)
    if final_image is None:
        return _failure(
            design, spec, selection, timing_ms, total_start,
            design_result.error or "design transformation failed",
            design_result.error_code or "VISUALIZATION_PROVIDER_ERROR",
            fabric_name, provider_label,
        )

    # --- Validation (reuses the existing Phase 4 comparison logic) -----
    t0 = time.monotonic()
    validator = get_generated_image_validator()
    final_bytes = get_visualization_asset_store().read(final_image.uri)
    validation_result = validator.analyze(final_bytes, "image/png")
    if validation_result.observation is None:
        warning = validation_result.error or "visual validation unavailable"
        validation = VisualValidationResult(overall=ValidationVerdict.UNKNOWN, warnings=[warning])
    else:
        overall, checks = compare_observation_to_specification(validation_result.observation, spec)
        validation = VisualValidationResult(
            overall=overall, checks=checks, observation=validation_result.observation
        )
    timing_ms["visualization.validation_ms"] = round((time.monotonic() - t0) * 1000, 1)
    timing_ms["visualization.total_ms"] = round((time.monotonic() - total_start) * 1000, 1)

    return VisualizationResult(
        id=uuid.uuid4().hex,
        design_id=design.id,
        fabric_name=fabric_name,
        images=[base_image, final_image],
        specification=spec,
        fabric_references=selection,
        validation=validation,
        source_fabric_reference_id=material_reference.id,
        generation_metadata=VisualizationGenerationMetadata(
            provider=provider_label,
            strategy="staged",
            reference_image_ids=[r.source_image_id for r in material_reference.references],
            timing_ms=timing_ms,
            capability_used=ProviderCapability.IMAGE_EDIT,
        ),
    )
