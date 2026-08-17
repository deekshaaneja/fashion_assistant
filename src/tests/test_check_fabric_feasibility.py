from __future__ import annotations

from src.domain.models.common import Range
from src.tools.check_fabric_feasibility import check_fabric_feasibility


def test_feasible_when_enough_fabric():
    result = check_fabric_feasibility(6.0, Range(min=5.0, max=5.5))
    assert result.status == "FEASIBLE"
    assert result.shortage_range is None
    assert result.redesign_options == []


def test_marginal_just_under_minimum():
    result = check_fabric_feasibility(4.85, Range(min=5.0, max=5.5))
    assert result.status == "MARGINAL"
    assert result.redesign_options


def test_insufficient_with_shortage_and_redesign_options():
    """Matches section 11's worked example: 3.0m available, 4.8-5.2m
    required -> insufficient with a shortage and concrete redesign options."""
    result = check_fabric_feasibility(3.0, Range(min=4.8, max=5.2), garment_name="Suit", silhouette_name="Anarkali")
    assert result.status == "INSUFFICIENT"
    assert result.shortage_range is not None
    assert 1.5 <= result.shortage_range.min <= 2.5
    assert len(result.redesign_options) >= 3


def test_high_flare_redesign_option_prioritized_first():
    result = check_fabric_feasibility(2.0, Range(min=5.0, max=5.5), high_flare=True)
    assert "flare" in result.redesign_options[0].lower()


def test_directional_motif_adds_a_specific_redesign_option():
    result = check_fabric_feasibility(2.0, Range(min=5.0, max=5.5), has_directional_motif=True)
    assert any("directional motif" in o.lower() for o in result.redesign_options)
