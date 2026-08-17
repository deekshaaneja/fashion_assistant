"""Transparent candidate evaluation (section 13 of the product brief).

Phase 1.2 correction pass (see docs/rule-engine.md's "Three questions, not
one"): a candidate's evaluation is explicitly three separate, never-blended
questions --

  - design suitability: is this fabric+garment+silhouette combination
    intrinsically good, independent of who it's for or what's in stock?
  - context suitability: does it suit *this* consultation (occasion,
    wear-category preference, season)?
  - material feasibility: can it actually be cut from the fabric on hand?

`recommendation_classification` (BEST_USE/GOOD_ALTERNATIVE/POSSIBLE_NOT_IDEAL/
AVOID) reflects design + context quality ONLY, gated by configurable minimum
per-component floors (a candidate cannot be BEST_USE on a strong blended
score alone if a specific component is critically weak). Material
feasibility never downgrades that classification -- it instead drives the
separate `actionability` signal and a ranking tiebreak. Every component that
was genuinely computable carries a rule/evidence trace; a component that
couldn't be computed given the inputs is *omitted*, never filled with a
placeholder score standing in for a real evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.enums import (
    Actionability,
    Classification,
    ConsumptionStatus,
    MaterialFeasibilityStatus,
    SuitabilityTier,
)
from src.domain.models.consumption import ConsumptionEstimate
from src.domain.models.context import RecommendationContext
from src.domain.models.fabric import Fabric
from src.domain.models.feasibility import MaterialFeasibility
from src.domain.models.garment import Garment, Silhouette
from src.domain.models.recommendation import ConfidenceBreakdown, SuitabilityAssessment
from src.fashion_engine.consumption.calculate import calculate_consumption
from src.fashion_engine.feasibility.check import check_fabric_feasibility
from src.rules.compatibility import score_fabric_silhouette

_TIER_ORDER = [
    Classification.AVOID,
    Classification.POSSIBLE_NOT_IDEAL,
    Classification.GOOD_ALTERNATIVE,
    Classification.BEST_USE,
]
_TIER_THRESHOLDS: list[tuple[float, Classification]] = [
    (75.0, Classification.BEST_USE),
    (55.0, Classification.GOOD_ALTERNATIVE),
    (35.0, Classification.POSSIBLE_NOT_IDEAL),
]
_SUITABILITY_THRESHOLDS: list[tuple[float, SuitabilityTier]] = [
    (85.0, SuitabilityTier.EXCELLENT),
    (70.0, SuitabilityTier.STRONG),
    (50.0, SuitabilityTier.MODERATE),
    (30.0, SuitabilityTier.WEAK),
]

# Design suitability is occasion/consultation-independent by construction:
# just the fabric-silhouette structural/material relationship and real
# tailoring friction. Context suitability is entirely consultation-dependent.
DESIGN_SUITABILITY_WEIGHTS: dict[str, float] = {
    "fabric_compatibility": 0.65,
    "construction_practicality": 0.35,
}
CONTEXT_SUITABILITY_WEIGHTS: dict[str, float] = {
    "occasion_fit": 0.35,
    "wear_category_fit": 0.20,
    "season_fit": 0.15,
    "formality_fit": 0.30,
}
# How much each dimension contributes to the blended score used ONLY for the
# raw classification threshold step -- material feasibility never appears
# here (section 1/2: classification describes design quality, not stock on
# hand).
RECOMMENDATION_WEIGHTS: dict[str, float] = {"design_suitability": 0.6, "context_suitability": 0.4}

# A candidate cannot reach BEST_USE on a strong blended score alone if any of
# these specific components is weak (section 5: "do not allow arithmetic
# averaging to hide serious incompatibility"). Only components that were
# actually computed are checked -- an omitted component (e.g. no occasion
# given) does not gate anything.
BEST_USE_MIN_COMPONENTS: dict[str, float] = {
    "fabric_compatibility": 65.0,
    "construction_practicality": 55.0,
    "occasion_fit": 65.0,
    "wear_category_fit": 50.0,
}
# A softer second gate: even GOOD_ALTERNATIVE requires no critical dimension
# actively broken.
GOOD_ALTERNATIVE_MIN_COMPONENTS: dict[str, float] = {
    "fabric_compatibility": 35.0,
    "construction_practicality": 35.0,
    "occasion_fit": 35.0,
    "wear_category_fit": 40.0,
}
# A hard floor: no averaging can rescue a candidate from AVOID once fabric
# compatibility is this low, and a curated avoid-anchor is always decisive.
CRITICAL_FABRIC_COMPATIBILITY_FLOOR = 25.0

_OCCASION_FORMALITY: dict[str, int] = {
    "daytime": 1,
    "cocktail": 2,
    "evening": 3,
    "engagement": 3,
    "reception": 3,
    "festive": 3,
    "wedding_guest": 4,
}
_SHEEN_FORMALITY: dict[str, int] = {"matte": 1, "subtle_sheen": 2, "high_sheen": 3, "metallic": 4}
_AESTHETIC_FORMALITY_SHIFT: dict[str, int] = {
    "glamour": 1,
    "heritage": 1,
    "romance": 1,
    "ornamentation": 1,
    "dramatic": 1,
    "minimal": -1,
    "comfortable": -1,
    "daywear": -1,
    "clean": -1,
    "easy_wear": -1,
}

_FLARE_ORDER = ["minimal", "moderate", "high", "dramatic"]
_ACTIONABILITY_RANK: dict[str, int] = {
    Actionability.NOT_RECOMMENDED: 0,
    Actionability.REQUIRES_MISSING_INFORMATION: 1,
    Actionability.REQUIRES_ADDITIONAL_FABRIC: 2,
    Actionability.REQUIRES_DESIGN_MODIFICATION: 3,
    Actionability.READY_TO_MAKE: 4,
}


def classify_score(score: float) -> Classification:
    """Fixed thresholds on a blended score alone -> exactly one tier, never a
    hedge across tiers. This is the raw threshold step before hard-gate
    checks -- see `classify_recommendation`."""
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return Classification.AVOID


def classify_suitability(score: float) -> SuitabilityTier:
    for threshold, tier in _SUITABILITY_THRESHOLDS:
        if score >= threshold:
            return tier
    return SuitabilityTier.POOR


def tier_rank(tier: Classification) -> int:
    """Numeric rank of a classification tier, higher is better (BEST_USE
    highest) -- lets callers sort candidates by tier first and other signals
    only as tiebreakers."""
    return _TIER_ORDER.index(tier)


def actionability_rank(actionability: Actionability) -> int:
    """Numeric rank of an actionability value, higher is closer to
    ready-to-make -- used purely as a ranking tiebreak, never to change a
    classification."""
    return _ACTIONABILITY_RANK[actionability]


def classify_recommendation(
    design: SuitabilityAssessment, context: SuitabilityAssessment, curated_avoid_anchor_fired: bool
) -> Classification:
    """The real entry point: blend design+context into a raw tier, then
    apply hard per-component gates and a critical-incompatibility floor.
    Material feasibility never enters this function (section 2/3) -- an
    excellent, currently-fabric-short design stays classified on its own
    merits; see `_material_feasibility`/`_actionability` for the feasibility
    side of the story."""
    all_components = {**design.components, **context.components}

    if curated_avoid_anchor_fired or all_components.get("fabric_compatibility", 100.0) <= (
        CRITICAL_FABRIC_COMPATIBILITY_FLOOR
    ):
        return Classification.AVOID

    blended = design.score * RECOMMENDATION_WEIGHTS["design_suitability"] + context.score * (
        RECOMMENDATION_WEIGHTS["context_suitability"]
    )
    tier = classify_score(blended)

    if tier == Classification.BEST_USE:
        if any(
            component in all_components and all_components[component] < minimum
            for component, minimum in BEST_USE_MIN_COMPONENTS.items()
        ):
            tier = Classification.GOOD_ALTERNATIVE

    if tier == Classification.GOOD_ALTERNATIVE:
        if any(
            component in all_components and all_components[component] < minimum
            for component, minimum in GOOD_ALTERNATIVE_MIN_COMPONENTS.items()
        ):
            tier = Classification.POSSIBLE_NOT_IDEAL

    return tier


def _weighted_score(components: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted average over only the components actually present, weights
    renormalized to sum to 1 among those -- an omitted component (not enough
    information to compute it) is excluded rather than silently treated as a
    neutral default that would distort the blend."""
    present = {key: weight for key, weight in weights.items() if key in components}
    if not present:
        return 60.0  # nothing given to judge by at all -- documented, rare fallback
    total_weight = sum(present.values())
    return sum(components[key] * weight for key, weight in present.items()) / total_weight


