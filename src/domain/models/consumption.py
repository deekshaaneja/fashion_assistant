"""Consumption seed rules + computed estimates. The rule engine
(`src/fashion_engine/consumption/calculate.py`) is deterministic arithmetic
over these -- never an LLM guess. Seed values are configurable starting
assumptions, not universal manufacturing truths (see docs/rule-engine.md).

Phase 1.2, sections 6-8: a missing curated rule now returns an explicit
`NO_CURATED_RULE` status with no metres at all, rather than a fabricated
generic band -- an honest "we don't know" beats false precision. When a rule
*is* used, the estimate exposes the exact `ConstructionAssumptions` it was
generated from, not assumptions invented after the fact to justify a number.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.domain.enums import ConsumptionStatus
from src.domain.models.common import Confidence, DomainModel, Range

# seed = a rough starting assumption, not independently verified.
# curated = cross-checked against a named real-world reference point (e.g.
#   the product brief's own "Medium blouse ~1m / Medium A-line ~3m / Medium
#   Anarkali ~5m" examples).
# boutique_override = supplied by a specific boutique for their own
#   construction practice, superseding the seed/curated default.
ConsumptionSource = Literal["seed", "curated", "boutique_override"]


class ConsumptionRule(DomainModel):
    garment_id: str
    silhouette_id: str
    reference_size: str = "M"
    reference_width_cm: float = 112.0  # ~44 inches
    base_metres: float
    grading_increment_pct: float = Field(
        default=0.06, description="fractional yardage change per standard-size step away from reference_size"
    )
    flare_modifier_pct: float = Field(
        default=0.12, description="fractional change per FlareLevel step away from the silhouette's own default"
    )
    sleeve_modifier_m: float = 0.0
    lining_modifier_m: float = 0.0
    border_modifier_m: float = 0.0
    directional_motif_wastage_pct: float = Field(
        default=0.0, description="extra wastage when the fabric has a directional motif and pieces must all match"
    )
    wastage_allowance_pct: float = 0.08
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    source: ConsumptionSource = "seed"
    notes: str | None = None


class ConstructionAssumptions(DomainModel):
    """Every input the yardage arithmetic was actually generated FROM (Phase
    1.2, section 7) -- the estimate is derived from exactly these values, not
    a number computed first and assumptions written afterward to match. A
    field left at its documented default (e.g. size defaulting to the rule's
    own reference size) is still listed here, never silently hidden."""

    fabric_width_cm: float
    size: str
    flare_level: str
    sleeve_allowance_included: bool
    lining_included: bool
    border_included: bool
    directional_motif: bool
    wastage_percent: float = Field(description="total wastage allowance actually applied, as a percentage")


class ConsumptionEstimate(DomainModel):
    garment_id: str
    silhouette_id: str
    status: ConsumptionStatus
    min_metres: float | None = Field(default=None, description="None when status is NO_CURATED_RULE")
    max_metres: float | None = Field(default=None, description="None when status is NO_CURATED_RULE")
    base_metres: float | None = None
    modifiers: dict[str, float] = Field(
        default_factory=dict,
        description="named numeric deltas/multipliers actually applied, e.g. "
        "{'size_grading_pct': 0.0, 'flare_adjustment_pct': -0.12, 'lining_m': 3.0, 'wastage_pct': 0.08}",
    )
    modifiers_applied: list[str] = Field(default_factory=list)
    construction_assumptions: ConstructionAssumptions | None = Field(
        default=None, description="None when status is NO_CURATED_RULE -- there is no rule to have assumed from"
    )
    assumptions: list[str] = Field(default_factory=list)
    rule_source: ConsumptionSource | None = None
    confidence: Confidence

    def as_range(self) -> Range | None:
        if self.min_metres is None or self.max_metres is None:
            return None
        return Range(min=self.min_metres, max=self.max_metres)
