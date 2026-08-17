"""ClientBrief: what the client told the boutique they want, for a single
consultation. Phase 2 scope is ephemeral -- no CRM, no client history (section
5); every field is optional so the engine works with a partial brief."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import NecklineType, Occasion, SleeveLength, WearCategory
from src.domain.models.common import DomainModel


class ClientBrief(DomainModel):
    occasion: Occasion | None = None
    wear_category_preference: WearCategory | None = None
    desired_aesthetic: list[str] = Field(
        default_factory=list, description="free-form aesthetic tags, e.g. ['elegant', 'contemporary']"
    )
    desired_formality: str | None = None
    preferred_fit: str | None = None  # e.g. "fitted", "relaxed"
    preferred_coverage: str | None = None  # e.g. "modest", "moderate", "open"
    preferred_sleeve: SleeveLength | None = None
    preferred_neckline: NecklineType | None = None
    preferred_length: str | None = None  # e.g. "floor_length", "ankle_length"
    color_preferences: list[str] = Field(default_factory=list)
    disliked_colors: list[str] = Field(default_factory=list)
    embellishment_preference: str | None = None  # "none" | "minimal" | "moderate" | "heavy"
    traditional_contemporary_lean: float | None = Field(
        default=None, ge=0.0, le=1.0, description="0=traditional, 1=contemporary -- same scale as DesignDNA"
    )
    understated_statement_lean: float | None = Field(
        default=None, ge=0.0, le=1.0, description="0=understated, 1=statement -- same scale as DesignDNA"
    )
    budget_tier: str | None = None  # "budget" | "mid" | "luxury"
    notes: str | None = None