@dataclass(frozen=True)
class CandidateEvaluation:
    recommendation_classification: Classification
    design_suitability: SuitabilityAssessment
    context_suitability: SuitabilityAssessment
    material_feasibility: MaterialFeasibility
    actionability: Actionability
    consumption: ConsumptionEstimate
    confidence: ConfidenceBreakdown
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    source_rules: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    effective_flare_level: str = "moderate"


def _effective_flare_level(fabric: Fabric, silhouette: Silhouette) -> tuple[str, str | None]:
    """The flare level actually being recommended for THIS fabric in THIS
    silhouette. A stiff/heavy fabric can't comfortably deliver GATHERED or
    DRAMATIC volume -- but the same fabric can be an *asset* for CONTROLLED,
    panel-built volume (section 9), so only GATHERED/DRAMATIC constructions
    get toned down. Returns (effective_flare, note_or_None)."""
    natural = silhouette.default_flare_level
    idx = _FLARE_ORDER.index(natural) if natural in _FLARE_ORDER else 1
    fabric_limits_flare = silhouette.flare_construction in ("gathered", "dramatic") and (
        fabric.properties.drape in ("crisp", "stiff") or fabric.properties.weight_class == "heavy"
    )
    if fabric_limits_flare and idx >= 2:  # natural flare is "high" or "dramatic"
        effective = _FLARE_ORDER[idx - 1]
        note = (
            f"{fabric.name}'s body doesn't comfortably support this silhouette's full "
            f"{natural} ({silhouette.flare_construction}) flare -- recommended here at a "
            f"toned-down {effective} flare instead."
        )
        return effective, note
    return natural, None


