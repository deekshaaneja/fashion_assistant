"""Fabric domain model. `FabricProperties` fields are deliberately optional --
not every property of a real swatch is known, and the kernel must say "unknown"
rather than silently guessing a value that then looks authoritative downstream."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import (
    Drape,
    EmbellishmentTolerance,
    Season,
    Sheen,
    Stiffness,
    Stretch,
    StructureLevel,
    SurfaceDensity,
    Transparency,
    WeightClass,
)
from src.domain.models.common import DomainModel, Range


class FabricProperties(DomainModel):
    drape: Drape | None = None
    stiffness: Stiffness | None = None
    transparency: Transparency | None = None
    sheen: Sheen | None = None
    stretch: Stretch | None = None
    weight_class: WeightClass | None = None
    structure: StructureLevel | None = None
    embellishment_tolerance: EmbellishmentTolerance | None = None
    surface_density: SurfaceDensity = SurfaceDensity.NONE
    border_available: bool | None = None
    motif_directional: bool | None = None
    gsm: Range | None = None
    width_cm: Range | None = None


class Fabric(DomainModel):
    """Static/seeded knowledge about a fabric family (e.g. "organza"), not a
    specific physical swatch -- see `FabricObservation` in analyze_fabric's
    contract for the per-swatch/user-declared layer."""

    id: str
    name: str
    category: str  # broad family label, e.g. "sheer_synthetic", "silk_brocade"
    composition: str | None = None
    properties: FabricProperties = Field(default_factory=FabricProperties)
    seasonality: list[Season] = Field(default_factory=list)
    strong_fit_silhouettes: list[str] = Field(
        default_factory=list, description="curated silhouette ids this fabric is a BEST_USE anchor for"
    )
    avoid_silhouettes: list[str] = Field(
        default_factory=list, description="curated silhouette ids this fabric is an AVOID anchor for"
    )
    notes: str | None = None
