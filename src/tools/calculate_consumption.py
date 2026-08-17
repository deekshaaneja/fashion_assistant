"""Tool: calculate_consumption(garment, silhouette, size, measurements,
fabric_width, options).

Deterministic yardage estimate -- always a min/max range with stated
assumptions and a confidence score, never a single fake-exact number.
"""
from __future__ import annotations

from src.domain.models.consumption import ConsumptionEstimate
from src.fashion_engine.consumption.calculate import calculate_consumption as _calculate_consumption
from src.rules.repository import get_garment_repository, get_silhouette_repository

__all__ = ["calculate_consumption"]


def calculate_consumption(
    garment_id: str,
    silhouette_id: str,
    size: str | None = None,
    fabric_width_cm: float = 112.0,
    flare_level: str | None = None,
    include_sleeve_allowance: bool = False,
    include_lining: bool = True,
    include_border: bool = False,
    directional_motif: bool = False,
    batch_quantity: int = 1,
) -> ConsumptionEstimate:
    if get_garment_repository().get(garment_id) is None:
        raise ValueError(f"Unknown garment id '{garment_id}'.")
    if get_silhouette_repository().get(silhouette_id) is None:
        raise ValueError(f"Unknown silhouette id '{silhouette_id}'.")

    return _calculate_consumption(
        garment_id,
        silhouette_id,
        size=size,
        fabric_width_cm=fabric_width_cm,
        flare_level=flare_level,
        include_sleeve_allowance=include_sleeve_allowance,
        include_lining=include_lining,
        include_border=include_border,
        directional_motif=directional_motif,
        batch_quantity=batch_quantity,
    )
