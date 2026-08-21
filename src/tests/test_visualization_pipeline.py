from __future__ import annotations

import pytest

from src.domain.models.visualization import ValidationVerdict, VisualizationOptions
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage, generate_design_directions_from_images
from src.fashion_engine.visualization import pipeline as pipeline_module
from src.providers.settings import get_settings
from src.providers.visualization import (
    DesignVisualizationProvider,
    GeneratedImage,
    GeneratedImageValidator,
    ValidationProviderResult,
    VisualizationProviderResult,
)
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch):
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _design_and_analysis():
    images = [UploadedFabricImage(image_id="img1", data=make_synthetic_fabric_image())]
    result = generate_design_directions_from_images(
        images, fabric_name_hint="organza", selected_garment_id="suit", selected_silhouette_id="anarkali", count=1
    )
    return result.design_directions.designs[0], result.image_analysis, images


class _CountingProvider(DesignVisualizationProvider):
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return VisualizationProviderResult(images=[GeneratedImage(data=b"fake-png")], attempts=1)


class _FixedObservationValidator(GeneratedImageValidator):
    def __init__(self, observations):
        self._observations = list(observations)
        self.calls = 0

    def analyze(self, image_bytes, content_type="image/png"):
        self.calls += 1
        obs = self._observations[min(self.calls - 1, len(self._observations) - 1)]
        return ValidationProviderResult(observation=obs, attempts=1)


class _FailingProvider(DesignVisualizationProvider):
    def generate(self, request):
        return VisualizationProviderResult(images=[], error="simulated failure", error_code="VISUALIZATION_PROVIDER_ERROR")


def test_end_to_end_with_mock_provider_produces_stored_image(tmp_path, monkeypatch):
    monkeypatch.setenv("VISUALIZATION_STORAGE_DIR", str(tmp_path))
    import src.fashion_engine.visualization.asset_store as asset_store_module

    asset_store_module._store = None
    design, image_analysis, images = _design_and_analysis()

    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    assert len(result.images) == 1
    assert (tmp_path / f"{result.images[0].id}.png").exists()
    assert result.design_id == design.id
    assert result.disclaimer  # section 13 -- always present


def test_no_usable_reference_images_fails_cleanly_without_calling_provider(monkeypatch):
    design, image_analysis, images = _design_and_analysis()
    corrupt_images = [UploadedFabricImage(image_id="img1", data=b"not an image")]
    # Rebuild image_analysis so its own image_quality reflects the corrupt upload.
    from src.fashion_engine.fabric.vision_pipeline import analyze_fabric_images

    corrupt_analysis = analyze_fabric_images(corrupt_images, fabric_name_hint="organza")

    provider = _CountingProvider()
    monkeypatch.setattr(pipeline_module, "get_design_visualization_provider", lambda: provider)

    result = pipeline_module.visualize_design(design, corrupt_analysis, corrupt_images, VisualizationOptions())
    assert result.images == []
    assert result.generation_metadata.provider_error_code == "NO_USABLE_REFERENCES"
    assert provider.calls == 0


def test_provider_failure_returns_structured_result_not_raise(monkeypatch):
    design, image_analysis, images = _design_and_analysis()
    monkeypatch.setattr(pipeline_module, "get_design_visualization_provider", lambda: _FailingProvider())

    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    assert result.images == []
    assert result.generation_metadata.provider_error_code == "VISUALIZATION_PROVIDER_ERROR"
    assert result.validation.overall == ValidationVerdict.UNKNOWN


def test_corrective_regeneration_is_bounded_to_exactly_one_attempt(monkeypatch):
    """Sections 17-18: FAIL triggers exactly one corrective regeneration,
    never an unbounded loop -- even if the corrective attempt ALSO fails."""
    design, image_analysis, images = _design_and_analysis()
    provider = _CountingProvider()
    monkeypatch.setattr(pipeline_module, "get_design_visualization_provider", lambda: provider)

    from src.domain.models.visualization import GeneratedImageObservation

    always_wrong = GeneratedImageObservation(
        garment_subject="a completely different garment entirely",
        neckline="v_neck",
        sleeve_length="sleeveless",
    )
    validator = _FixedObservationValidator([always_wrong, always_wrong])
    monkeypatch.setattr(pipeline_module, "get_generated_image_validator", lambda: validator)

    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    assert provider.calls == 2  # 1 initial + exactly 1 corrective, never more
    assert validator.calls == 2
    assert result.generation_metadata.corrective_regenerations == 1
    assert result.validation.corrective_regeneration_attempted is True


