from __future__ import annotations

from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
    DesignCandidate,
    DesignGarment,
    FabricUsageSpec,
    FinishingSpec,
    NecklineSpec,
    SleeveSpec,
)
from src.domain.models.recommendation import GarmentRef, SilhouetteRef
from src.fashion_engine.consumption.calculate import calculate_consumption
from src.fashion_engine.design.diversity import filter_diverse, similarity, too_similar


def _candidate(title: str, dna: DesignDNA, neckline: str = "round", sleeve: str = "three_quarter") -> DesignCandidate:
    consumption = calculate_consumption("suit", "a_line", size="M")
    return DesignCandidate(
        title=title,
        design_intent="test",
        garment=DesignGarment(
            garment=GarmentRef(id="suit", name="Suit"), silhouette=SilhouetteRef(id="a_line", name="A-Line")
        ),
        design_dna=dna,
        construction=ConstructionSpec(
            bodice_style="fitted", flare_level="moderate", flare_construction="controlled",
            garment_length="floor_length", rationale="r",
        ),
        neckline=NecklineSpec(type=neckline, rationale="r"),
        sleeves=SleeveSpec(length=sleeve, rationale="r"),
        decoration=DecorationSpec(level="MINIMAL", rationale="r"),
        finishing=FinishingSpec(seams="clean"),
        fabric_usage=FabricUsageSpec(main_fabric_id="organza", consumption=consumption),
    )


def test_identical_candidates_are_maximally_similar():
    dna = DesignDNA()
    a = _candidate("A", dna)
    b = _candidate("B", dna)
    assert similarity(a, b) == 1.0
    assert too_similar(a, b)


def test_opposite_dna_and_attributes_are_not_too_similar():
    a = _candidate("A", DesignDNA(traditional_contemporary=0.05, soft_architectural=0.05), neckline="round", sleeve="sleeveless")
    b = _candidate(
        "B",
        DesignDNA(traditional_contemporary=0.95, soft_architectural=0.95),
        neckline="deep_v",
        sleeve="full",
    )
    assert not too_similar(a, b)


def test_filter_diverse_keeps_only_distinct_candidates():
    dna = DesignDNA()
    identical = [_candidate(f"dup-{i}", dna) for i in range(3)]
    selected, rejected = filter_diverse(identical, count=3)
    assert len(selected) == 1
    assert rejected == 2


def test_filter_diverse_does_not_backfill_with_near_duplicates():
    """Structural attributes dominate the similarity signal now -- a
    'second direction' that's identical to the first on every structural
    axis and differs only in DesignDNA is still a cosmetic variation, not a
    genuinely distinct direction, so B here must differ structurally too."""
    dna_a = DesignDNA(traditional_contemporary=0.05)
    dna_b = DesignDNA(traditional_contemporary=0.95)
    candidates = [
        _candidate("A", dna_a, neckline="round", sleeve="three_quarter"),
        _candidate("A-again", dna_a, neckline="round", sleeve="three_quarter"),  # near-duplicate of A
        _candidate("B", dna_b, neckline="deep_v", sleeve="full"),  # structurally distinct direction
    ]
    selected, rejected = filter_diverse(candidates, count=3)
    # only 2 genuinely distinct directions exist -- must not pad with the near-duplicate
    assert len(selected) == 2
    assert rejected == 1
