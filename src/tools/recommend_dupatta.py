"""Tool: recommend_dupatta (Phase 2, section 16). Decides whether a dupatta
belongs in the design at all before deciding its fabric/color/border."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import DupattaSpec
from src.fashion_engine.design.dupatta import recommend_dupatta as _recommend_dupatta
from src.rules.repository import get_fabric_repository, get_garment_repository

__all__ = ["recommend_dupatta"]


def recommend_dupatta(
    garment_id: str,
    fabric_name: str,
    dupatta_philosophy: str = "lightweight_contrast_or_tonal",
    client_brief: ClientBrief | None = None,
) -> DupattaSpec | None:
    garment = get_garment_repository().get(garment_id)
    if garment is None:
        raise ValueError(f"Unknown garment id '{garment_id}'.")
    fabric = get_fabric_repository().resolve(fabric_name).profile
    return _recommend_dupatta(garment, fabric, dupatta_philosophy, client_brief or ClientBrief())
