"""DesignDNA: the internal aesthetic representation Phase 2 reasons about --
never a designer name (section 6). Every axis is a float in [0, 1]; the
*name* documents which end is 0 and which is 1 (e.g. `traditional_contemporary`
of 0.75 reads as "leaning contemporary"). Designer/aesthetic references are a
later-phase concern that would map INTO this representation, not replace it.
"""
from __future__ import annotations

import math

from pydantic import Field

from src.domain.models.common import DomainModel

_AXES = (
    "traditional_contemporary",
    "minimal_maximal",
    "soft_architectural",
    "romantic_sharp",
    "understated_glamorous",
    "heritage_modern",
    "fluid_structured",
    "subtle_statement",
)


class DesignDNA(DomainModel):
    """0.0 = the first word in the axis name, 1.0 = the second. E.g.
    `soft_architectural=0.1` reads as "soft"; `soft_architectural=0.9` reads
    as "architectural". 0.5 is genuinely neutral/balanced, not "unknown"."""

    traditional_contemporary: float = Field(default=0.5, ge=0.0, le=1.0)
    minimal_maximal: float = Field(default=0.5, ge=0.0, le=1.0)
    soft_architectural: float = Field(default=0.5, ge=0.0, le=1.0)
    romantic_sharp: float = Field(default=0.5, ge=0.0, le=1.0)
    understated_glamorous: float = Field(default=0.5, ge=0.0, le=1.0)
    heritage_modern: float = Field(default=0.5, ge=0.0, le=1.0)
    fluid_structured: float = Field(default=0.5, ge=0.0, le=1.0)
    subtle_statement: float = Field(default=0.5, ge=0.0, le=1.0)

    def distance(self, other: DesignDNA) -> float:
        """Euclidean distance across all 8 axes -- the primary structured
        signal the diversity checker uses (section 29: "use structured
        attributes first," not embeddings). Max possible distance is
        sqrt(8) ~= 2.83."""
        return math.sqrt(sum((getattr(self, axis) - getattr(other, axis)) ** 2 for axis in _AXES))

    def as_vector(self) -> dict[str, float]:
        return {axis: getattr(self, axis) for axis in _AXES}
