"""recommend_silhouettes: Question A -- "I have this fabric, what should I
make?" Ranks every (garment, silhouette) pair the fabric could plausibly
become, decisively classified, never a flat unranked list.

Phase 1.2 ranking policy (section 4) -- deterministic, applied only AFTER
every candidate has a full evaluation (design suitability, context
suitability, material feasibility, classification, confidence):

    1. recommendation_classification (BEST_USE first)
    2. design_suitability.score
    3. context_suitability.score
    4. actionability (closer to READY_TO_MAKE ranks higher)
    5. confidence.overall

This is deliberately NOT a single blended score sort -- a technically
excellent but currently fabric-short design can still be shown prominently
(it outranks a design that is simply worse), while a similarly strong and
immediately feasible design can reasonably outrank it once classification,
design, and context are tied. See docs/rule-engine.md.
"""
from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.fabric import Fabric
from src.domain.models.recommendation import (
    GarmentRef,
    SilhouetteCandidate,
    SilhouetteRecommendationResult,
    SilhouetteRef,
)
from src.fashion_engine.scoring.engine import actionability_rank, evaluate_candidate, tier_rank
from src.rules.repository import get_garment_repository, get_silhouette_repository

_MAX_AVOID_EXAMPLES = 2


def _required_fabric_properties_for(silhouette, effective_flare: str) -> list[str]:
    props = [f"structure: {silhouette.structure_affinity}", f"flare: {effective_flare}"]
    if silhouette.aesthetic_tags:
        props.append(f"aesthetic fit: {', '.join(silhouette.aesthetic_tags)}")
    return props


def _ranking_key(candidate: SilhouetteCandidate) -> tuple:
    return (
        tier_rank(candidate.recommendation_classification),
        candidate.design_suitability.score,
        candidate.context_suitability.score,
        actionability_rank(candidate.actionability),
        candidate.confidence.overall,
    )


def recommend_silhouettes(
    fabric: Fabric, context: RecommendationContext | None = None, fabric_confidence: float = 1.0
) -> SilhouetteRecommendationResult:
    context = context or RecommendationContext()
    garment_repo = get_garment_repository()
    silhouette_repo = get_silhouette_repository()

    all_candidates: list[SilhouetteCandidate] = []
    assumptions: list[str] = []

    for silhouette in silhouette_repo.all():
        for garment_id in silhouette.applicable_garment_ids:
            garment = garment_repo.get(garment_id)
            if garment is None:
                continue

            evaluation = evaluate_candidate(
                fabric, garment, silhouette, context, fabric_confidence=fabric_confidence
            )

            all_candidates.append(
                SilhouetteCandidate(
                    rank=0,  # assigned after sorting
                    garment=GarmentRef(id=garment.id, name=garment.name),
                    silhouette=SilhouetteRef(id=silhouette.id, name=silhouette.name),
                    recommendation_classification=evaluation.recommendation_classification,
                    design_suitability=evaluation.design_suitability,
                    context_suitability=evaluation.context_suitability,
                    material_feasibility=evaluation.material_feasibility,
                    actionability=evaluation.actionability,
                    consumption=evaluation.consumption,
                    required_fabric_properties=_required_fabric_properties_for(
                        silhouette, evaluation.effective_flare_level
                    ),
                    reasons=evaluation.reasons,
                    risks=evaluation.risks,
                    assumptions=evaluation.assumptions,
                    confidence=evaluation.confidence,
                    source_rules=evaluation.source_rules,
                )
            )

    all_candidates.sort(key=_ranking_key, reverse=True)

    top = all_candidates[: context.top_n]
    for i, candidate in enumerate(top, start=1):
        candidate.rank = i

    avoid_pool = [c for c in all_candidates if c.recommendation_classification == "AVOID" and c not in top]
    avoid_examples = avoid_pool[-_MAX_AVOID_EXAMPLES:] if avoid_pool else []
    for i, candidate in enumerate(avoid_examples, start=1):
        candidate.rank = i

    if not all_candidates:
        assumptions.append("No silhouettes are seeded as applicable to any garment for this fabric's context.")

    wear_category_lean = None
    if top:
        top_garment = garment_repo.get(top[0].garment.id)
        wear_category_lean = top_garment.wear_category if top_garment else None

    return SilhouetteRecommendationResult(
        fabric_id=fabric.id,
        fabric_name=fabric.name,
        wear_category_lean=wear_category_lean,
        candidates=top,
        avoid_examples=avoid_examples,
        assumptions=assumptions,
    )
