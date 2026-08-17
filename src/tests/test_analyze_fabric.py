from __future__ import annotations

from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_analysis import FabricObservation
from src.tools.analyze_fabric import analyze_fabric


def test_analyze_known_fabric_returns_catalog_properties():
    analysis = analyze_fabric(FabricObservation(fabric_name="organza"))
    assert analysis.resolution_method == "exact"
    assert analysis.properties.structure == "structured"
    assert analysis.confidence >= 0.9


def test_analyze_unresolved_fabric_states_assumption_not_a_guess():
    analysis = analyze_fabric(FabricObservation(fabric_name="xyz not a fabric"))
    assert analysis.resolution_method == "unresolved"
    assert analysis.resolved_fabric_id is None
    assert analysis.confidence < 0.3
    assert any("did not match" in a for a in analysis.assumptions)


def test_declared_properties_override_catalog_defaults():
    """'Embroidered organza' should read as densely decorated even though
    plain organza's catalog default is surface_density=none."""
    analysis = analyze_fabric(
        FabricObservation(fabric_name="organza", declared_properties=FabricProperties(surface_density="dense"))
    )
    assert analysis.properties.surface_density == "dense"
    assert any("overwork" in limitation for limitation in analysis.limitations)


def test_declared_none_value_is_still_an_explicit_override():
    """A field explicitly declared as its 'none'-equivalent value must still
    count as declared, not be confused with 'not declared'."""
    analysis = analyze_fabric(
        FabricObservation(fabric_name="banarasi", declared_properties=FabricProperties(surface_density="none"))
    )
    assert analysis.properties.surface_density == "none"


def test_declared_properties_boost_confidence():
    # Uses a partial-match fabric name (lower base confidence) so there's
    # room for the declared-properties boost to actually show -- an exact
    # match is already at the confidence ceiling either way.
    without = analyze_fabric(FabricObservation(fabric_name="embroidered organza"))
    with_declared = analyze_fabric(
        FabricObservation(
            fabric_name="embroidered organza", declared_properties=FabricProperties(surface_density="dense")
        )
    )
    assert with_declared.confidence > without.confidence


def test_example_from_product_brief_embroidered_organza():
    """Matches the section 6 worked example: embroidered organza should
    surface structured-silhouette strengths and over-decoration limitations."""
    analysis = analyze_fabric(
        FabricObservation(fabric_name="embroidered organza", declared_properties=FabricProperties(surface_density="dense"))
    )
    assert analysis.resolution_method in ("partial", "exact")
    assert any("structured" in s for s in analysis.strengths)
    assert any("overwork" in limitation for limitation in analysis.limitations)
