"""Tool: recommend_styling(garment, silhouette, fabric, context).

Input: garment id, silhouette id, fabric name, and a recommendation context.
Output: a structured StylingSpec (neckline, sleeve, length, flare, bottom
style, dupatta, lining, finishing, decoration intensity) -- always a
structured object, never free prose.
"""
from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.styling import StylingSpec
from src.fashion_engine.styling.recommend import recommend_styling as _recommend_styling
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

__all__ = ["recommend_styling"]


def recommend_styling(
    garment_id: str,
    silhouette_id: str,
    fabric_name: str,
    context: RecommendationContext | None = None,
) -> StylingSpec:
    garment = get_garment_repository().get(garment_id)
    if garment is None:
        raise ValueError(f"Unknown garment id '{garment_id}'.")

    silhouette = get_silhouette_repository().get(silhouette_id)
    if silhouette is None:
        raise ValueError(f"Unknown silhouette id '{silhouette_id}'.")

    fabric = get_fabric_repository().resolve(fabric_name).profile
    return _recommend_styling(garment, silhouette, fabric, context)
