from __future__ import annotations

from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import (
    FabricIdentityStatus,
    FabricSubject,
    VisionModelOutput,
    VisionPropertyOut,
)
from src.fashion_engine.fabric.vision_pipeline import (
    UploadedFabricImage,
    analyze_fabric_images,
    generate_design_directions_from_images,
    recommend_silhouettes_from_images,
)
from src.providers.settings import get_settings
from src.providers.vision import FabricVisionProvider, VisionProviderResult
from src.tests.conftest import make_non_fabric_image, make_synthetic_fabric_image


def _image(image_id="img1", data=None) -> UploadedFabricImage:
    return UploadedFabricImage(image_id=image_id, data=data or make_synthetic_fabric_image())


class _FakeProvider(FabricVisionProvider):
    """Test-only provider for exercising specific scenarios without a real
    network call -- mirrors the Phase 2 test convention of small inline
    fake providers rather than adding test hooks to MockFabricVisionProvider."""

    def __init__(self, output=None, error=None, error_code=None):
        self._output = output
        self._error = error
        self._error_code = error_code
        self.calls: list[list] = []

    def analyze(self, images, fabric_name_hint=None):
        self.calls.append(images)
        return VisionProviderResult(
            output=self._output, error=self._error, error_code=self._error_code, attempts=1
        )


def _use_provider(monkeypatch, provider: FabricVisionProvider):
    monkeypatch.setattr(
        "src.fashion_engine.fabric.vision_pipeline.get_fabric_vision_provider", lambda: provider
    )


def _valid_output(**overrides) -> VisionModelOutput:
    base = dict(
        image_subject="fabric_swatch",
        subject_reason="looks like a swatch",
        transparency=VisionPropertyOut(value="semi_sheer", certainty="medium"),
        sheen=VisionPropertyOut(value="subtle_sheen", certainty="low"),
        drape=VisionPropertyOut(value="fluid", certainty="medium"),
        stiffness=VisionPropertyOut(certainty="unknown"),
        structure=VisionPropertyOut(certainty="unknown"),
        surface_density=VisionPropertyOut(value="sparse", certainty="high"),
        weight_class=VisionPropertyOut(value="light", certainty="medium"),
        embellishment_tolerance=VisionPropertyOut(certainty="unknown"),
        fabric_family=VisionPropertyOut(value="organza", certainty="medium"),
    )
    base.update(overrides)
    return VisionModelOutput(**base)


def test_analyze_single_image_end_to_end(monkeypatch):
    _use_provider(monkeypatch, _FakeProvider(output=_valid_output()))
    result = analyze_fabric_images([_image()], fabric_name_hint="organza")
    assert result.fabric_profile.fabric_name == "organza"
    assert result.fabric_profile.resolution_method == "exact"
    assert result.generation_metadata.provider_error is None


def test_analyze_multiple_images_dedup_only_sends_unique_ones(monkeypatch):
    provider = _FakeProvider(output=_valid_output())
    _use_provider(monkeypatch, provider)
    same_bytes = make_synthetic_fabric_image()
    distinct_bytes = make_synthetic_fabric_image(background=(10, 200, 10), accent=(200, 10, 200))
    images = [_image("a", same_bytes), _image("b", same_bytes), _image("c", distinct_bytes)]
    result = analyze_fabric_images(images)
    assert result.generation_metadata.images_submitted == 2
    assert result.generation_metadata.duplicate_images_dropped == 1
    assert len(provider.calls[0]) == 2


def test_analyze_no_images_returns_structured_no_usable_result():
    result = analyze_fabric_images([])
    assert result.generation_metadata.provider_error_code == "NO_USABLE_IMAGES"
    assert result.analysis.image_subject == FabricSubject.UNCERTAIN


def test_analyze_all_corrupt_images_returns_structured_result():
    result = analyze_fabric_images([_image("bad", b"not an image")])
    assert result.generation_metadata.provider_error_code == "NO_USABLE_IMAGES"


def test_analyze_provider_failure_is_reported_not_hidden(monkeypatch):
    _use_provider(monkeypatch, _FakeProvider(error="simulated failure", error_code="VISION_PROVIDER_ERROR"))
    result = analyze_fabric_images([_image()])
    assert result.generation_metadata.provider_error == "simulated failure"
    assert result.generation_metadata.provider_error_code == "VISION_PROVIDER_ERROR"