def _construction_practicality(
    fabric: Fabric, silhouette: Silhouette, effective_flare: str
) -> tuple[float, list[str], list[str]]:
    """Real tailoring friction -- occasion-independent, belongs to design
    suitability. Returns (score, risks, trace)."""
    score = 85.0
    risks: list[str] = []
    trace: list[str] = []

    if fabric.properties.weight_class == "heavy" and silhouette.id in ("fitted", "corset"):
        score -= 15
        risks.append(f"{fabric.name} is heavy for a close-fitted construction -- expect more tailoring work.")
        trace.append("heavy_fabric_vs_fitted_or_corset_construction")
    if fabric.properties.motif_directional and effective_flare in ("high", "dramatic"):
        score -= 10
        risks.append(
            "A directional motif with this much flare means more fabric-matching complexity when cutting."
        )
        trace.append("directional_motif_vs_high_or_dramatic_effective_flare")
    if not fabric.properties.stretch or fabric.properties.stretch == "none":
        if silhouette.id in ("fitted", "corset"):
            score -= 8
            risks.append(
                f"{fabric.name} has no stretch -- a fitted/corset cut needs precise tailoring, not forgiving ease."
            )
            trace.append("no_stretch_vs_fitted_or_corset_construction")
    if not trace:
        trace.append("no_construction_friction_detected")

    return max(30.0, score), risks, trace


def _occasion_fit(garment: Garment, context: RecommendationContext) -> tuple[float | None, list[str], list[str]]:
    """None (omitted) when no occasion was given -- never a neutral
    placeholder standing in for a real judgment."""
    if context.occasion is None:
        return None, [], []
    occasion_label = context.occasion.replace("_", " ")
    if context.occasion in garment.occasions_fit:
        return 90.0, [f"{garment.name} is well positioned for {occasion_label}."], []
    return 35.0, [], [f"{garment.name} is not typically positioned for {occasion_label}."]


