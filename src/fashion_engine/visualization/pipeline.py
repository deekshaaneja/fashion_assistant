"""visualize_design: Phase 4's top-level orchestrator, and the CANONICAL MVP
rendering path --

    original FabricMaterialReference + current DesignProposal
    -> fabric reference selection -> VisualizationSpecification
    -> DesignVisualizationProvider (exactly ONE generation call)
    -> asset storage -> visual validation -> VisualizationResult

Every call is an independent fresh render from the ORIGINAL fabric photos
-- never from a previously generated image (see the real-image acceptance
experiment in docs/visualization-engine.md: iterative in-place editing
failed on precise design-geometry edits; rebuild-per-DesignProposal-version
did not). A generated image is disposable rendered output, never canonical
design state -- `DesignProposal` is never inferred or updated from one.

Corrective regeneration (generate -> validate -> FAIL -> regenerate once)
is OFF by default (`VISUALIZATION_AUTO_CORRECT=false`, Phase 4
finalization section 2) -- a probabilistic validator must never
automatically trigger another paid generation without explicit opt-in.
When enabled, at most one corrective attempt is ever made.

The structured system stays authoritative throughout (section 2): nothing
here ever writes back into `DesignProposal`, and provider failures always
degrade to a structured result, never a hang or an exception."""
from __future__ import annotations

import time

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.domain.models.visualization import (
    ValidationVerdict,
    VisualizationGenerationMetadata,
    VisualizationImage,
    VisualizationOptions,
    VisualizationResult,
    VisualizationSpecification,
    VisualValidationResult,
)
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store, new_image_id
from src.fashion_engine.visualization.reference_selector import CandidateFabricImage, select_fabric_references
from src.fashion_engine.visualization.spec_builder import (
    border_placements,
    build_visualization_specification,
    fabric_preservation_instruction,
)
from src.fashion_engine.visualization.visual_validate import compare_observation_to_specification
from src.providers.settings import get_settings
from src.providers.visualization import (
    ReferenceImage,
    VisualizationProviderRequest,
    estimated_cost_per_image_usd,
    get_design_visualization_provider,
    get_generated_image_validator,
    provider_label,
)


def uses_drape_reference(design: DesignProposal) -> bool:
    return design.construction.flare_construction != "controlled" or design.construction.flare_level in (
        "high",
        "dramatic",
    )


def _model_for(label: str) -> str | None:
    settings = get_settings()
    if label == "gemini":
        return settings.gemini_image_model
    if label == "fal":
        return settings.fal_edit_model
    if label == "openai_compatible":
        return settings.visualization_model
    return None


def _estimate_total_cost(label: str, image_count: int) -> float | None:
    per_image = estimated_cost_per_image_usd(label)
    if per_image is None or image_count <= 0:
        return None
    return round(per_image * image_count, 4)


def _build_candidates(
    image_analysis: FabricImageAnalysisResult, fabric_images: list[UploadedFabricImage]
) -> list[CandidateFabricImage]:
    role_by_id = {img.image_id: img.role for img in fabric_images}
    from src.domain.models.fabric_vision import ImageRole

    return [
        CandidateFabricImage(
            image_id=q.image_id,
            role=role_by_id.get(q.image_id) or ImageRole.UNKNOWN,
            usable=q.usable,
            duplicate_of=q.duplicate_of,
        )
        for q in image_analysis.image_quality
    ]


