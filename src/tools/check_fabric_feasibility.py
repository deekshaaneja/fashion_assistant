"""Tool: check_fabric_feasibility(available_metres, required_range,
fabric_width, design_context).

Returns FEASIBLE / MARGINAL / INSUFFICIENT plus, when short, a shortage
range and rule-based redesign options.
"""
from __future__ import annotations

from src.domain.models.common import Range
from src.domain.models.feasibility import FeasibilityResult
from src.fashion_engine.feasibility.check import check_fabric_feasibility as _check_fabric_feasibility

__all__ = ["check_fabric_feasibility"]


def check_fabric_feasibility(
    available_metres: float,
    required_range: Range,
    garment_name: str | None = None,
    silhouette_name: str | None = None,
    high_flare: bool = False,
    has_directional_motif: bool = False,
) -> FeasibilityResult:
    return _check_fabric_feasibility(
        available_metres,
        required_range,
        garment_name=garment_name,
        silhouette_name=silhouette_name,
        high_flare=high_flare,
        has_directional_motif=has_directional_motif,
    )
