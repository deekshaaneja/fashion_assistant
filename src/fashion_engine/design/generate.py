"""generate_design_directions: Phase 2, section 7. The core orchestrator --
FabricProfile + FashionContext + ClientBrief + (selected or Phase-1-resolved)
Silhouette -> DESIGN CONSTRAINTS -> CANDIDATE GENERATION -> DOMAIN VALIDATION
-> DIVERSITY CHECK -> RERANKING -> DesignProposal[] (section 2's pipeline).

Ranking only ever happens after every surviving candidate has a complete
evaluation (constraints, validation, palette, score) -- never mid-pipeline.

Every stage is wall-clock timed (`generation.*_ms` in the returned
`generation_metadata.timing_ms`) and logged at INFO -- never the raw model
output or credentials, just durations -- so a slow/hanging path is always
diagnosable (see the "generate-design-directions times out" bug fix).
"""
from __future__ import annotations

import logging
import time

from src.domain.models.client_brief import ClientBrief
from src.domain.models.common import Confidence
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import (
    DesignDirectionsResult,
    DesignGenerationRequest,
    GenerationMetadata,
    RejectedCandidate,
    ValidationReport,
)
from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric import Fabric
from src.fashion_engine.design.colorways import generate_design_colorways
from src.fashion_engine.design.constraints import build_design_constraints
from src.fashion_engine.design.diversity import filter_diverse
from src.fashion_engine.design.scoring import score_candidate
from src.fashion_engine.design.validation import validate_candidate
from src.fashion_engine.silhouettes.recommend import recommend_silhouettes
from src.providers.design_generation import (
    MockDesignGenerationProvider,
    OpenAICompatibleDesignGenerationProvider,
    TemplateDesignGenerationProvider,
    get_design_generation_provider,
)
from src.providers.settings import get_settings
from src.rules.repository import get_garment_repository, get_silhouette_repository

logger = logging.getLogger(__name__)


def _ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 1)


def _provider_label(provider) -> str:
    if isinstance(provider, MockDesignGenerationProvider):
        return "mock"
    if isinstance(provider, TemplateDesignGenerationProvider):
        return "template"
    return "openai_compatible"


def _resolve_garment_silhouette(
    fabric: Fabric,
    context: RecommendationContext,
    selected_garment_id: str | None,
    selected_silhouette_id: str | None,
):
    garment_repo = get_garment_repository()
    silhouette_repo = get_silhouette_repository()

    if selected_silhouette_id is not None:
        silhouette = silhouette_repo.get(selected_silhouette_id)
        if silhouette is None:
            raise ValueError(f"Unknown silhouette id '{selected_silhouette_id}'.")
        garment_id = selected_garment_id or (
            silhouette.applicable_garment_ids[0] if silhouette.applicable_garment_ids else None
        )
        if garment_id is None or garment_id not in silhouette.applicable_garment_ids:
            raise ValueError(f"Silhouette '{selected_silhouette_id}' does not apply to garment '{garment_id}'.")
        garment = garment_repo.get(garment_id)
        if garment is None:
            raise ValueError(f"Unknown garment id '{garment_id}'.")
        return garment, silhouette

    recommendation = recommend_silhouettes(fabric, context)
    if not recommendation.candidates:
        raise ValueError("Phase 1 found no applicable silhouettes for this fabric to design against.")
    top = recommendation.candidates[0]
    garment = garment_repo.get(top.garment.id)
    silhouette = silhouette_repo.get(top.silhouette.id)
    return garment, silhouette


