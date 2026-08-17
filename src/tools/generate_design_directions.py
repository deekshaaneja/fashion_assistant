"""Tool: generate_design_directions -- Phase 2's core capability, "what
should I actually design?" (section 7).

Input: a fabric name (resolved against the seed catalog, same graceful
degradation as Phase 1's recommend_silhouettes) plus optional declared
per-swatch properties, a fashion context, a client brief, and an optional
fixed (garment, silhouette) selection.
Output: up to `count` complete, validated, ranked DesignProposals plus a
validation report and generation metadata.
"""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import DesignDirectionsResult
from src.domain.models.fabric import FabricProperties
from src.fashion_engine.design.generate import generate_design_directions as _generate_design_directions
from src.fashion_engine.fabric.analyze import merge_fabric_properties
from src.rules.repository import get_fabric_repository

__all__ = ["generate_design_directions"]


def generate_design_directions(
    fabric_name: str,
    declared_properties: FabricProperties | None = None,
    fashion_context: RecommendationContext | None = None,
    client_brief: ClientBrief | None = None,
    selected_garment_id: str | None = None,
    selected_silhouette_id: str | None = None,
    count: int = 3,
) -> DesignDirectionsResult:
    resolution = get_fabric_repository().resolve(fabric_name)
    fabric = resolution.profile
    if declared_properties is not None:
        merged = merge_fabric_properties(fabric.properties, declared_properties)
        fabric = fabric.model_copy(update={"properties": merged})

    return _generate_design_directions(
        fabric,
        fashion_context,
        client_brief,
        selected_garment_id=selected_garment_id,
        selected_silhouette_id=selected_silhouette_id,
        count=count,
    )
