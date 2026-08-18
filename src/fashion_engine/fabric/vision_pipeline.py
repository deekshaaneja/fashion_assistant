"""analyze_fabric_images: Phase 3's top-level orchestrator (the pipeline
diagram in the brief) --

    photo(s) -> preprocess/dedup -> vision provider -> normalize/evidence
    -> user overrides -> canonical FabricProperties (declared-only, ready
    to hand to Phase 1/2 exactly like a text-declared `FabricObservation`)

This module NEVER duplicates Phase 1/2 logic -- `recommend_silhouettes_from_images`
composes the EXISTING `src.tools.recommend_silhouettes`/`generate_design_directions`
tool functions with whatever `(fabric_name, declared_properties)` this
pipeline produces, the same shape a text-declared `FabricObservation`
already produces (section 30-31)."""
from __future__ import annotations

import time
from dataclasses import dataclass

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import DesignDirectionsResult
from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import (
    Evidence,
    EvidenceType,
    FabricIdentityStatus,
    FabricImageAnalysisResult,
    FabricProfileWithProvenance,
    FabricSubject,
    FabricVisionObservation,
    ImageQualityAssessment,
    ImageRole,
    VisionGenerationMetadata,
)
from src.domain.models.recommendation import SilhouetteRecommendationResult
from src.fashion_engine.fabric.vision_evidence import (
    apply_user_confirmed_fabric_name,
    apply_user_overrides,
    build_fabric_properties,
    normalize_observation,
)
from src.fashion_engine.fabric.vision_preprocess import (
    assess_quality,
    average_hash,
    decode_image,
    detect_duplicates,
)
from src.providers.vision import MockFabricVisionProvider, ProviderImage, get_fabric_vision_provider
from src.rules.repository import get_fabric_repository


@dataclass
class UploadedFabricImage:
    """Raw upload at the pipeline boundary -- bytes never enter a domain
    model (section 32)."""

    image_id: str
    data: bytes
    content_type: str = "image/jpeg"
    role: ImageRole | None = None


_ALWAYS_UNKNOWN_EVIDENCE = ("gsm", "width_cm", "stretch")


def _no_usable_images_result(
    image_quality: list[ImageQualityAssessment], reason: str
) -> FabricImageAnalysisResult:
    evidence = [
        Evidence(property=name, value=None, evidence_type=EvidenceType.UNKNOWN, confidence=0.0, reason=reason)
        for name in _ALWAYS_UNKNOWN_EVIDENCE
    ]
    observation = FabricVisionObservation(
        image_subject=FabricSubject.UNCERTAIN,
        subject_confidence=0.0,
        wear_potential=None,
        evidence=evidence,
        warnings=[reason],
    )
    return FabricImageAnalysisResult(
        image_quality=image_quality,
        analysis=observation,
        fabric_profile=FabricProfileWithProvenance(
            fabric_name="unknown fabric",
            resolved_fabric_id=None,
            resolution_method="unresolved",
            properties=FabricProperties(),
            evidence=evidence,
        ),
        evidence=evidence,
        warnings=[reason],
        generation_metadata=VisionGenerationMetadata(
            provider="none", provider_error=reason, provider_error_code="NO_USABLE_IMAGES"
        ),
    )


