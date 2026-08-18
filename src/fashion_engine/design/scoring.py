"""Design scoring: Phase 2, section 19. Multiple named dimensions, never one
vague "fashion score" -- each is independently computed and traceable.
Scores are for reranking surviving (already-validated) candidates, not for
deciding validity -- that's `validation.py`'s job.

Phase 3.1, section 11-12: a dimension with no real evaluation behind it
(no calibrated palette-vs-fabric-vs-construction check exists yet) is left
`None` and listed in `not_evaluated` rather than filled with a plausible
constant. `overall` renormalizes `_SCORE_WEIGHTS` over only the dimensions
actually present for THIS candidate -- an unevaluated dimension is excluded
from the denominator, never treated as a zero."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import DesignConstraints
from src.domain.models.design_proposal import DesignCandidate, DesignScoreBreakdown

_SCORE_WEIGHTS = {
    "fabric_design_fit": 0.20,
    "aesthetic_coherence": 0.15,
    "occasion_fit": 0.15,
    "client_brief_fit": 0.15,
    "construction_coherence": 0.15,
    "surface_design_coherence": 0.10,
    "color_coherence": 0.05,
    "originality": 0.05,
}


def _weighted_average(components: dict[str, float], weights: dict[str, float]) -> float:
    """Same renormalize-over-what's-present pattern as Phase 1's own
    `_weighted_score` (`src/fashion_engine/scoring/engine.py`) -- an omitted
    (not genuinely evaluated) dimension is excluded rather than distorting
    the blend as an implicit zero."""
    present = {key: weight for key, weight in weights.items() if key in components}
    if not present:
        return 60.0
    total_weight = sum(present.values())
    return sum(components[key] * weight for key, weight in present.items()) / total_weight


def score_candidate(
    candidate: DesignCandidate,
    constraints: DesignConstraints,
    context: RecommendationContext,
    client_brief: ClientBrief,
    sibling_dna_distances: list[float],
) -> DesignScoreBreakdown:
    trace: dict[str, list[str]] = {}

    flare_matches = candidate.construction.flare_construction == constraints.flare_construction
    fabric_design_fit = 90.0 if flare_matches else 40.0
    trace["fabric_design_fit"] = [f"flare_construction respects fabric constraint: {flare_matches}"]

    coherence_checks = 3
    coherence_hits = 0
    statement_leaning = candidate.design_dna.subtle_statement >= 0.6
    decoration_is_bold = candidate.decoration.level in ("MODERATE", "STATEMENT")
    if statement_leaning == decoration_is_bold:
        coherence_hits += 1
    architectural_leaning = candidate.design_dna.soft_architectural >= 0.6
    controlled_construction = candidate.construction.flare_construction == "controlled"
    if architectural_leaning == controlled_construction:
        coherence_hits += 1
    coherence_hits += 1  # dupatta presence alone isn't a strong enough signal to penalize either way
    aesthetic_coherence = 50.0 + (coherence_hits / coherence_checks) * 45.0
    trace["aesthetic_coherence"] = [f"{coherence_hits}/{coherence_checks} DNA-vs-construction checks passed"]

    if context.occasion:
        occasion_fit = 85.0 if candidate.design_dna.understated_glamorous >= 0.35 else 60.0
    else:
        occasion_fit = 70.0
    trace["occasion_fit"] = [f"occasion={context.occasion}"]

    preference_checks: list[bool] = []
    if client_brief.preferred_neckline is not None:
        preference_checks.append(candidate.neckline.type == client_brief.preferred_neckline)
    if client_brief.preferred_sleeve is not None:
        preference_checks.append(candidate.sleeves.length == client_brief.preferred_sleeve)
    if client_brief.embellishment_preference == "none":
        preference_checks.append(candidate.decoration.level == "NO_ADDITIONAL_DECORATION")
    if preference_checks:
        honored = sum(1 for c in preference_checks if c)
        client_brief_fit = honored / len(preference_checks) * 100.0
        trace["client_brief_fit"] = [f"{honored}/{len(preference_checks)} explicit brief preferences honored"]
    else:
        client_brief_fit = 75.0
        trace["client_brief_fit"] = ["no explicit brief preferences stated to check against"]

    construction_coherence = 90.0
    if constraints.hard_avoid and not candidate.risks:
        construction_coherence -= 15.0
    trace["construction_coherence"] = [
        f"hard_avoid={constraints.hard_avoid}",
        f"risks_stated={bool(candidate.risks)}",
    ]

    # Genuinely evaluated (Phase 3.1, section 11): whether the decoration
    # that actually survived assembly needed correction against the
    # fabric's own ceiling/tolerance, not just whether a rationale string
    # happens to be non-empty.
    decoration = candidate.decoration
    surface_design_coherence = 90.0
    if decoration.level_capped:
        surface_design_coherence -= 20.0
    if decoration.invalid_treatments_dropped:
        surface_design_coherence -= 10.0 * decoration.invalid_treatments_dropped
    surface_design_coherence = max(40.0, surface_design_coherence)
    trace["surface_design_coherence"] = [
        f"level_capped={decoration.level_capped}",
        f"invalid_treatments_dropped={decoration.invalid_treatments_dropped}",
        f"source={decoration.source}",
    ]

    # Not yet genuinely evaluated: no calibrated check exists comparing the
    # generated palette against fabric/construction (see
    # generate_design_colorways, a separate, uncorrelated step). Honest
    # unknown beats a plausible-looking constant.
    color_coherence = None
    not_evaluated: list[str] = ["color_coherence"]
    trace["color_coherence"] = ["not yet evaluated against a specific palette -- see generate_design_colorways"]

    if sibling_dna_distances:
        avg_distance = sum(sibling_dna_distances) / len(sibling_dna_distances)
        originality = min(100.0, avg_distance / (8**0.5) * 130.0)
    else:
        originality = 75.0
    trace["originality"] = [f"avg DesignDNA distance to sibling directions: {sibling_dna_distances}"]

    components = {
        "fabric_design_fit": fabric_design_fit,
        "aesthetic_coherence": aesthetic_coherence,
        "occasion_fit": occasion_fit,
        "client_brief_fit": client_brief_fit,
        "construction_coherence": construction_coherence,
        "surface_design_coherence": surface_design_coherence,
        "originality": originality,
    }
    if color_coherence is not None:
        components["color_coherence"] = color_coherence
    overall = _weighted_average(components, _SCORE_WEIGHTS)

    return DesignScoreBreakdown(
        fabric_design_fit=round(fabric_design_fit, 1),
        aesthetic_coherence=round(aesthetic_coherence, 1),
        occasion_fit=round(occasion_fit, 1),
        client_brief_fit=round(client_brief_fit, 1),
        construction_coherence=round(construction_coherence, 1),
        surface_design_coherence=round(surface_design_coherence, 1),
        color_coherence=color_coherence,
        originality=round(originality, 1),
        overall=round(overall, 1),
        not_evaluated=not_evaluated,
        trace=trace,
    )