def generate_design_directions(
    fabric: Fabric,
    fashion_context: RecommendationContext | None = None,
    client_brief: ClientBrief | None = None,
    selected_garment_id: str | None = None,
    selected_silhouette_id: str | None = None,
    count: int = 3,
) -> DesignDirectionsResult:
    total_start = time.monotonic()
    timing_ms: dict[str, float] = {}
    context = fashion_context or RecommendationContext()
    brief = client_brief or ClientBrief()

    t0 = time.monotonic()
    garment, silhouette = _resolve_garment_silhouette(fabric, context, selected_garment_id, selected_silhouette_id)
    constraints = build_design_constraints(fabric, garment, silhouette, context, brief)
    timing_ms["generation.resolve_ms"] = _ms(t0)

    request = DesignGenerationRequest(
        fabric=fabric,
        fashion_context=context,
        client_brief=brief,
        constraints=constraints,
        garment_id=garment.id,
        garment_name=garment.name,
        silhouette_id=silhouette.id,
        silhouette_name=silhouette.name,
        count=count,
    )

    provider = get_design_generation_provider()
    provider_name = _provider_label(provider)
    is_live = isinstance(provider, OpenAICompatibleDesignGenerationProvider)
    model_name = get_settings().llm_model if is_live else None
    thinking_enabled = get_settings().design_generation_thinking if is_live else None
    t0 = time.monotonic()
    raw_candidates = provider.generate(request)
    timing_ms["generation.provider_ms"] = _ms(t0)
    for key in ("parse_ms", "call_ms"):
        value = getattr(provider, "last_timing_ms", {}).get(key)
        if value is not None:
            timing_ms[f"generation.{key}"] = value
    attempts = getattr(provider, "last_attempts", 0) or 1
    usage = getattr(provider, "last_usage", None) or {}
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    reasoning_tokens = usage.get("reasoning_tokens")
    candidate_metadata = getattr(provider, "last_candidate_metadata", None) or []

    fallback_to_template = False
    provider_error = None
    provider_error_code = None
    if not raw_candidates and provider_name not in ("template", "mock"):
        provider_error = getattr(provider, "last_error", None) or "provider returned no usable candidates"
        provider_error_code = getattr(provider, "last_error_code", None) or "MODEL_PROVIDER_ERROR"
        t0 = time.monotonic()
        raw_candidates = TemplateDesignGenerationProvider().generate(request)
        timing_ms["generation.fallback_provider_ms"] = _ms(t0)
        fallback_to_template = True
        provider_name = "template (fallback)"
    elif (
        provider_name not in ("template", "mock")
        and len(raw_candidates) < count
        and getattr(provider, "last_error_code", None) == "MODEL_PARTIAL_FAILURE"
    ):
        # Multi-direction fix, section 7: a partial live failure (e.g. 2 of 3
        # succeeded) is returned AS-IS -- never silently backfilled with
        # template designs, which would contaminate a live design-quality
        # benchmark. Explicitly visible via provider_error(_code); backfill
        # is opt-in only (DESIGN_GENERATION_TEMPLATE_BACKFILL=true).
        provider_error = getattr(provider, "last_error", None)
        provider_error_code = getattr(provider, "last_error_code", None)
        if get_settings().design_generation_template_backfill:
            missing = count - len(raw_candidates)
            t0 = time.monotonic()
            backfill_request = request.model_copy(update={"count": missing})
            raw_candidates = raw_candidates + TemplateDesignGenerationProvider().generate(backfill_request)
            timing_ms["generation.fallback_provider_ms"] = _ms(t0)
            fallback_to_template = True
            provider_name = f"{provider_name} (partial fallback)"

    t0 = time.monotonic()
    rejected: list[RejectedCandidate] = []
    valid_candidates = []
    for candidate in raw_candidates:
        issues = validate_candidate(candidate, request)
        if issues:
            rejected.append(RejectedCandidate(title=candidate.title, reasons=issues))
        else:
            valid_candidates.append(candidate)
    timing_ms["generation.validation_ms"] = _ms(t0)

    t0 = time.monotonic()
    if count <= 1:
        # Section: "for count=1, do not run diversity comparison, do not
        # regenerate for diversity, generate exactly one candidate."
        selected = valid_candidates[:1]
        diversity_rejections = 0
    else:
        selected, diversity_rejections = filter_diverse(valid_candidates, count=count)
    timing_ms["generation.diversity_ms"] = _ms(t0)

    t0 = time.monotonic()
    designs: list[DesignProposal] = []
    for candidate in selected:
        siblings = [c for c in selected if c is not candidate]
        sibling_distances = [candidate.design_dna.distance(sibling.design_dna) for sibling in siblings]
        scores = score_candidate(candidate, constraints, context, brief, sibling_distances)

        palettes = generate_design_colorways(
            fabric, candidate.title, candidate.construction.flare_construction, brief, context, count=1
        )
        palette = palettes[0] if palettes else None

        provider_confidence = 0.9 if not fallback_to_template else 0.75
        confidence_score = (constraints.consumption.confidence.score + provider_confidence) / 2
        designs.append(
            DesignProposal(
                **candidate.model_dump(),
                id=f"{candidate.title.lower().replace(' ', '-')}",
                rank=0,
                palette=palette,
                scores=scores,
                confidence=Confidence.of(confidence_score),
            )
        )

    designs.sort(key=lambda d: d.scores.overall, reverse=True)
    for i, design in enumerate(designs, start=1):
        design.rank = i
    timing_ms["generation.scoring_ms"] = _ms(t0)

    timing_ms["generation.total_ms"] = _ms(total_start)
    logger.info(
        "generate_design_directions provider=%s fallback=%s count=%d accepted=%d timing_ms=%s",
        provider_name,
        fallback_to_template,
        count,
        len(designs),
        timing_ms,
    )

    validation_report = ValidationReport(
        candidates_generated=len(raw_candidates),
        candidates_accepted=len(designs),
        candidates_rejected=rejected,
        diversity_regenerations=diversity_rejections,
    )
    metadata = GenerationMetadata(
        provider=provider_name,
        model=model_name,
        thinking_enabled=thinking_enabled,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        attempts=attempts,
        fallback_to_template=fallback_to_template,
        provider_error=provider_error,
        provider_error_code=provider_error_code,
        timing_ms=timing_ms,
        candidates=candidate_metadata,
        constraints=constraints,
    )

    return DesignDirectionsResult(designs=designs, validation=validation_report, generation_metadata=metadata)
