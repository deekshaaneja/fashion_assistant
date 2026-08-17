"""Structured, ranked outputs shared by recommend_silhouettes and
recommend_fabrics. Both directions produce the same shape of thing: a ranked,
classified candidate with transparent reasons -- never a flat unranked list.

Phase 1.2 (section 1/15): a candidate's evaluation is explicitly three
separate questions, never blended into one opaque score --

  - `design_suitability`: is this fabric+garment+silhouette combination
    intrinsically good, independent of who it's for or what's in stock?
  - `context_suitability`: does it suit *this* consultation (occasion,
    wear-category preference, season)?
  - `material_feasibility`: can it actually be cut from the fabric on hand
    right now?

`recommendation_classification` (BEST_USE/.../AVOID) describes design +
context quality only. `actionability` is the separate, practical "what should
the client do next" signal that folds in material feasibility. See
docs/rule-engine.md's "Three questions, not one."
"""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import Actionability, Classification, SuitabilityTier
from src.domain.models.common import DomainModel
from src.domain.models.consumption import ConsumptionEstimate
from src.domain.models.feasibility import MaterialFeasibility


class SuitabilityAssessment(DomainModel):
    """Answers exactly one of the two "is this a good idea" questions --
    design suitability or context suitability -- never material feasibility
    (see module docstring)."""

    score: float = Field(ge=0.0, le=100.0)
    classification: SuitabilityTier
    components: dict[str, float] = Field(
        default_factory=dict, description="only components that were genuinely computable given the inputs given"
    )
    omitted_components: dict[str, str] = Field(
        default_factory=dict,
        description="components that could not be genuinely computed given the inputs (e.g. no occasion given), "
        "mapped to why -- never silently filled with a placeholder score standing in for a real evaluation "
        "(section 10: no numeric score is ever shown as if evaluated when it was only a fallback)",
    )
    component_trace: dict[str, list[str]] = Field(
        default_factory=dict,
        description="for each computed component, the rule ids / evidence that produced its score -- "
        "development-time traceability (section 11), not necessarily a permanent public contract",
    )


class ConfidenceBreakdown(DomainModel):
    """Confidence is not one number -- design/context fit can be well-evidenced
    even when the yardage estimate is a shaky fallback, and vice versa
    (section 12)."""

    design_suitability: float = Field(ge=0.0, le=1.0)
    context_suitability: float = Field(ge=0.0, le=1.0)
    consumption: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)


class GarmentRef(DomainModel):
    id: str
    name: str


class SilhouetteRef(DomainModel):
    id: str
    name: str


class FabricRef(DomainModel):
    id: str
    name: str


class SilhouetteCandidate(DomainModel):
    """One ranked (garment, silhouette) pairing for a given fabric -- the
    answer shape for Question A ("I have this fabric, what should I make?")."""

    rank: int
    garment: GarmentRef
    silhouette: SilhouetteRef
    recommendation_classification: Classification
    design_suitability: SuitabilityAssessment
    context_suitability: SuitabilityAssessment
    material_feasibility: MaterialFeasibility
    actionability: Actionability
    consumption: ConsumptionEstimate
    required_fabric_properties: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    source_rules: list[str] = Field(default_factory=list)


class SilhouetteRecommendationResult(DomainModel):
    """Answer shape for Question A: 'I have this fabric, what should I make?'"""

    fabric_id: str
    fabric_name: str
    wear_category_lean: str | None = None
    candidates: list[SilhouetteCandidate] = Field(default_factory=list)
    avoid_examples: list[SilhouetteCandidate] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class FabricCandidate(DomainModel):
    """One ranked fabric choice for a given silhouette -- the answer shape
    for Question B ("I want this silhouette, what fabric should I use?")."""

    rank: int
    fabric: FabricRef
    recommendation_classification: Classification
    design_suitability: SuitabilityAssessment
    context_suitability: SuitabilityAssessment
    material_feasibility: MaterialFeasibility
    actionability: Actionability
    consumption: ConsumptionEstimate
    construction_implications: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown
    source_rules: list[str] = Field(default_factory=list)


class FabricRecommendationResult(DomainModel):
    """Answer shape for Question B: 'I want this silhouette, what fabric
    should I use?'"""

    garment_id: str
    garment_name: str
    silhouette_id: str
    silhouette_name: str
    candidates: list[FabricCandidate] = Field(default_factory=list)
    avoid_examples: list[FabricCandidate] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
