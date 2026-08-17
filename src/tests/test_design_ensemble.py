from __future__ import annotations

from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import (
    ConstructionSpec,
    DecorationSpec,
    DesignCandidate,
    DesignGarment,
    DupattaSpec,
    FabricUsageSpec,
    FinishingSpec,
    LiningSpec,
    NecklineSpec,
    SleeveSpec,
)
from src.domain.models.recommendation import GarmentRef, SilhouetteRef
from src.fashion_engine.consumption.calculate import calculate_consumption
from src.fashion_engine.design.ensemble import design_ensemble
from src.rules.repository import get_garment_repository


def _candidate(garment_id: str, silhouette_id: str, **overrides) -> DesignCandidate:
    consumption = calculate_consumption(garment_id, silhouette_id, size="M")
    defaults = dict(
        title="Test",
        design_intent="test",
        garment=DesignGarment(
            garment=GarmentRef(id=garment_id, name=garment_id),
            silhouette=SilhouetteRef(id=silhouette_id, name=silhouette_id),
        ),
        design_dna=DesignDNA(),
        construction=ConstructionSpec(
            bodice_style="fitted", flare_level="moderate", flare_construction="controlled",
            garment_length="floor_length", rationale="r",
        ),
        neckline=NecklineSpec(type="round", rationale="r"),
        sleeves=SleeveSpec(length="three_quarter", rationale="r"),
        decoration=DecorationSpec(level="MINIMAL", rationale="r"),
        finishing=FinishingSpec(seams="clean"),
        fabric_usage=FabricUsageSpec(main_fabric_id="organza", consumption=consumption),
    )
    defaults.update(overrides)
    return DesignCandidate(**defaults)


def test_suit_ensemble_has_no_blouse_jacket_or_cape():
    garment = get_garment_repository().get("suit")
    candidate = _candidate("suit", "a_line", dupatta=DupattaSpec(included=True, rationale="r"))
    ensemble = design_ensemble(candidate, garment)
    component_names = {c.component for c in ensemble.components}
    assert "main_garment" in component_names
    assert "blouse" not in component_names
    assert "jacket" not in component_names
    assert "cape" not in component_names


def test_lehenga_ensemble_has_a_blouse_component():
    garment = get_garment_repository().get("lehenga")
    candidate = _candidate("lehenga", "a_line", dupatta=DupattaSpec(included=True, rationale="r"))
    ensemble = design_ensemble(candidate, garment)
    component_names = {c.component for c in ensemble.components}
    assert "blouse" in component_names


def test_dupatta_omitted_shows_as_not_included_not_missing():
    garment = get_garment_repository().get("suit")
    candidate = _candidate("suit", "a_line", dupatta=DupattaSpec(included=False, rationale="omitted on purpose"))
    ensemble = design_ensemble(candidate, garment)
    dupatta_entries = [c for c in ensemble.components if c.component == "dupatta"]
    assert len(dupatta_entries) == 1
    assert dupatta_entries[0].included is False


def test_lining_only_appears_when_required():
    garment = get_garment_repository().get("suit")
    candidate = _candidate("suit", "a_line", lining=LiningSpec(required=False, rationale="not needed"))
    ensemble = design_ensemble(candidate, garment)
    assert not any(c.component == "lining" for c in ensemble.components)