def _build_prompt(spec: VisualizationSpecification, has_references: bool) -> str:
    """The rendering instruction handed to the provider -- English
    description of the specification, never provider-specific request
    shape (section 3). Explicitly asks the model to use the reference
    photograph(s) as the actual fabric rather than inventing one from a
    text description alone (section 10)."""
    lines = [
        f"Render a {spec.subject.presentation} product photograph, {spec.subject.view} view, "
        f"{spec.subject.pose}, clean neutral studio background.",
        f"Garment: {spec.garment.category_name} in a {spec.garment.silhouette_name} silhouette.",
        f"Construction: {spec.construction.bodice} bodice, {spec.construction.waist} waist, "
        f"{spec.construction.flare_level} flare built via {spec.construction.flare_construction} construction, "
        f"{spec.construction.length} length.",
    ]
    if spec.construction.panelling:
        lines.append(f"Panelling: {spec.construction.panelling}.")
    if spec.construction.hem:
        lines.append(f"Hem: {spec.construction.hem}.")
    lines.append(f"Neckline: {spec.neckline.type}{f', {spec.neckline.depth}' if spec.neckline.depth else ''}.")
    lines.append(
        f"Sleeves: {spec.sleeves.length}, {spec.sleeves.style} style"
        f"{', sheer' if spec.sleeves.sheer else ''}"
        f"{f', {spec.sleeves.cuff_treatment} cuff' if spec.sleeves.cuff_treatment else ''}."
    )
    if spec.bottom:
        lines.append(f"Bottom: {spec.bottom.type}.")
    if spec.dupatta and spec.dupatta.included:
        dupatta_bits = [f"{spec.dupatta.color_strategy} color story" if spec.dupatta.color_strategy else None]
        if spec.dupatta.border:
            dupatta_bits.append(f"border: {spec.dupatta.border}")
        if spec.dupatta.embellishment:
            dupatta_bits.append(f"embellishment: {spec.dupatta.embellishment}")
        if spec.dupatta.ombre_direction:
            dupatta_bits.append(f"ombre: {spec.dupatta.ombre_direction}")
        lines.append("Dupatta included -- " + ", ".join(b for b in dupatta_bits if b) + ".")
    elif spec.dupatta is not None:
        lines.append("No dupatta -- this design intentionally omits one.")

    if spec.decoration.treatments:
        for t in spec.decoration.treatments:
            lines.append(f"Decoration ({t.intensity}): {t.material} at {', '.join(t.placement) or 'as shown'}.")
    else:
        lines.append(f"Decoration level: {spec.decoration.level} -- no explicit additional treatment.")

    lines.extend(fabric_preservation_instruction(spec, has_references))
    pr = spec.preservation_requirements
    if pr.lined_components:
        lines.append(f"Lined (opaque): {', '.join(pr.lined_components)}.")
    if pr.unlined_sheer_components:
        lines.append(f"Left unlined and sheer: {', '.join(pr.unlined_sheer_components)}.")

    lines.append(
        "This is a design CONCEPT visualization, not a manufacturing simulation -- exact pixel-level "
        "fabric reproduction is not required, but the color/motif/surface identity must be recognizable."
    )
    return "\n".join(lines)


def _corrective_prompt(base_prompt: str, checks) -> str:
    failed = [c for c in checks if c.verdict == ValidationVerdict.FAIL]
    lines = [
        "The previous image did not match the specification. Preserve the same composition, fabric, and "
        "everything else, but correct ONLY the following:",
    ]
    lines += [f"- {c.name}: {c.detail}" for c in failed]
    return base_prompt + "\n\n" + "\n".join(lines)


