from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.domain.models.recommendation import SuitabilityAssessment
from src.fashion_engine.scoring.engine import (
    CONTEXT_SUITABILITY_WEIGHTS,
    DESIGN_SUITABILITY_WEIGHTS,
    actionability_rank,
    classify_recommendation,
    classify_score,
    classify_suitability,
    tier_rank,
)


def test_design_and_context_suitability_weights_each_sum_to_one():
    assert abs(sum(DESIGN_SUITABILITY_WEIGHTS.values()) - 1.0) < 1e-9
    assert abs(sum(CONTEXT_SUITABILITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_classify_score_thresholds():
    assert classify_score(90) == "BEST_USE"
    assert classify_score(75) == "BEST_USE"
    assert classify_score(60) == "GOOD_ALTERNATIVE"
    assert classify_score(40) == "POSSIBLE_NOT_IDEAL"
    assert classify_score(10) == "AVOID"


def test_classify_score_is_decisive_never_a_hedge():
    for score in (0, 34.9, 35, 54.9, 55, 74.9, 75, 100):
        result = classify_score(score)
        assert result in ("AVOID", "POSSIBLE_NOT_IDEAL", "GOOD_ALTERNATIVE", "BEST_USE")


def test_classify_suitability_thresholds():
    assert classify_suitability(90) == "EXCELLENT"
    assert classify_suitability(75) == "STRONG"
    assert classify_suitability(55) == "MODERATE"
    assert classify_suitability(35) == "WEAK"
    assert classify_suitability(10) == "POOR"


def test_tier_rank_orders_best_use_highest():
    assert (
        tier_rank("AVOID")
        < tier_rank("POSSIBLE_NOT_IDEAL")
        < tier_rank("GOOD_ALTERNATIVE")
        < tier_rank("BEST_USE")
    )


def test_actionability_rank_orders_ready_to_make_highest():
    assert (
        actionability_rank("NOT_RECOMMENDED")
        < actionability_rank("REQUIRES_MISSING_INFORMATION")
        < actionability_rank("REQUIRES_ADDITIONAL_FABRIC")
        < actionability_rank("REQUIRES_DESIGN_MODIFICATION")
        < actionability_rank("READY_TO_MAKE")
    )


def _suitability(score, components):
    return SuitabilityAssessment(score=score, classification=classify_suitability(score), components=components)


def test_classify_recommendation_downgrades_best_use_on_weak_occasion_fit():
    # A strong blended score alone must not be enough for BEST_USE if a
    # specific component (here occasion_fit) is weak (section 5).
    design = _suitability(90.0, {"fabric_compatibility": 90.0, "construction_practicality": 85.0})
    context = _suitability(75.0, {"occasion_fit": 62.5, "wear_category_fit": 92.0})
    assert classify_score(0.6 * design.score + 0.4 * context.score) == "BEST_USE"
    assert classify_recommendation(design, context, curated_avoid_anchor_fired=False) == "GOOD_ALTERNATIVE"


def test_classify_recommendation_keeps_best_use_when_all_gates_pass():
    design = _suitability(90.0, {"fabric_compatibility": 90.0, "construction_practicality": 85.0})
    context = _suitability(90.0, {"occasion_fit": 90.0, "wear_category_fit": 92.0})
    assert classify_recommendation(design, context, curated_avoid_anchor_fired=False) == "BEST_USE"


def test_classify_recommendation_forces_avoid_on_curated_avoid_anchor():
    # Section 5: "AVOID: critical incompatibility or explicit curated avoid
    # rule" -- a curated avoid anchor is decisive regardless of how strong
    # every other component looks.
    design = _suitability(90.0, {"fabric_compatibility": 90.0, "construction_practicality": 90.0})
    context = _suitability(90.0, {"occasion_fit": 90.0, "wear_category_fit": 92.0})
    assert classify_recommendation(design, context, curated_avoid_anchor_fired=True) == "AVOID"


def test_classify_recommendation_forces_avoid_on_critical_fabric_incompatibility():
    design = _suitability(50.0, {"fabric_compatibility": 20.0, "construction_practicality": 85.0})
    context = _suitability(90.0, {"occasion_fit": 90.0})
    assert classify_recommendation(design, context, curated_avoid_anchor_fired=False) == "AVOID"


def test_classify_recommendation_ignores_gates_for_omitted_components():
    # No occasion/wear-category given at all -> occasion_fit and
    # wear_category_fit are omitted, not defaulted to a failing score --
    # they must not gate anything.
    design = _suitability(90.0, {"fabric_compatibility": 90.0, "construction_practicality": 90.0})
    context = _suitability(70.0, {})
    assert classify_recommendation(design, context, curated_avoid_anchor_fired=False) in ("BEST_USE", "GOOD_ALTERNATIVE")


def test_combine_same_subject_lines_handles_possessive_phrasing():
    from src.fashion_engine.scoring.engine import _combine_same_subject_lines

    lines = [
        "Organza is a curated strong pairing for a-line.",
        "Organza carries structured lines cleanly, matching this silhouette's own architecture.",
        "Organza's character suits engagement in this silhouette without needing embellishment to carry it.",
    ]
    combined = _combine_same_subject_lines(lines, "Organza")
    assert len(combined) == 1
    # Must read as "...and its character suits...", never the ungrammatical
    # "...and 's character suits..." left behind by naively stripping the
    # subject off a possessive ("Organza's" -> "'s").
    assert "and its character suits" in combined[0]
    assert " 's " not in combined[0]


def test_evaluate_candidate_separates_design_context_and_feasibility():
    from src.fashion_engine.scoring.engine import evaluate_candidate
    from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

    fabric = get_fabric_repository().resolve("silk").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    evaluation = evaluate_candidate(fabric, garment, silhouette, RecommendationContext())

    assert set(evaluation.design_suitability.components.keys()) == set(DESIGN_SUITABILITY_WEIGHTS.keys())
    assert 0 <= evaluation.design_suitability.score <= 100
    assert 0 <= evaluation.context_suitability.score <= 100
    assert evaluation.material_feasibility.status == "UNKNOWN"  # no available_metres given
    assert evaluation.actionability == "REQUIRES_MISSING_INFORMATION"


def test_available_metres_changes_feasibility_not_design_suitability():
    """Section 17: changing available metres must not change intrinsic
    design suitability -- only material feasibility/actionability (and,
    downstream, ranking position)."""
    from src.fashion_engine.scoring.engine import evaluate_candidate
    from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

    fabric = get_fabric_repository().resolve("organza").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    context = RecommendationContext(occasion="reception", size="M")

    plenty = evaluate_candidate(fabric, garment, silhouette, context.model_copy(update={"available_metres": 50.0}))
    short = evaluate_candidate(fabric, garment, silhouette, context.model_copy(update={"available_metres": 0.5}))

    assert plenty.design_suitability.score == short.design_suitability.score
    assert plenty.design_suitability.components == short.design_suitability.components
    assert plenty.context_suitability.score == short.context_suitability.score
    assert plenty.recommendation_classification == short.recommendation_classification
    assert plenty.material_feasibility.status == "FEASIBLE"
    assert short.material_feasibility.status == "INSUFFICIENT"
    assert plenty.actionability == "READY_TO_MAKE"
    assert short.actionability == "REQUIRES_ADDITIONAL_FABRIC"


def test_every_computed_component_has_a_trace():
    """Section 11/17: every non-null numeric score has a rule/evidence
    trace."""
    from src.fashion_engine.scoring.engine import evaluate_candidate
    from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

    fabric = get_fabric_repository().resolve("silk").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    context = RecommendationContext(occasion="reception", season="winter", wear_category_preference="indian")
    evaluation = evaluate_candidate(fabric, garment, silhouette, context)

    for name in evaluation.design_suitability.components:
        assert evaluation.design_suitability.component_trace.get(name), f"missing trace for {name}"
    for name in evaluation.context_suitability.components:
        assert evaluation.context_suitability.component_trace.get(name), f"missing trace for {name}"


def test_omitted_context_components_are_not_silently_scored():
    """Section 10: a component that can't genuinely be computed is omitted,
    never filled with a placeholder score standing in for a real
    evaluation."""
    from src.fashion_engine.scoring.engine import evaluate_candidate
    from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

    fabric = get_fabric_repository().resolve("silk").profile
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("a_line")
    evaluation = evaluate_candidate(fabric, garment, silhouette, RecommendationContext())

    assert "occasion_fit" not in evaluation.context_suitability.components
    assert "occasion_fit" in evaluation.context_suitability.omitted_components
    assert "formality_fit" not in evaluation.context_suitability.components
    assert "wear_category_fit" not in evaluation.context_suitability.components
    assert "season_fit" not in evaluation.context_suitability.components
