"""Tool: generate_design_colorways (Phase 2, section 15). Expands Phase 1's
single-palette generate_colorways into complete, per-component coordinated
color stories for an already-generated design."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import DesignColorway, DesignProposal
from src.fashion_engine.design.colorways import generate_design_colorways as _generate_design_colorways
from src.rules.repository import get_fabric_repository

__all__ = ["generate_design_colorways"]


def generate_design_colorways(
    fabric_name: str,
    design: DesignProposal,
    client_brief: ClientBrief | None = None,
    fashion_context: RecommendationContext | None = None,
    count: int = 3,
) -> list[DesignColorway]:
    fabric = get_fabric_repository().resolve(fabric_name).profile
    return _generate_design_colorways(
        fabric,
        design.title,
        design.construction.flare_construction,
        client_brief or ClientBrief(),
        fashion_context,
        count=count,
    )
