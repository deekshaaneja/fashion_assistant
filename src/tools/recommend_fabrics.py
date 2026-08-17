"""Tool: recommend_fabrics -- Question B, "I want this silhouette, what
fabric should I use?"

Input: a silhouette id (e.g. "anarkali") and, when that silhouette applies to
more than one garment category (e.g. "flared" applies to suit/lehenga/gown/
skirt_top), a garment id to disambiguate -- if omitted, the kernel assumes
the first applicable garment and says so explicitly rather than guessing
silently.
Output: a ranked, decisively classified list of fabric candidates plus
explicit AVOID examples.
"""
from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.recommendation import FabricRecommendationResult
from src.fashion_engine.fabric.recommend import recommend_fabrics as _recommend_fabrics
from src.rules.repository import get_garment_repository, get_silhouette_repository

__all__ = ["recommend_fabrics"]


def recommend_fabrics(
    silhouette_id: str,
    garment_id: str | None = None,
    context: RecommendationContext | None = None,
) -> FabricRecommendationResult:
    silhouette_repo = get_silhouette_repository()
    garment_repo = get_garment_repository()

    silhouette = silhouette_repo.get(silhouette_id)
    if silhouette is None:
        raise ValueError(f"Unknown silhouette id '{silhouette_id}'.")

    assumption: str | None = None
    if garment_id is None:
        if not silhouette.applicable_garment_ids:
            raise ValueError(f"Silhouette '{silhouette_id}' has no applicable garments seeded.")
        garment_id = silhouette.applicable_garment_ids[0]
        if len(silhouette.applicable_garment_ids) > 1:
            assumption = (
                f"No garment specified for '{silhouette.name}' -- assumed '{garment_id}' "
                f"(also applies to: {', '.join(silhouette.applicable_garment_ids[1:])})."
            )

    garment = garment_repo.get(garment_id)
    if garment is None:
        raise ValueError(f"Unknown garment id '{garment_id}'.")
    if garment_id not in silhouette.applicable_garment_ids:
        raise ValueError(f"Silhouette '{silhouette_id}' does not apply to garment '{garment_id}'.")

    result = _recommend_fabrics(garment, silhouette, context)
    if assumption:
        result = result.model_copy(update={"assumptions": [assumption, *result.assumptions]})
    return result
