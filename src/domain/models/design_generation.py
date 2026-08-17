"""Design generation orchestration models: the translation of Phase 1 facts
+ ClientBrief into hard constraints, plus the request/response envelope for
`generate_design_directions`. Phase 2, section 2's pipeline diagram --
DesignConstraints is the "DESIGN CONSTRAINTS" stage, built once per
(fabric, garment, silhouette, brief) and handed to every later stage so
Phase 1 facts are computed exactly once, never duplicated per candidate.
"""
from __future__ import annotations

from pydantic import Field

from src.domain.models.client_brief import ClientBrief
from src.domain.models.common import DomainModel
from src.domain.models.consumption import ConsumptionEstimate
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric import Fabric


class DesignConstraints(DomainModel):
    """Deterministic facts a candidate MUST respect -- derived from Phase 1's
    own evaluation of the fabric against the chosen (garment, silhouette),
    never re-derived or second-guessed inside generation (section 33: reuse
    Phase 1, don't duplicate it)."""

    fabric_id: str
    garment_id: str
    silhouette_id: str
    effective_flare_level: str
    flare_construction: str
    requires_lining: bool
    max_embellishment_intensity: str  # "none" | "minimal" | "moderate" | "heavy" -- a ceiling, not a mandate
    consumption: ConsumptionEstimate
    hard_avoid: list[str] = Field(
        default_factory=list, description="construction choices this fabric structurally cannot support"
    )
    notes: list[str] = Field(default_factory=list)


class RejectedCandidate(DomainModel):
    title: str
    reasons: list[str]


class ValidationReport(DomainModel):
    candidates_generated: int
    candidates_accepted: int
    candidates_rejected: list[RejectedCandidate] = Field(default_factory=list)
    diversity_regenerations: int = Field(
        default=0, description="how many times a too-similar candidate was discarded in favor of another"
    )


class CandidateGenerationMetadata(DomainModel):
    """Per-candidate generation debug info (multi-direction fix, section 11)
    -- one entry per independently-generated design direction. `latency_ms`
    is that candidate's own call time (attempts summed); the provider-level
    `GenerationMetadata.timing_ms['generation.provider_ms']` is the
    aggregate WALL-CLOCK time across all candidates run concurrently, which
    is why the two numbers are not expected to add up."""

    provider: str
    model: str | None = None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1
    divergence_objective: str | None = None
    succeeded: bool
    error: str | None = None
    error_code: str | None = None


class GenerationMetadata(DomainModel):
    provider: str  # "template" | "mock" | "openai_compatible" | "template (fallback)"
    model: str | None = None
    thinking_enabled: bool | None = Field(
        default=None, description="whether DESIGN_GENERATION_THINKING was on for this call -- live provider only"
    )
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = Field(
        default=None, description="tokens spent on the model's internal reasoning, if the provider reports it"
    )
    attempts: int = 1
    fallback_to_template: bool = Field(
        default=False,
        description="true if a live provider failed and generation fell back to the template provider",
    )
    provider_error: str | None = Field(
        default=None,
        description="why the live provider's output wasn't used (timeout, no valid candidates, etc.) -- "
        "set only when fallback_to_template is true",
    )
    provider_error_code: str | None = Field(
        default=None,
        description="MODEL_PROVIDER_TIMEOUT | MODEL_OUTPUT_INVALID | MODEL_PROVIDER_ERROR -- set only "
        "when fallback_to_template is true",
    )
    timing_ms: dict[str, float] = Field(
        default_factory=dict,
        description="wall-clock timing per pipeline stage in milliseconds, for debugging -- never includes "
        "secrets or raw model output",
    )
    candidates: list[CandidateGenerationMetadata] = Field(
        default_factory=list,
        description="one entry per independently-generated design direction -- live provider only",
    )
    constraints: DesignConstraints


class DesignDirectionsResult(DomainModel):
    designs: list[DesignProposal] = Field(default_factory=list)
    validation: ValidationReport
    generation_metadata: GenerationMetadata


class DesignGenerationRequest(DomainModel):
    """What a `DesignGenerationProvider` receives -- structured inputs only,
    never a giant free-text prompt built ad hoc per call site (section 2).
    `fabric` is the fully-resolved, declared-properties-merged profile (not
    just a catalog id) so a provider never has to re-resolve or re-merge it."""

    fabric: Fabric
    fashion_context: RecommendationContext
    client_brief: ClientBrief
    constraints: DesignConstraints
    garment_id: str
    garment_name: str
    silhouette_id: str
    silhouette_name: str
    count: int = 3