def _wear_category_fit(
    garment: Garment, context: RecommendationContext
) -> tuple[float | None, list[str], list[str]]:
    """None (omitted) when no wear-category preference was stated."""
    if context.wear_category_preference is None:
        return None, [], []
    preference = context.wear_category_preference
    if garment.wear_category == preference:
        return 92.0, [f"{garment.name} matches the requested {preference} preference."], []
    if garment.wear_category == "fusion":
        return 68.0, [f"{garment.name} is a fusion piece -- a partial match for the {preference} preference."], []
    mismatch_risk = (
        f"{garment.name}'s {garment.wear_category} register doesn't match the requested {preference} preference."
    )
    return 35.0, [], [mismatch_risk]


def _season_fit(fabric: Fabric, context: RecommendationContext) -> tuple[float | None, list[str]]:
    """None (omitted) when no season was given."""
    if context.season is None:
        return None, []
    supports_season = context.season in fabric.seasonality or "all_season" in fabric.seasonality
    if supports_season:
        return 90.0, []
    return 25.0, [f"{fabric.name} is not well suited to {context.season} wear."]


def _formality_fit(
    fabric: Fabric, silhouette: Silhouette, context: RecommendationContext
) -> tuple[float | None, list[str], list[str]]:
    """Whether the fabric's inherent richness (sheen, existing surface work)
    plus the silhouette's own aesthetic character reads appropriately formal
    for the STATED occasion -- genuinely context-dependent (needs an
    occasion to compare against), unlike design suitability. NOT whether the
    fabric carries enough embellishment for the occasion -- decoration
    intensity is recommend_styling's own, separate, fabric-driven decision
    (section 13); a plain fabric that isn't formal enough on its own is a cue
    to lean on cut/color/accessories, never an instruction to add
    embellishment. None (omitted) when no occasion was given."""
    if context.occasion is None:
        return None, [], []

    occasion_label = context.occasion.replace("_", " ")
    occasion_formality = _OCCASION_FORMALITY.get(context.occasion, 2)
    fabric_formality = _SHEEN_FORMALITY.get(fabric.properties.sheen or "matte", 1)
    if fabric.properties.surface_density == "dense":
        fabric_formality = max(fabric_formality, 3)
    aesthetic_shift = sum(_AESTHETIC_FORMALITY_SHIFT.get(tag, 0) for tag in silhouette.aesthetic_tags)
    combined_formality = min(4, max(1, fabric_formality + aesthetic_shift))

    if combined_formality >= occasion_formality:
        reason = (
            f"{fabric.name}'s character suits {occasion_label} in this silhouette "
            "without needing embellishment to carry it."
        )
        return 88.0, [reason], []

    gap = occasion_formality - combined_formality
    risk = (
        f"{fabric.name} reads fairly understated for {occasion_label} in this silhouette -- "
        "rely on cut, color, and accessories rather than assuming heavier embellishment is required."
    )
    return max(55.0, 80.0 - gap * 10), [], [risk]


def _combine_same_subject_lines(lines: list[str], subject: str) -> list[str]:
    """Rule contributions about the same fabric/subject read as one cohesive
    design rationale rather than a list of separate, repetitive-sounding
    bullets -- combines lines that literally start with `subject` into a
    single sentence, preserving every underlying fact."""
    own = [line for line in lines if line.startswith(subject)]
    other = [line for line in lines if not line.startswith(subject)]
    if len(own) <= 1:
        return lines
    first = own[0].rstrip(".")
    continuations = []
    for line in own[1:]:
        remainder = line[len(subject) :].strip()
        if not remainder:
            continue
        if remainder.startswith("'s "):
            # "Organza's character..." -> "...and its character..." rather
            # than the ungrammatical "...and 's character..." left behind by
            # blindly stripping the subject off a possessive.
            continuations.append("its " + remainder[3:].rstrip("."))
        else:
            continuations.append(remainder[0].lower() + remainder[1:].rstrip("."))
    combined = first + ", and " + ", and ".join(continuations) + "." if continuations else first + "."
    return [combined, *other]


