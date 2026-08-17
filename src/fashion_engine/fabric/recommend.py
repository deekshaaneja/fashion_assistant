"""recommend_fabrics: Question B -- "I want this silhouette, what fabric
should I use?" The mirror image of recommend_silhouettes -- same evaluation
engine, same deterministic ranking policy, fabric varies instead of
silhouette. See recommend_silhouettes.py for the full ranking-policy
docstring (section 4)."""
from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.garment import Garment, Silhouette
from src.domain.models.recommendation import FabricCandidate, FabricRecommendationResult, FabricRef
from src.fashion_engine.scoring.engine import actionability_rank, evaluate_candidate, tier_rank
from src.rules.repository import get_fabric_repository

_MAX_AVOID_EXAMPLES = 2


def _construction_implications_for(evaluation, fabric_name: str) -> list[str]:
    implications = [r for r in evaluation.risks if fabric_name in r]
    return implications


def _ranking_key(candidate: FabricCandidate) -> tuple:
    return (
        tier_rank(candidate.recommendation_classification),
        candidate.design_suitability.score,
        candidate.context_suitability.score,
        actionability_rank(candidate.actionability),
        candidate.confidence.overall,
    )


def recommend_fabrics(
    garment: Garment, silhouette: Silhouette, context: RecommendationContext | None = None
) -> FabricRecommendationResult:
    context = context or RecommendationContext()
    fabric_repo = get_fabric_repository()

    all_candidates: list[FabricCandidate] = []

    for fabric in fabric_repo.all():
        if fabric.id == "unknown_fabric":
            continue

        evaluation = evaluate_candidate(fabric, garment, silhouette, context)

        all_candidates.append(
            FabricCandidate(
                rank=0,
                fabric=FabricRef(id=fabric.id, name=fabric.name),
                recommendation_classification=evaluation.recommendation_classification,
                design_suitability=evaluation.design_suitability,
                context_suitability=evaluation.context_suitability,
                material_feasibility=evaluation.material_feasibility,
                actionability=evaluation.actionability,
                consumption=evaluation.consumption,
                construction_implications=_construction_implications_for(evaluation, fabric.name),
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

    return FabricRecommendationResult(
        garment_id=garment.id,
        garment_name=garment.name,
        silhouette_id=silhouette.id,
        silhouette_name=silhouette.name,
        candidates=top,
        avoid_examples=avoid_examples,
        assumptions=[],
    )
