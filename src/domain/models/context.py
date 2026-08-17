"""Shared input context for recommend_silhouettes / recommend_fabrics /
recommend_styling. Optional throughout -- the kernel makes a stated
assumption rather than blocking when something isn't given (section 18 of
the product brief)."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import Occasion, Season, StandardSize, WearCategory
from src.domain.models.common import DomainModel


class RecommendationContext(DomainModel):
    occasion: Occasion | None = None
    season: Season | None = None
    wear_category_preference: WearCategory | None = None
    size: StandardSize | None = None
    available_metres: float | None = None
    fabric_width_cm: float = 112.0  # ~44in, the kernel's stated default when not given
    top_n: int = Field(default=5, ge=1, le=15)
