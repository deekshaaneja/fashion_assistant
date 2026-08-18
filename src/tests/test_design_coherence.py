from __future__ import annotations

from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
    DecorationTreatment,
    DesignCandidate,
    DesignGarment,
    DupattaSpec,
    FabricUsageSpec,
    FinishingSpec,
    NecklineSpec,
    SleeveSpec,
)
from src.domain.models.recommendation import GarmentRef, SilhouetteRef
from src.fashion_engine.consumption.calculate import calculate_consumption
from src.fashion_engine.design.coherence import check_coherence, normalize_coherence


def _candidate(**overrides) -> DesignCandidate:
    consumption = calculate_consumption("suit", "a_line", size="M")
    defaults = dict(
        title="Test",
        design_intent="A test direction.",
        garment=DesignGarment(
            garment=GarmentRef(id="suit", name="Suit"), silhouette=SilhouetteRef(id="a_line", name="A-Line")
        ),
        design_dna={},
        construction=ConstructionSpec(
            bodice_style="fitted",
            flare_level="moderate",
            flare_construction="controlled",
            garment_length="floor_length",
            rationale="r",
        ),
        neckline=NecklineSpec(type="round", rationale="r"),
        sleeves=SleeveSpec(length="three_quarter", rationale="r"),
        decoration=DecorationSpec(level="MINIMAL", rationale="r"),
        finishing=FinishingSpec(seams="clean"),
        fabric_usage=FabricUsageSpec(main_fabric_id="organza", consumption=consumption),
    )
    defaults.update(overrides)
    return DesignCandidate(**defaults)


def test_normalizes_sleeveless_with_cuff_treatment():
    candidate = _candidate(sleeves=SleeveSpec(length="sleeveless", cuff_treatment="beaded cuff", rationale="r"))
    normalized, notes = normalize_coherence(candidate)
    assert normalized.sleeves.cuff_treatment is None
    assert any("cuff" in note for note in notes)
    assert check_coherence(normalized) == []


def test_normalizes_excluded_dupatta_with_leftover_attributes():
    candidate = _candidate(
        dupatta=DupattaSpec(included=False, border="heavy contrast border", weight="light", rationale="omitted")
    )
    normalized, notes = normalize_coherence(candidate)
    assert normalized.dupatta.border is None
    assert normalized.dupatta.weight is None
    assert any("dupatta" in note for note in notes)
    assert check_coherence(normalized) == []


def test_normalizes_no_additional_decoration_with_treatments():
    candidate = _candidate(
        decoration=DecorationSpec(
            level="NO_ADDITIONAL_DECORATION",
            treatments=[DecorationTreatment(material="zari", intensity="minimal", reason="r")],
            rationale="r",
        )
    )
    normalized, notes = normalize_coherence(candidate)
    assert normalized.decoration.treatments == []
    assert any("decoration" in note.lower() for note in notes)
    assert check_coherence(normalized) == []


def test_coherent_candidate_is_left_untouched():
    candidate = _candidate()
    normalized, notes = normalize_coherence(candidate)
    assert notes == []
    assert normalized == candidate
    assert check_coherence(candidate) == []


def test_check_coherence_flags_dramatic_construction_with_low_flare_level():
    candidate = _candidate(
        construction=ConstructionSpec(
            bodice_style="fitted",
            flare_level="minimal",
            flare_construction="dramatic",
            garment_length="floor_length",
            rationale="r",
        )
    )
    issues = check_coherence(candidate)
    assert any("flare_construction" in issue for issue in issues)
