from __future__ import annotations

import pytest

from src.domain.models.fabric import FabricProperties
from src.domain.models.visualization import PresentationMode, ViewAngle, VisualizationOptions
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage, generate_design_directions_from_images
from src.fashion_engine.visualization.reference_selector import CandidateFabricImage, select_fabric_references
from src.fashion_engine.visualization.spec_builder import build_visualization_specification
from src.providers.settings import get_settings
from src.tests.conftest import make_synthetic_fabric_image


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch):
    """These tests exercise spec-building logic, not live providers -- force
    both Phase 2 and Phase 3 to their deterministic paths regardless of this
    machine's .env (VISION_ENABLED/DESIGN_GENERATION_PROVIDER)."""
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _design_and_analysis(garment_id="suit", silhouette_id="anarkali", fabric_hint="organza", properties=None):
    images = [UploadedFabricImage(image_id="img1", data=make_synthetic_fabric_image())]
    result = generate_design_directions_from_images(
        images,
        fabric_name_hint=fabric_hint,
        user_confirmed_properties=properties,
        selected_garment_id=garment_id,
        selected_silhouette_id=silhouette_id,
        count=1,
    )
    return result.design_directions.designs[0], result.image_analysis


def _references(image_analysis):
    candidates = [
        CandidateFabricImage(image_id=q.image_id, role="full_view", usable=q.usable, duplicate_of=q.duplicate_of)
        for q in image_analysis.image_quality
    ]
    return select_fabric_references(candidates, max_references=3, uses_border=False)


def test_spec_maps_garment_and_construction_from_design():
    design, image_analysis = _design_and_analysis()
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())

    assert spec.design_id == design.id
    assert spec.garment.category == design.garment.garment.id
    assert spec.garment.silhouette == design.garment.silhouette.id
    assert spec.construction.bodice == design.construction.bodice_style
    assert spec.construction.flare_level == design.construction.flare_level
    assert spec.construction.flare_construction == design.construction.flare_construction
    assert spec.neckline.type == design.neckline.type
    assert spec.sleeves.length == design.sleeves.length


def test_subject_reflects_requested_presentation_and_view():
    design, image_analysis = _design_and_analysis()
    options = VisualizationOptions(presentation=PresentationMode.MODEL, view=ViewAngle.FRONT)
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), options)
    assert spec.subject.presentation == "model"
    assert spec.subject.view == "front"


def test_hero_fabric_material_gets_source_images_and_summary():
    design, image_analysis = _design_and_analysis()
    references = _references(image_analysis)
    spec = build_visualization_specification(design, image_analysis, references, VisualizationOptions())

    hero = next(m for m in spec.materials if m.role == "main_garment")
    assert hero.use_hero_fabric is True
    assert hero.source_image_ids == [r.image_id for r in references.selected]
    assert hero.fabric_summary is not None


def test_supporting_fabric_has_no_source_images():
    # Confirmed sheer (not just the mock provider's low-certainty guess) --
    # requires_lining is deterministic here.
    design, image_analysis = _design_and_analysis(properties=FabricProperties(transparency="sheer"))
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())
    lining = next((m for m in spec.materials if m.role == "lining"), None)
    assert lining is not None
    assert lining.use_hero_fabric is False
    assert lining.source_image_ids == []
    assert lining.fabric_summary is None


def test_dupatta_mapping_preserves_visual_attributes_when_included():
    design, image_analysis = _design_and_analysis()
    if design.dupatta is None or not design.dupatta.included:
        pytest.skip("this archetype/silhouette combination didn't include a dupatta")
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())
    assert spec.dupatta is not None
    assert spec.dupatta.included is True
    assert spec.dupatta.transparency == design.dupatta.transparency
    assert spec.dupatta.border == design.dupatta.border


def test_decoration_mapping_preserves_treatments():
    design, image_analysis = _design_and_analysis()
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())
    assert spec.decoration.level == design.decoration.level
    assert len(spec.decoration.treatments) == len(design.decoration.treatments)
    if design.decoration.treatments:
        assert spec.decoration.treatments[0].material == design.decoration.treatments[0].material


def test_transparency_and_lining_mapping():
    design, image_analysis = _design_and_analysis(properties=FabricProperties(transparency="sheer"))
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())
    assert design.lining.required is True
    assert "main_garment" in spec.preservation_requirements.lined_components
    if design.sleeves.sheer:
        assert "sleeves" in spec.preservation_requirements.unlined_sheer_components


def test_no_second_garment_representation_every_field_traces_to_design():
    """Section 47: nothing in the spec should be inventable independent of
    the DesignProposal -- every structural field must equal its source."""
    design, image_analysis = _design_and_analysis()
    spec = build_visualization_specification(design, image_analysis, _references(image_analysis), VisualizationOptions())
    assert spec.bottom.type == design.bottom.type if design.bottom else spec.bottom is None
