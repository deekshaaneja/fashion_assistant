"""Structured output of recommend_styling."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import NecklineType, SleeveLength
from src.domain.models.common import DomainModel


class StylingSpec(DomainModel):
    neckline: NecklineType | None = None
    sleeve: SleeveLength | None = None
    length: str | None = None  # e.g. "calf_length", "floor_length", "knee_length"
    flare: str | None = None  # e.g. "minimal", "moderate", "high", "dramatic"
    waist_placement: str | None = None  # e.g. "natural", "empire", "dropped"
    bottom_style: str | None = None  # e.g. "straight_trousers", "palazzo", "flared_skirt"
    dupatta: str | None = None
    lining: str | None = None
    finishing: str | None = None
    decoration_intensity: str = "none"  # none | restrained | moderate | heavy
    reasoning: list[str] = Field(default_factory=list)
