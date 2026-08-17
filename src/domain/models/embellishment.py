"""Embellishment technique knowledge backing recommend_styling."""
from __future__ import annotations

from src.domain.enums import EmbellishmentTolerance, EmbellishmentType
from src.domain.models.common import DomainModel


class EmbellishmentTechnique(DomainModel):
    id: str
    type: EmbellishmentType
    display_name: str
    min_fabric_embellishment_tolerance: EmbellishmentTolerance
    density_guidance: str  # sparse | moderate | dense
    notes: str | None = None
