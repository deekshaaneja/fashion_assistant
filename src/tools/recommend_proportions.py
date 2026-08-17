"""Tool: recommend_proportions (Phase 2, section 12)."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import ProportionSpec
from src.domain.models.fabric import FabricProperties
from src.fashion_engine.design.constraints import build_design_constraints
from src.fashion_engine.design.proportions import recommend_proportions as _recommend_proportions
from src.fashion_engine.fabric.analyze import merge_fabric_properties
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

__all__ = ["recommend_proportions"]


def recommend_proportions(
    fabric_name: str,
    garment_id: str,
    silhouette_id: str,
    declared_properties: FabricProperties | None = None,
    fashion_context: RecommendationContext | None = None,
    client_brief: ClientBrief | None = None,
    has_dupatta: bool = False,
    has_overlay: bool = False,
) -> ProportionSpec:
    resolution = get_fabric_repository().resolve(fabric_name)
    fabric = resolution.profile
    if declared_properties is not None:
        merged = merge_fabric_properties(fabric.properties, declared_properties)
        fabric = fabric.model_copy(update={"properties": merged})

    garment = get_garment_repository().get(garment_id)
    silhouette = get_silhouette_repository().get(silhouette_id)
    if garment is None:
        raise ValueError(f"Unknown garment id '{garment_id}'.")
    if silhouette is None:
        raise ValueError(f"Unknown silhouette id '{silhouette_id}'.")

    context = fashion_context or RecommendationContext()
    brief = client_brief or ClientBrief()
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)

    return _recommend_proportions(
        garment_length="floor_length",
        waist_placement="natural",
        effective_flare_level=constraints.effective_flare_level,
        flare_construction=constraints.flare_construction,
        client_brief=brief,
        has_dupatta=has_dupatta,
        has_overlay=has_overlay,
    )