def _material_feasibility(
    fabric: Fabric,
    garment: Garment,
    silhouette: Silhouette,
    context: RecommendationContext,
    consumption: ConsumptionEstimate,
    effective_flare: str,
) -> MaterialFeasibility:
    """UNKNOWN when either no curated consumption rule exists or no
    available quantity was given -- in both cases feasibility cannot be
    honestly claimed either way (section 1C/6)."""
    if consumption.status == ConsumptionStatus.NO_CURATED_RULE:
        return MaterialFeasibility(
            status=MaterialFeasibilityStatus.UNKNOWN,
            available_metres=context.available_metres,
            reasoning=(
                f"No curated consumption rule exists for ({garment.id}, {silhouette.id}) -- required yardage "
                "cannot be honestly estimated, so material feasibility cannot be determined either."
            ),
        )

    if context.available_metres is None:
        return MaterialFeasibility(
            status=MaterialFeasibilityStatus.UNKNOWN,
            required_min_metres=consumption.min_metres,
            required_max_metres=consumption.max_metres,
            reasoning=(
                "No available fabric quantity was given, so feasibility against the estimated "
                f"{consumption.min_metres}-{consumption.max_metres}m requirement cannot be determined."
            ),
        )

    result = check_fabric_feasibility(
        context.available_metres,
        consumption.as_range(),
        garment_name=garment.name,
        silhouette_name=silhouette.name,
        high_flare=effective_flare in ("high", "dramatic"),
        has_directional_motif=bool(fabric.properties.motif_directional),
    )
    return MaterialFeasibility(
        status=result.status,
        available_metres=result.available_metres,
        required_min_metres=result.required_range.min,
        required_max_metres=result.required_range.max,
        shortage_min_metres=result.shortage_range.min if result.shortage_range else None,
        shortage_max_metres=result.shortage_range.max if result.shortage_range else None,
        redesign_options=result.redesign_options,
        reasoning=result.reasoning,
    )


def _actionability(classification: Classification, feasibility: MaterialFeasibility) -> Actionability:
    """What the client should do next -- folds classification (is this even
    a good idea) together with material feasibility (can you make it right
    now), which `recommendation_classification` deliberately never does on
    its own (section 3)."""
    if classification == Classification.AVOID:
        return Actionability.NOT_RECOMMENDED
    if feasibility.status == MaterialFeasibilityStatus.UNKNOWN:
        return Actionability.REQUIRES_MISSING_INFORMATION
    if feasibility.status == MaterialFeasibilityStatus.INSUFFICIENT:
        return Actionability.REQUIRES_ADDITIONAL_FABRIC
    if feasibility.status == MaterialFeasibilityStatus.MARGINAL:
        return Actionability.REQUIRES_DESIGN_MODIFICATION
    return Actionability.READY_TO_MAKE


def _aggregate_confidence(
    fabric_confidence: float, compatibility_rules_fired: bool, context: RecommendationContext, consumption
) -> ConfidenceBreakdown:
    """Confidence is not one number (section 12) -- design/context fit can be
    well-evidenced even when the yardage estimate is a shaky fallback, and
    vice versa. Unknown inputs and fallback rules pull the relevant
    dimension down; a rule matching is one input among several, never a
    stand-in for ~95% confidence."""
    design_confidence = round((fabric_confidence + (0.85 if compatibility_rules_fired else 0.55)) / 2, 2)
    context_confidence = round(
        sum(
            [
                0.85 if context.occasion is not None else 0.5,
                0.75 if context.season is not None else 0.6,
                0.8 if context.wear_category_preference is not None else 0.6,
            ]
        )
        / 3,
        2,
    )
    consumption_confidence = consumption.confidence.score
    overall = round((design_confidence + context_confidence + consumption_confidence) / 3, 2)
    return ConfidenceBreakdown(
        design_suitability=design_confidence,
        context_suitability=context_confidence,
        consumption=consumption_confidence,
        overall=overall,
    )