def analyze_fabric_images(
    images: list[UploadedFabricImage],
    fabric_name_hint: str | None = None,
    user_confirmed_properties: FabricProperties | None = None,
    user_confirmed_fabric_name: str | None = None,
) -> FabricImageAnalysisResult:
    timing_ms: dict[str, float] = {}
    total_start = time.monotonic()

    t0 = time.monotonic()
    quality_by_id = {img.image_id: assess_quality(img.image_id, img.data) for img in images}
    timing_ms["vision.preprocess_ms"] = round((time.monotonic() - t0) * 1000, 1)

    t0 = time.monotonic()
    decodable = {img.image_id: img for img in images if quality_by_id[img.image_id].usable}
    hashes = {
        image_id: average_hash(decode_image(img.data))
        for image_id, img in decodable.items()
        if decode_image(img.data) is not None
    }
    duplicate_map = detect_duplicates(hashes)
    quality_list = [
        quality_by_id[img.image_id].model_copy(update={"duplicate_of": duplicate_map.get(img.image_id)})
        for img in images
    ]
    timing_ms["vision.dedup_ms"] = round((time.monotonic() - t0) * 1000, 1)

    usable_images = [
        img for img in images if quality_by_id[img.image_id].usable and duplicate_map.get(img.image_id) is None
    ]
    duplicates_dropped = sum(1 for v in duplicate_map.values() if v is not None)

    if not usable_images:
        reason = (
            "No usable images were submitted -- all were unreadable, too small, blank, or duplicates."
            if images
            else "No images were submitted."
        )
        result = _no_usable_images_result(quality_list, reason)
        result.generation_metadata.timing_ms = timing_ms
        return result

    provider_images = [
        ProviderImage(
            image_id=img.image_id, data=img.data, content_type=img.content_type, role=img.role or ImageRole.UNKNOWN
        )
        for img in usable_images
    ]

    provider = get_fabric_vision_provider()
    t0 = time.monotonic()
    provider_result = provider.analyze(provider_images, fabric_name_hint)
    timing_ms["vision.provider_ms"] = round((time.monotonic() - t0) * 1000, 1)

    provider_label = "mock" if isinstance(provider, MockFabricVisionProvider) else "openai_compatible"

    if provider_result.output is None:
        warnings = [provider_result.error or "Vision provider returned no usable analysis."]
        result = _no_usable_images_result(quality_list, warnings[0])
        result.generation_metadata = VisionGenerationMetadata(
            provider=provider_label,
            model=None,
            attempts=provider_result.attempts,
            images_submitted=len(provider_images),
            duplicate_images_dropped=duplicates_dropped,
            provider_error=provider_result.error,
            provider_error_code=provider_result.error_code,
            timing_ms=timing_ms,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
        )
        return result

    t0 = time.monotonic()
    observation = normalize_observation(
        provider_result.output, [img.image_id for img in usable_images], warnings=list(provider_result.warnings)
    )
    evidence = apply_user_overrides(observation.evidence, user_confirmed_properties)
    evidence = apply_user_confirmed_fabric_name(evidence, user_confirmed_fabric_name)
    observation = observation.model_copy(update={"evidence": evidence})
    timing_ms["vision.evidence_ms"] = round((time.monotonic() - t0) * 1000, 1)

    fabric_family_evidence = next((e for e in evidence if e.property == "fabric_family"), None)
    final_fabric_name = (
        user_confirmed_fabric_name
        or (fabric_family_evidence.value if fabric_family_evidence and fabric_family_evidence.value else None)
        or fabric_name_hint
        or "unknown fabric"
    )

    declared_properties = build_fabric_properties(evidence)
    resolution = get_fabric_repository().resolve(final_fabric_name)

    if user_confirmed_fabric_name:
        identity_status = FabricIdentityStatus.CONFIRMED
    elif resolution.method != "unresolved":
        identity_status = FabricIdentityStatus.PROBABLE
    else:
        identity_status = FabricIdentityStatus.UNRESOLVED

    fabric_profile = FabricProfileWithProvenance(
        fabric_name=final_fabric_name,
        resolved_fabric_id=resolution.profile.id if resolution.method != "unresolved" else None,
        resolution_method=resolution.method,
        identity_status=identity_status,
        properties=declared_properties,
        evidence=evidence,
    )

    timing_ms["vision.total_ms"] = round((time.monotonic() - total_start) * 1000, 1)

    return FabricImageAnalysisResult(
        image_quality=quality_list,
        analysis=observation,
        fabric_profile=fabric_profile,
        evidence=evidence,
        warnings=observation.warnings,
        generation_metadata=VisionGenerationMetadata(
            provider=provider_label,
            model=None,
            attempts=provider_result.attempts,
            images_submitted=len(provider_images),
            duplicate_images_dropped=duplicates_dropped,
            timing_ms=timing_ms,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
        ),
    )


@dataclass
class FabricImageRecommendationResult:
    image_analysis: FabricImageAnalysisResult
    silhouette_recommendation: SilhouetteRecommendationResult


def recommend_silhouettes_from_images(
    images: list[UploadedFabricImage],
    fabric_name_hint: str | None = None,
    user_confirmed_properties: FabricProperties | None = None,
    user_confirmed_fabric_name: str | None = None,
    context: RecommendationContext | None = None,
) -> FabricImageRecommendationResult:
    """Section 30: image -> FabricProfile -> `recommend_silhouettes()`,
    composing the existing Phase 1 tool rather than duplicating it."""
    from src.tools.recommend_silhouettes import recommend_silhouettes

    image_analysis = analyze_fabric_images(
        images, fabric_name_hint, user_confirmed_properties, user_confirmed_fabric_name
    )
    result = recommend_silhouettes(
        image_analysis.fabric_profile.fabric_name, image_analysis.fabric_profile.properties, context
    )
    return FabricImageRecommendationResult(image_analysis=image_analysis, silhouette_recommendation=result)


@dataclass
class FabricImageDesignResult:
    image_analysis: FabricImageAnalysisResult
    design_directions: DesignDirectionsResult


def generate_design_directions_from_images(
    images: list[UploadedFabricImage],
    fabric_name_hint: str | None = None,
    user_confirmed_properties: FabricProperties | None = None,
    user_confirmed_fabric_name: str | None = None,
    fashion_context: RecommendationContext | None = None,
    client_brief: ClientBrief | None = None,
    selected_garment_id: str | None = None,
    selected_silhouette_id: str | None = None,
    count: int = 3,
) -> FabricImageDesignResult:
    """Section 31: image -> FabricProfile -> Phase 1 -> Phase 2, composing
    the existing `generate_design_directions` tool rather than duplicating
    it. Proves the full photo-to-design-proposal handoff programmatically."""
    from src.tools.generate_design_directions import generate_design_directions

    image_analysis = analyze_fabric_images(
        images, fabric_name_hint, user_confirmed_properties, user_confirmed_fabric_name
    )
    result = generate_design_directions(
        image_analysis.fabric_profile.fabric_name,
        image_analysis.fabric_profile.properties,
        fashion_context,
        client_brief,
        selected_garment_id=selected_garment_id,
        selected_silhouette_id=selected_silhouette_id,
        count=count,
    )
    return FabricImageDesignResult(image_analysis=image_analysis, design_directions=result)
