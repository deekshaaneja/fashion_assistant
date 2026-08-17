"""Input/output contracts for the analyze_fabric tool. Phase 1 accepts
structured metadata only -- image analysis is a later phase (see section 6)."""
from __future__ import annotations

from pydantic import Field

from src.domain.models.common import DomainModel
from src.domain.models.fabric import FabricProperties


class FabricObservation(DomainModel):
    """What the caller declares about a specific piece of fabric. `fabric_name`
    is matched against the seed catalog; any explicitly declared properties
    override the catalog's defaults for this specific swatch."""

    fabric_name: str
    declared_properties: FabricProperties = Field(default_factory=FabricProperties)
    available_metres: float | None = None
    fabric_width_cm: float | None = None
    notes: str | None = None


class FabricAnalysis(DomainModel):
    fabric_name: str
    resolved_fabric_id: str | None = None
    resolution_method: str  # exact | alias | partial | unresolved
    properties: FabricProperties
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    suitable_garment_families: list[str] = Field(default_factory=list)
    unsuitable_garment_families: list[str] = Field(default_factory=list)
    wear_category_lean: str | None = None  # indian | western | fusion | None if no strong lean
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
