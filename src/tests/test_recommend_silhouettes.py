from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.tools.recommend_silhouettes import recommend_silhouettes


def test_returns_ranked_decisive_candidates():
    result = recommend_silhouettes("silk", context=RecommendationContext(occasion="reception", top_n=5))
    assert len(result.candidates) == 5
    ranks = [c.rank for c in result.candidates]
    assert ranks == sorted(ranks)
    for candidate in result.candidates:
        assert candidate.recommendation_classification in (
            "BEST_USE",
            "GOOD_ALTERNATIVE",
            "POSSIBLE_NOT_IDEAL",
            "AVOID",
        )


def test_top_n_is_respected():
    result = recommend_silhouettes("cotton", context=RecommendationContext(top_n=3))
    assert len(result.candidates) == 3


def test_unresolved_fabric_still_returns_a_result_with_assumption_stated():
    result = recommend_silhouettes("not a real fabric at all")
    assert result.candidates  # still produces a ranked list, doesn't error out
    assert any("did not match" in a for a in result.assumptions)


def test_wear_category_lean_reflects_top_candidate():
    result = recommend_silhouettes("georgette", context=RecommendationContext(occasion="festive", top_n=3))
    assert result.wear_category_lean in ("indian", "western", "fusion")


def test_feasibility_shortfall_does_not_change_classification_but_does_change_actionability():
    """Phase 1.2, sections 1-3: design suitability, context suitability, and
    material feasibility are three separate questions. A-Line Suit is a
    structurally excellent design for engagement -- with only 4m on hand
    against a ~5-5.1m requirement, that must NOT downgrade
    `recommendation_classification` (still BEST_USE), but it does mean
    `material_feasibility` is INSUFFICIENT and `actionability` says to get
    more fabric, not that the design itself is flawed."""
    ctx = RecommendationContext(occasion="engagement", available_metres=4.0, top_n=15)
    result = recommend_silhouettes("korean organza", context=ctx)

    suit_a_line = next(c for c in result.candidates if c.garment.id == "suit" and c.silhouette.id == "a_line")
    kurta_a_line = next(
        (c for c in result.candidates if c.garment.id == "kurta_set" and c.silhouette.id == "a_line"), None
    )

    assert suit_a_line.recommendation_classification == "BEST_USE"
    assert suit_a_line.material_feasibility.status == "INSUFFICIENT"
    assert suit_a_line.actionability == "REQUIRES_ADDITIONAL_FABRIC"
    # A genuinely better design that's merely fabric-short still outranks a
    # worse design (kurta set isn't typically positioned for engagement),
    # even though the kurta candidate has no feasibility problem at all.
    if kurta_a_line is not None:
        assert suit_a_line.rank < kurta_a_line.rank


def test_declared_properties_change_design_suitability_for_the_same_silhouette():
    from src.domain.models.fabric import FabricProperties

    ctx = RecommendationContext(occasion="festive", top_n=15)
    plain = recommend_silhouettes("chiffon", context=ctx)
    declared_dense = recommend_silhouettes(
        "chiffon", declared_properties=FabricProperties(surface_density="dense"), context=ctx
    )

    def _design_score_for(result, silhouette_id):
        return next(c.design_suitability.score for c in result.candidates if c.silhouette.id == silhouette_id)

    common_silhouettes = {c.silhouette.id for c in plain.candidates} & {
        c.silhouette.id for c in declared_dense.candidates
    }
    assert common_silhouettes
    # Declaring the fabric dense doesn't necessarily move every silhouette's
    # rounded score (e.g. one whose aesthetic tags don't interact with
    # surface density at all) -- assert at least one common silhouette
    # moved, not an arbitrary pick from a set whose iteration order isn't
    # stable across interpreter runs.
    assert any(
        _design_score_for(plain, silhouette_id) != _design_score_for(declared_dense, silhouette_id)
        for silhouette_id in common_silhouettes
    )
