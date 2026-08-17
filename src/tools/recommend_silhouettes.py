"""Tool: recommend_silhouettes -- Question A, "I have this fabric, what
should I make?"

Input: a fabric name (resolved against the seed catalog, gracefully
degrading to an unresolved/low-confidence profile rather than erroring) plus
optional declared per-swatch properties and a recommendation context.
Output: a ranked, decisively classified list of (garment, silhouette)
candidates plus explicit AVOID examples.
"""
from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.fabric import FabricProperties
from src.domain.models.recommendation import SilhouetteRecommendationResult
from src.fashion_engine.fabric.analyze import merge_fabric_properties
from src.fashion_engine.silhouettes.recommend import recommend_silhouettes as _recommend_silhouettes
from src.rules.repository import get_fabric_repository

__all__ = ["recommend_silhouettes"]


def recommend_silhouettes(
    fabric_name: str,
    declared_properties: FabricProperties | None = None,
    context: RecommendationContext | None = None,
) -> SilhouetteRecommendationResult:
    resolution = get_fabric_repository().resolve(fabric_name)
    fabric = resolution.profile
    if declared_properties is not None:
        merged = merge_fabric_properties(fabric.properties, declared_properties)
        fabric = fabric.model_copy(update={"properties": merged})

    result = _recommend_silhouettes(fabric, context, fabric_confidence=resolution.confidence)
    if resolution.method == "unresolved":
        result = result.model_copy(
            update={
                "assumptions": [
                    f"'{fabric_name}' did not match the seed catalog -- ranking used unknown/generic properties.",
                    *result.assumptions,
                ]
            }
        )
    return result
