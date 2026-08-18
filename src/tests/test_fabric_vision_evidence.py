from __future__ import annotations

from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import EvidenceType, VisionModelOutput, VisionPropertyOut
from src.fashion_engine.fabric.vision_evidence import (
    apply_user_confirmed_fabric_name,
    apply_user_overrides,
    build_fabric_properties,
    normalize_observation,
)


def _output(**overrides) -> VisionModelOutput:
    base = dict(
        image_subject="fabric_swatch",
        subject_reason="looks like a swatch",
        transparency=VisionPropertyOut(value="semi_sheer", certainty="medium", reason="r"),
        sheen=VisionPropertyOut(value="subtle_sheen", certainty="low"),
        drape=VisionPropertyOut(certainty="unknown"),
        stiffness=VisionPropertyOut(certainty="unknown"),
        structure=VisionPropertyOut(certainty="unknown"),
        surface_density=VisionPropertyOut(value="sparse", certainty="high"),
        weight_class=VisionPropertyOut(certainty="unknown"),
        embellishment_tolerance=VisionPropertyOut(certainty="unknown"),
        fabric_family=VisionPropertyOut(value="organza", certainty="medium", alternative="tissue"),
    )
    base.update(overrides)
    return VisionModelOutput(**base)


def test_unknown_certainty_produces_unknown_evidence_with_null_value():
    obs = normalize_observation(_output(), ["real_image_id"])
    drape = next(e for e in obs.evidence if e.property == "drape")
    assert drape.evidence_type == EvidenceType.UNKNOWN
    assert drape.value is None
    assert drape.confidence == 0.0


def test_unrecognized_value_becomes_unknown_not_forced():
    output = _output(sheen=VisionPropertyOut(value="sparkly disco ball", certainty="high"))
    obs = normalize_observation(output, ["img1"])
    sheen = next(e for e in obs.evidence if e.property == "sheen")
    assert sheen.evidence_type == EvidenceType.UNKNOWN
    assert sheen.value is None
    assert any("unrecognized" in w.lower() for w in obs.warnings)


def test_value_normalization_is_case_and_spacing_insensitive():
    output = _output(transparency=VisionPropertyOut(value="Semi Sheer", certainty="high"))
    obs = normalize_observation(output, ["img1"])
    transparency = next(e for e in obs.evidence if e.property == "transparency")
    assert transparency.value == "semi_sheer"


def test_observed_vs_inferred_evidence_type_split():
    obs = normalize_observation(_output(), ["img1"])
    by_property = {e.property: e for e in obs.evidence}
    assert by_property["transparency"].evidence_type == EvidenceType.OBSERVED
    assert by_property["surface_density"].evidence_type == EvidenceType.OBSERVED
    assert by_property["fabric_family"].evidence_type == EvidenceType.INFERRED


def test_source_images_are_translated_from_labels_to_real_ids():
    output = _output(transparency=VisionPropertyOut(value="sheer", certainty="high", source_images=["image_1"]))
    obs = normalize_observation(output, ["real-uuid-123"])
    transparency = next(e for e in obs.evidence if e.property == "transparency")
    assert transparency.source_images == ["real-uuid-123"]


def test_always_unknown_properties_are_present_regardless_of_model_output():
    obs = normalize_observation(_output(), ["img1"])
    by_property = {e.property: e for e in obs.evidence}
    for name in ("gsm", "width_cm", "stretch"):
        assert by_property[name].evidence_type == EvidenceType.UNKNOWN
        assert by_property[name].value is None


def test_fabric_family_alternative_is_preserved():
    obs = normalize_observation(_output(), ["img1"])
    fabric_family = next(e for e in obs.evidence if e.property == "fabric_family")
    assert fabric_family.value == "organza"
    assert fabric_family.alternatives
    assert fabric_family.alternatives[0].value == "tissue"


def test_build_fabric_properties_only_sets_non_unknown_fields():
    obs = normalize_observation(_output(), ["img1"])
    props = build_fabric_properties(obs.evidence)
    assert props.transparency == "semi_sheer"
    assert props.surface_density == "sparse"
    assert props.drape is None  # unknown -- never guessed
    assert props.weight_class is None


def test_apply_user_overrides_precedence_and_keeps_ai_inference_as_alternative():
    obs = normalize_observation(_output(), ["img1"])
    user_properties = FabricProperties(transparency="sheer")
    updated = apply_user_overrides(obs.evidence, user_properties)
    transparency = next(e for e in updated if e.property == "transparency")
    assert transparency.evidence_type == EvidenceType.USER_CONFIRMED
    assert transparency.value == "sheer"
    assert transparency.confidence == 1.0
    assert transparency.alternatives
    assert transparency.alternatives[0].value == "semi_sheer"  # the prior AI inference, preserved for audit


def test_apply_user_overrides_noop_when_nothing_confirmed():
    obs = normalize_observation(_output(), ["img1"])
    updated = apply_user_overrides(obs.evidence, None)
    assert updated == obs.evidence


def test_apply_user_confirmed_fabric_name_overrides_vision_inference():
    obs = normalize_observation(_output(), ["img1"])
    updated = apply_user_confirmed_fabric_name(obs.evidence, "tissue silk")
    fabric_family = next(e for e in updated if e.property == "fabric_family")
    assert fabric_family.value == "tissue silk"
    assert fabric_family.evidence_type == EvidenceType.USER_CONFIRMED
    assert fabric_family.alternatives[0].value == "organza"


def test_non_fabric_subject_is_normalized_correctly():
    obs = normalize_observation(_output(image_subject="non_fabric"), ["img1"])
    assert obs.image_subject == "non_fabric"
    assert obs.subject_confidence > 0.5


def test_uncertain_subject_gets_low_confidence():
    obs = normalize_observation(_output(image_subject="something weird"), ["img1"])
    assert obs.image_subject == "uncertain"
    assert obs.subject_confidence < 0.5
