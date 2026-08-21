from __future__ import annotations

from src.domain.models.visualization import (
    ConstructionVisualSpec,
    DecorationVisualSpec,
    DupattaVisualSpec,
    GarmentSpec,
    GeneratedImageObservation,
    MaterialFabricSummary,
    MaterialReference,
    NecklineVisualSpec,
    PresentationMode,
    PreservationRequirements,
    SleevesVisualSpec,
    SubjectSpec,
    ValidationVerdict,
    ViewAngle,
    VisualizationSpecification,
)
from src.fashion_engine.visualization.visual_validate import compare_observation_to_specification


def _spec(**overrides) -> VisualizationSpecification:
    defaults = dict(
        design_id="d1",
        subject=SubjectSpec(presentation=PresentationMode.MANNEQUIN, view=ViewAngle.FRONT),
        garment=GarmentSpec(category="suit", category_name="Suit", silhouette="anarkali", silhouette_name="Anarkali"),
        construction=ConstructionVisualSpec(
            bodice="fitted", waist="natural", flare_level="high", flare_construction="gathered", length="floor_length"
        ),
        neckline=NecklineVisualSpec(type="round"),
        sleeves=SleevesVisualSpec(length="three_quarter", style="straight"),
        decoration=DecorationVisualSpec(level="MINIMAL"),
        materials=[
            MaterialReference(
                role="main_garment",
                use_hero_fabric=True,
                source_image_ids=["img1"],
                fabric_summary=MaterialFabricSummary(
                    dominant_color="wine",
                    transparency="semi_sheer",
                    surface_density="dense",
                    border_present=True,
                ),
            )
        ],
        preservation_requirements=PreservationRequirements(border_placement=["hem"]),
    )
    defaults.update(overrides)
    return VisualizationSpecification(**defaults)


def _observation(**overrides) -> GeneratedImageObservation:
    defaults = dict(
        garment_subject="anarkali suit on a mannequin",
        neckline="round",
        sleeve_length="three_quarter",
        sleeve_style="straight",
        dupatta_present=False,
        dominant_color="deep wine",
        surface_density="dense",
        border_present=True,
        transparency="semi_sheer",
    )
    defaults.update(overrides)
    return GeneratedImageObservation(**defaults)


def test_matching_observation_passes():
    overall, checks = compare_observation_to_specification(_observation(), _spec())
    assert overall == ValidationVerdict.PASS
    assert all(c.verdict in (ValidationVerdict.PASS, ValidationVerdict.UNKNOWN) for c in checks)


def test_silhouette_mismatch_detected():
    overall, checks = compare_observation_to_specification(_observation(garment_subject="a plain kurta"), _spec())
    silhouette = next(c for c in checks if c.name == "silhouette_match")
    assert silhouette.verdict == ValidationVerdict.FAIL


def test_sleeve_mismatch_matches_section_18_example():
    """Section 18's worked example: requested full sleeves, observed
    sleeveless."""
    spec = _spec(sleeves=SleevesVisualSpec(length="full", style="fitted"))
    overall, checks = compare_observation_to_specification(_observation(sleeve_length="sleeveless"), spec)
    sleeve = next(c for c in checks if c.name == "sleeve_match")
    assert sleeve.verdict == ValidationVerdict.FAIL


def test_dupatta_presence_mismatch_detected():
    spec = _spec(dupatta=DupattaVisualSpec(included=True))
    overall, checks = compare_observation_to_specification(_observation(dupatta_present=False), spec)
    dupatta = next(c for c in checks if c.name == "dupatta_match")
    assert dupatta.verdict == ValidationVerdict.FAIL


def test_color_family_mismatch_matches_section_19_example():
    """Section 19's worked example: deep wine fabric rendered as pink."""
    overall, checks = compare_observation_to_specification(_observation(dominant_color="bright pink"), _spec())
    color = next(c for c in checks if c.name == "color_match")
    assert color.verdict == ValidationVerdict.FAIL
    assert overall in (ValidationVerdict.PARTIAL, ValidationVerdict.FAIL)


def test_surface_density_gap_of_one_is_partial_not_fail():
    overall, checks = compare_observation_to_specification(_observation(surface_density="moderate"), _spec())
    density = next(c for c in checks if c.name == "surface_density_match")
    assert density.verdict == ValidationVerdict.PARTIAL


def test_surface_density_large_gap_fails():
    overall, checks = compare_observation_to_specification(_observation(surface_density="none"), _spec())
    density = next(c for c in checks if c.name == "surface_density_match")
    assert density.verdict == ValidationVerdict.FAIL


def test_border_presence_mismatch_detected_when_border_used():
    overall, checks = compare_observation_to_specification(_observation(border_present=False), _spec())
    border = next(c for c in checks if c.name == "border_presence_match")
    assert border.verdict == ValidationVerdict.FAIL


def test_border_check_unknown_when_design_does_not_use_border():
    spec = _spec(preservation_requirements=PreservationRequirements(border_placement=[], preserve_border=False))
    overall, checks = compare_observation_to_specification(_observation(border_present=False), spec)
    border = next(c for c in checks if c.name == "border_presence_match")
    assert border.verdict == ValidationVerdict.UNKNOWN


def test_all_unknown_observation_yields_unknown_overall():
    empty = GeneratedImageObservation()
    overall, checks = compare_observation_to_specification(empty, _spec())
    assert overall == ValidationVerdict.UNKNOWN
    assert all(c.verdict == ValidationVerdict.UNKNOWN for c in checks)


def test_single_mismatch_among_many_passes_is_partial():
    overall, checks = compare_observation_to_specification(_observation(neckline="v_neck"), _spec())
    assert overall == ValidationVerdict.PARTIAL


def test_multiple_mismatches_is_fail():
    overall, checks = compare_observation_to_specification(
        _observation(neckline="v_neck", sleeve_length="sleeveless"), _spec()
    )
    assert overall == ValidationVerdict.FAIL
