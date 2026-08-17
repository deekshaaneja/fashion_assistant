"""Tool: generate_colorways(fabric, garment, occasion, aesthetic_context).

Structured colorway engine only -- no image generation in Phase 1 (section
12). All color relationships are computed via deterministic HSL math.
"""
from __future__ import annotations

from src.domain.models.colorway import Colorway
from src.domain.models.context import RecommendationContext
from src.fashion_engine.colors.generate import generate_colorways as _generate_colorways
from src.rules.repository import get_fabric_repository, get_garment_repository

__all__ = ["generate_colorways"]


def generate_colorways(
    fabric_name: str,
    garment_id: str | None = None,
    context: RecommendationContext | None = None,
) -> Colorway:
    fabric = get_fabric_repository().resolve(fabric_name).profile
    garment = get_garment_repository().get(garment_id) if garment_id else None
    return _generate_colorways(fabric, garment, context)
