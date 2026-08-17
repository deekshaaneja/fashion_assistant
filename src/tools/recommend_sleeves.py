"""Tool: recommend_sleeves (Phase 2, section 11)."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import SleeveSpec
from src.fashion_engine.design.sleeves import recommend_sleeves as _recommend_sleeves
from src.rules.repository import get_fabric_repository

__all__ = ["recommend_sleeves"]


def recommend_sleeves(fabric_name: str, client_brief: ClientBrief | None = None) -> SleeveSpec:
    fabric = get_fabric_repository().resolve(fabric_name).profile
    return _recommend_sleeves(fabric, client_brief or ClientBrief())
