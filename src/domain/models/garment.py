"""Garment (broad category, e.g. "suit", "lehenga", "gown") and Silhouette
(the shape applied to a garment, e.g. "straight", "a_line", "anarkali") are
kept as two separate, composable concepts -- a named outfit like "A-line suit"
is the pair (garment=suit, silhouette=a_line), not one flat enum value. Both
are seeded from data (`data/seed/garments.yaml`, `data/seed/silhouettes.yaml`),
not hardcoded as Python enums, so new entries never require a code change."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import FlareConstruction, FlareLevel, StructureLevel, WearCategory
from src.domain.models.common import DomainModel


class Garment(DomainModel):
    id: str
    name: str
    wear_category: WearCategory
    typical_components: list[str] = Field(
        default_factory=list, description="e.g. top, bottom, dupatta, blouse, lining, cape, jacket"
    )
    occasions_fit: list[str] = Field(default_factory=list)
    description: str


class Silhouette(DomainModel):
    id: str
    name: str
    applicable_garment_ids: list[str] = Field(
        default_factory=list, description="which Garment ids this silhouette shape can apply to"
    )
    default_flare_level: FlareLevel = FlareLevel.MODERATE
    # How the flare volume is actually built, not just how much of it there
    # is (Phase 1.2, section 9) -- a crisp/stiff fabric can be an *excellent*
    # match for CONTROLLED volume (its own body gives clean architectural
    # lines) while a poor one for GATHERED/DRAMATIC volume (needs drape to
    # move rather than stand stiffly). See docs/rule-engine.md.
    flare_construction: FlareConstruction = FlareConstruction.CONTROLLED
    structure_affinity: StructureLevel = StructureLevel.SEMI_STRUCTURED
    aesthetic_tags: list[str] = Field(default_factory=list)
    description: str