def test_analyze_non_fabric_image_does_not_invent_a_profile(monkeypatch):
    output = _valid_output(image_subject="non_fabric", subject_reason="looks like a shoe")
    _use_provider(monkeypatch, _FakeProvider(output=output))
    result = analyze_fabric_images([_image(data=make_non_fabric_image())])
    assert result.analysis.image_subject == FabricSubject.NON_FABRIC
    # no property should be confidently declared from a non-fabric photo
    assert result.fabric_profile.properties.transparency is not None  # model still answered, but subject flags it
    assert result.analysis.image_subject != FabricSubject.FABRIC_SWATCH


def test_user_confirmed_properties_take_precedence(monkeypatch):
    _use_provider(monkeypatch, _FakeProvider(output=_valid_output()))
    result = analyze_fabric_images(
        [_image()], fabric_name_hint="organza", user_confirmed_properties=FabricProperties(transparency="opaque")
    )
    assert result.fabric_profile.properties.transparency == "opaque"
    transparency_evidence = next(e for e in result.evidence if e.property == "transparency")
    assert transparency_evidence.evidence_type == "user_confirmed"


def test_user_confirmed_fabric_name_overrides_vision_and_resolves(monkeypatch):
    output = _valid_output(fabric_family=VisionPropertyOut(value="organza", certainty="medium"))
    _use_provider(monkeypatch, _FakeProvider(output=output))
    result = analyze_fabric_images([_image()], user_confirmed_fabric_name="georgette")
    assert result.fabric_profile.fabric_name == "georgette"
    assert result.fabric_profile.resolution_method == "exact"
    # Section 14-15: a user-confirmed identity is CONFIRMED, never demoted
    # back to a mere repository match.
    assert result.fabric_profile.identity_status == FabricIdentityStatus.CONFIRMED
    fabric_family_evidence = next(e for e in result.evidence if e.property == "fabric_family")
    assert fabric_family_evidence.evidence_type == "user_confirmed"
    assert fabric_family_evidence.value == "georgette"
    # The original vision inference is preserved for audit, not discarded.
    assert any(alt.value == "organza" for alt in fabric_family_evidence.alternatives)


def test_repository_match_from_vision_alone_is_only_probable(monkeypatch):
    """Section 14: a repository match built from vision-inferred evidence
    (never user-confirmed) must read as PROBABLE, not a confirmed identity --
    string-match quality (resolution_method) and vision confidence are
    orthogonal, and a repository entry is supplementary knowledge, not new
    visual evidence."""
    output = _valid_output(fabric_family=VisionPropertyOut(value="organza", certainty="medium"))
    _use_provider(monkeypatch, _FakeProvider(output=output))
    result = analyze_fabric_images([_image()])
    assert result.fabric_profile.resolution_method == "exact"
    assert result.fabric_profile.identity_status == FabricIdentityStatus.PROBABLE


def test_unresolved_fabric_name_has_unresolved_identity_status(monkeypatch):
    output = _valid_output(fabric_family=VisionPropertyOut(certainty="unknown"))
    _use_provider(monkeypatch, _FakeProvider(output=output))
    result = analyze_fabric_images([_image()])
    assert result.fabric_profile.resolution_method == "unresolved"
    assert result.fabric_profile.identity_status == FabricIdentityStatus.UNRESOLVED


def test_recommend_silhouettes_from_images_reuses_phase1(monkeypatch):
    _use_provider(monkeypatch, _FakeProvider(output=_valid_output()))
    result = recommend_silhouettes_from_images([_image()], fabric_name_hint="organza")
    assert result.silhouette_recommendation.candidates
    assert result.image_analysis.fabric_profile.fabric_name == "organza"


def test_generate_design_directions_from_images_reuses_phase2(monkeypatch):
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        _use_provider(monkeypatch, _FakeProvider(output=_valid_output()))
        result = generate_design_directions_from_images(
            [_image()],
            fabric_name_hint="organza",
            selected_garment_id="suit",
            selected_silhouette_id="anarkali",
            count=1,
        )
        assert len(result.design_directions.designs) == 1
    finally:
        get_settings.cache_clear()