def visualize_design(
    design: DesignProposal,
    image_analysis: FabricImageAnalysisResult,
    fabric_images: list[UploadedFabricImage],
    options: VisualizationOptions | None = None,
) -> VisualizationResult:
    options = options or VisualizationOptions()
    settings = get_settings()
    timing_ms: dict[str, float] = {}
    total_start = time.monotonic()

    t0 = time.monotonic()
    candidates = _build_candidates(image_analysis, fabric_images)
    selection = select_fabric_references(
        candidates,
        max_references=settings.visualization_max_reference_images,
        uses_border=bool(border_placements(design)),
        flare_construction_uses_drape=uses_drape_reference(design),
    )
    timing_ms["visualization.reference_selection_ms"] = round((time.monotonic() - t0) * 1000, 1)

    t0 = time.monotonic()
    spec = build_visualization_specification(design, image_analysis, selection, options)
    timing_ms["visualization.specification_build_ms"] = round((time.monotonic() - t0) * 1000, 1)

    fabric_family_evidence = next(
        (e for e in image_analysis.fabric_profile.evidence if e.property == "fabric_family"), None
    )

    fabric_name = image_analysis.fabric_profile.fabric_name

    if not selection.selected:
        return _failure_result(
            design,
            spec,
            selection,
            timing_ms,
            total_start,
            "no usable fabric reference images",
            "NO_USABLE_REFERENCES",
            fabric_name=fabric_name,
        )

    bytes_by_id = {img.image_id: img for img in fabric_images}
    reference_images = [
        ReferenceImage(
            image_id=s.image_id,
            data=bytes_by_id[s.image_id].data,
            content_type=bytes_by_id[s.image_id].content_type,
        )
        for s in selection.selected
        if s.image_id in bytes_by_id
    ]

    provider = get_design_visualization_provider()
    label = provider_label(provider)
    prompt = _build_prompt(spec, has_references=bool(reference_images))

    t0 = time.monotonic()
    provider_result = provider.generate(
        VisualizationProviderRequest(
            specification=spec, reference_images=reference_images, prompt=prompt, count=options.count
        )
    )
    timing_ms["visualization.provider_ms"] = round((time.monotonic() - t0) * 1000, 1)

    if not provider_result.images:
        return _failure_result(
            design,
            spec,
            selection,
            timing_ms,
            total_start,
            provider_result.error or "provider returned no image",
            provider_result.error_code or "VISUALIZATION_PROVIDER_ERROR",
            fabric_name=fabric_name,
            provider=label,
            attempts=provider_result.attempts,
        )

    t0 = time.monotonic()
    store = get_visualization_asset_store()
    images = []
    for img in provider_result.images[: options.count]:
        image_id = new_image_id()
        uri = store.save(image_id, img.data, img.content_type)
        images.append(
            VisualizationImage(id=image_id, uri=uri, view=options.view, presentation=options.presentation)
        )
    timing_ms["visualization.asset_storage_ms"] = round((time.monotonic() - t0) * 1000, 1)

    t0 = time.monotonic()
    validator = get_generated_image_validator()
    validation_result = validator.analyze(provider_result.images[0].data, provider_result.images[0].content_type)
    corrective_attempts = 0

    if validation_result.observation is None:
        validation = VisualValidationResult(
            overall=ValidationVerdict.UNKNOWN,
            warnings=[validation_result.error or "visual validation unavailable"],
        )
    else:
        overall, checks = compare_observation_to_specification(validation_result.observation, spec)
        # Phase 4 finalization, section 2-3: OFF by default -- a
        # probabilistic validator must never automatically trigger another
        # PAID generation without explicit opt-in. When enabled, at most
        # ONE corrective regeneration is made, only on a hard FAIL.
        if settings.visualization_auto_correct and overall == ValidationVerdict.FAIL:
            corrective_attempts = 1
            corrective = provider.generate(
                VisualizationProviderRequest(
                    specification=spec,
                    reference_images=reference_images,
                    prompt=_corrective_prompt(prompt, checks),
                    count=1,
                )
            )
            if corrective.images:
                image_id = new_image_id()
                uri = store.save(image_id, corrective.images[0].data, corrective.images[0].content_type)
                images = [
                    VisualizationImage(id=image_id, uri=uri, view=options.view, presentation=options.presentation)
                ]
                retry_validation = validator.analyze(corrective.images[0].data, corrective.images[0].content_type)
                if retry_validation.observation is not None:
                    overall, checks = compare_observation_to_specification(retry_validation.observation, spec)
                    validation_result = retry_validation

        validation = VisualValidationResult(
            overall=overall,
            checks=checks,
            observation=validation_result.observation,
            corrective_regeneration_attempted=corrective_attempts > 0,
        )
    timing_ms["visualization.validation_ms"] = round((time.monotonic() - t0) * 1000, 1)
    timing_ms["visualization.total_ms"] = round((time.monotonic() - total_start) * 1000, 1)

    return VisualizationResult(
        id=new_image_id(),
        design_id=design.id,
        fabric_name=image_analysis.fabric_profile.fabric_name,
        fabric_identity_evidence_type=fabric_family_evidence.evidence_type if fabric_family_evidence else None,
        images=images,
        specification=spec,
        fabric_references=selection,
        validation=validation,
        generation_metadata=VisualizationGenerationMetadata(
            provider=label,
            model=_model_for(label),
            strategy="reference_conditioned" if reference_images else "text_only",
            attempts=provider_result.attempts,
            corrective_regenerations=corrective_attempts,
            reference_image_ids=[r.image_id for r in reference_images],
            timing_ms=timing_ms,
            quality=options.quality,
            estimated_cost_usd=_estimate_total_cost(label, len(images) + corrective_attempts),
        ),
    )


def _failure_result(
    design: DesignProposal,
    spec: VisualizationSpecification,
    selection,
    timing_ms: dict[str, float],
    total_start: float,
    error: str,
    error_code: str,
    fabric_name: str = "unknown fabric",
    provider: str = "none",
    attempts: int = 0,
) -> VisualizationResult:
    timing_ms["visualization.total_ms"] = round((time.monotonic() - total_start) * 1000, 1)
    return VisualizationResult(
        id=new_image_id(),
        design_id=design.id,
        fabric_name=fabric_name,
        images=[],
        specification=spec,
        fabric_references=selection,
        validation=VisualValidationResult(overall=ValidationVerdict.UNKNOWN, warnings=[error]),
        generation_metadata=VisualizationGenerationMetadata(
            provider=provider,
            strategy="none",
            attempts=attempts,
            timing_ms=timing_ms,
            provider_error=error,
            provider_error_code=error_code,
        ),
    )