def evaluate_candidate(
    fabric: Fabric,
    garment: Garment,
    silhouette: Silhouette,
    context: RecommendationContext,
    fabric_confidence: float = 1.0,
) -> CandidateEvaluation:
    effective_flare, flare_note = _effective_flare_level(fabric, silhouette)

    fabric_compat = score_fabric_silhouette(fabric, silhouette)
    construction_score, construction_risks, construction_trace = _construction_practicality(
        fabric, silhouette, effective_flare
    )

    design_components = {
        "fabric_compatibility": round(fabric_compat.score, 1),
        "construction_practicality": round(construction_score, 1),
    }
    design_trace = {
        "fabric_compatibility": list(fabric_compat.source_rules) or ["baseline_no_rules_fired"],
        "construction_practicality": construction_trace,
    }
    design_score = _weighted_score(design_components, DESIGN_SUITABILITY_WEIGHTS)
    design_suitability = SuitabilityAssessment(
        score=round(design_score, 1),
        classification=classify_suitability(design_score),
        components=design_components,
        component_trace=design_trace,
    )

    occasion_score, occasion_reasons, occasion_risks = _occasion_fit(garment, context)
    wear_category_score, wear_category_reasons, wear_category_risks = _wear_category_fit(garment, context)
    season_score, season_risks = _season_fit(fabric, context)
    formality_score, formality_reasons, formality_risks = _formality_fit(fabric, silhouette, context)

    formality_trace = ["fabric sheen/surface_density + silhouette aesthetic_tags vs occasion"]
    context_components: dict[str, float] = {}
    context_trace: dict[str, list[str]] = {}
    omitted_context: dict[str, str] = {}
    for name, score, trace in (
        ("occasion_fit", occasion_score, ["garment.occasions_fit membership check"]),
        ("wear_category_fit", wear_category_score, ["garment.wear_category vs stated preference"]),
        ("season_fit", season_score, ["fabric.seasonality vs stated season"]),
        ("formality_fit", formality_score, formality_trace),
    ):
        if score is None:
            reason_for_omission = "no occasion given" if name in ("occasion_fit", "formality_fit") else (
                "no wear-category preference given" if name == "wear_category_fit" else "no season given"
            )
            omitted_context[name] = reason_for_omission
        else:
            context_components[name] = round(score, 1)
            context_trace[name] = trace

    context_score = _weighted_score(context_components, CONTEXT_SUITABILITY_WEIGHTS)
    context_suitability = SuitabilityAssessment(
        score=round(context_score, 1),
        classification=classify_suitability(context_score),
        components=context_components,
        omitted_components=omitted_context,
        component_trace=context_trace,
    )

    consumption = calculate_consumption(
        garment.id,
        silhouette.id,
        size=context.size,
        fabric_width_cm=context.fabric_width_cm,
        flare_level=effective_flare,
        directional_motif=bool(fabric.properties.motif_directional),
        include_border=bool(fabric.properties.border_available),
    )
    feasibility = _material_feasibility(fabric, garment, silhouette, context, consumption, effective_flare)

    curated_avoid_anchor_fired = "curated_avoid_anchor" in fabric_compat.source_rules
    classification = classify_recommendation(design_suitability, context_suitability, curated_avoid_anchor_fired)
    actionability = _actionability(classification, feasibility)

    reasons = [*fabric_compat.positive_reasons, *occasion_reasons, *wear_category_reasons, *formality_reasons]
    risks = [
        *fabric_compat.risks,
        *occasion_risks,
        *wear_category_risks,
        *season_risks,
        *formality_risks,
        *construction_risks,
    ]
    if feasibility.status in (MaterialFeasibilityStatus.MARGINAL, MaterialFeasibilityStatus.INSUFFICIENT):
        risks.append(feasibility.reasoning)
    reasons = _combine_same_subject_lines(reasons, fabric.name)
    risks = _combine_same_subject_lines(risks, fabric.name)

    assumptions = list(consumption.assumptions)
    if feasibility.status == MaterialFeasibilityStatus.UNKNOWN:
        assumptions.append(feasibility.reasoning)
    if flare_note:
        assumptions.append(flare_note)

    confidence = _aggregate_confidence(fabric_confidence, bool(fabric_compat.source_rules), context, consumption)

    return CandidateEvaluation(
        recommendation_classification=classification,
        design_suitability=design_suitability,
        context_suitability=context_suitability,
        material_feasibility=feasibility,
        actionability=actionability,
        consumption=consumption,
        reasons=reasons,
        risks=risks,
        source_rules=fabric_compat.source_rules,
        confidence=confidence,
        assumptions=assumptions,
        effective_flare_level=effective_flare,
    )