def test_no_corrective_regeneration_when_validation_passes(monkeypatch):
    design, image_analysis, images = _design_and_analysis()
    provider = _CountingProvider()
    monkeypatch.setattr(pipeline_module, "get_design_visualization_provider", lambda: provider)

    from src.domain.models.visualization import GeneratedImageObservation

    matching = GeneratedImageObservation(
        garment_subject=f"{design.garment.silhouette.name} suit",
        neckline=str(design.neckline.type),
        sleeve_length=str(design.sleeves.length),
        dupatta_present=bool(design.dupatta and design.dupatta.included),
    )
    validator = _FixedObservationValidator([matching])
    monkeypatch.setattr(pipeline_module, "get_generated_image_validator", lambda: validator)

    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    assert provider.calls == 1
    assert result.generation_metadata.corrective_regenerations == 0


def test_timing_stages_are_recorded():
    design, image_analysis, images = _design_and_analysis()
    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    timing = result.generation_metadata.timing_ms
    for stage in (
        "visualization.reference_selection_ms",
        "visualization.specification_build_ms",
        "visualization.provider_ms",
        "visualization.asset_storage_ms",
        "visualization.validation_ms",
        "visualization.total_ms",
    ):
        assert stage in timing


def test_traceability_fields_present():
    design, image_analysis, images = _design_and_analysis()
    result = pipeline_module.visualize_design(design, image_analysis, images, VisualizationOptions())
    assert result.design_id == design.id
    assert result.fabric_name == image_analysis.fabric_profile.fabric_name
    assert result.fabric_references.selected
    assert result.generation_metadata.reference_image_ids


def test_design_version_change_never_uses_prior_generated_image_as_reference(monkeypatch):
    """Phase 4 finalization, section 6: the canonical MVP path is
    FabricMaterialReference + current DesignProposal -> fresh render.
    Changing the DesignProposal from V1 to V2 must re-render from the
    ORIGINAL fabric photograph both times -- never from V1's own generated
    output, which would silently compound drift across versions."""
    design_v1, image_analysis, images = _design_and_analysis()
    design_v2 = design_v1.model_copy(
        update={
            "id": f"{design_v1.id}-v2",
            "neckline": design_v1.neckline.model_copy(update={"type": "square"}),
        }
    )

    class _RecordingProvider(DesignVisualizationProvider):
        def __init__(self):
            self.seen_reference_bytes: list[list[bytes]] = []
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            self.seen_reference_bytes.append([ref.data for ref in request.reference_images])
            # Each call's output is distinct and clearly NOT a valid input
            # image, so accidentally feeding it back in as a reference on
            # the next call would be obviously detectable.
            return VisualizationProviderResult(images=[GeneratedImage(data=f"generated-v{self.calls}".encode())])

    provider = _RecordingProvider()
    monkeypatch.setattr(pipeline_module, "get_design_visualization_provider", lambda: provider)

    result_v1 = pipeline_module.visualize_design(design_v1, image_analysis, images, VisualizationOptions())
    result_v2 = pipeline_module.visualize_design(design_v2, image_analysis, images, VisualizationOptions())

    assert provider.calls == 2
    assert result_v1.design_id == design_v1.id
    assert result_v2.design_id == design_v2.id
    original_bytes = images[0].data

    # Both calls were conditioned on the ORIGINAL fabric photo bytes.
    assert original_bytes in provider.seen_reference_bytes[0]
    assert original_bytes in provider.seen_reference_bytes[1]

    # Neither call's reference images are V1's (or V2's) own generated
    # output -- proving V2 did not chain from V1's rendered image.
    assert result_v1.images and result_v1.images[0].id
    for ref_bytes in provider.seen_reference_bytes[1]:
        assert ref_bytes != b"generated-v1"

    # The two calls are independent renders of the same source material,
    # not a chained edit -- confirmed by both receiving identical reference
    # bytes rather than call 2 receiving call 1's distinct output.
    assert provider.seen_reference_bytes[0] == provider.seen_reference_bytes[1]
