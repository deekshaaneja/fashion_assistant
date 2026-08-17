"""Output of generate_colorways -- structured only, no image generation in
Phase 1 (see section 12 of the product brief)."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import Classification, ColorHarmonyType
from src.domain.models.common import DomainModel


class ColorSpec(DomainModel):
    name: str
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    role: str  # main | supporting | metallic_accent | embroidery


class Colorway(DomainModel):
    harmony_type: ColorHarmonyType
    main_colors: list[ColorSpec] = Field(default_factory=list)
    supporting_colors: list[ColorSpec] = Field(default_factory=list)
    metallic_accents: list[ColorSpec] = Field(default_factory=list)
    embroidery_colors: list[ColorSpec] = Field(default_factory=list)
    dupatta_direction: str | None = None
    classification: Classification
    reasoning: list[str] = Field(default_factory=list)
