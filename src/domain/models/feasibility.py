"""Material feasibility: can a specific design actually be cut from the
fabric on hand? Deliberately a *different* question from design/context
suitability (see `src/domain/models/recommendation.py`) -- see
docs/rule-engine.md's "Three questions, not one" section."""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import MaterialFeasibilityStatus
from src.domain.models.common import DomainModel, Range


class FeasibilityResult(DomainModel):
    """Output of the standalone `check_fabric_feasibility` tool, which always
    receives an explicit required range from its caller -- so it can always
    determine a real status and never returns `UNKNOWN` itself (that status
    only arises one level up, in `MaterialFeasibility`, before a required
    range can even be computed -- e.g. no curated consumption rule)."""

    status: MaterialFeasibilityStatus
    available_metres: float
    required_range: Range
    shortage_range: Range | None = None  # None when feasible
    redesign_options: list[str] = Field(default_factory=list)
    reasoning: str


class MaterialFeasibility(DomainModel):
    """The material-feasibility facet of a candidate evaluation (Phase 1.2,
    section 1C) -- a flat, directly-renderable shape, deliberately separate
    from `recommendation_classification`. `UNKNOWN` when either no available
    quantity was given or no curated consumption rule exists to estimate
    required yardage against; in both cases feasibility cannot be honestly
    claimed either way."""

    status: MaterialFeasibilityStatus
    available_metres: float | None = None
    required_min_metres: float | None = None
    required_max_metres: float | None = None
    shortage_min_metres: float | None = None
    shortage_max_metres: float | None = None
    redesign_options: list[str] = Field(default_factory=list)
    reasoning: str
