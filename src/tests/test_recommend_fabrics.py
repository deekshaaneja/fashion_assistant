from __future__ import annotations

import pytest

from src.domain.models.context import RecommendationContext
from src.tools.recommend_fabrics import recommend_fabrics


def test_returns_ranked_decisive_fabric_candidates():
    result = recommend_fabrics("a_line", garment_id="suit", context=RecommendationContext(top_n=5))
    assert len(result.candidates) == 5
    # Ranking is classification-tier-first (section 4) -- the invariant is
    # "tier order is non-increasing," not "any single score is non-increasing."
    tier_order = ["BEST_USE", "GOOD_ALTERNATIVE", "POSSIBLE_NOT_IDEAL", "AVOID"]
    tiers = [tier_order.index(c.recommendation_classification) for c in result.candidates]
    assert tiers == sorted(tiers)


def test_unknown_silhouette_raises():
    with pytest.raises(ValueError, match="Unknown silhouette"):
        recommend_fabrics("not_a_real_silhouette")


def test_unknown_garment_raises():
    with pytest.raises(ValueError, match="Unknown garment"):
        recommend_fabrics("a_line", garment_id="not_a_real_garment")


def test_garment_not_applicable_to_silhouette_raises():
    with pytest.raises(ValueError, match="does not apply"):
        recommend_fabrics("anarkali", garment_id="gown")


def test_auto_resolves_garment_when_silhouette_has_single_applicable_garment():
    result = recommend_fabrics("anarkali")  # anarkali only applies to "suit"
    assert result.garment_id == "suit"
    assert not result.assumptions  # unambiguous, no assumption needed


def test_states_assumption_when_garment_is_ambiguous_and_omitted():
    # "a_line" applies to suit, kurta_set, gown, cocktail_dress, evening_dress, lehenga --
    # ("flared" was ambiguous like this before the Phase 1.1 ontology fix restricted it
    # to lehenga only, so it's no longer a useful example of the ambiguous-garment case.)
    result = recommend_fabrics("a_line")
    assert result.garment_id == "suit"
    assert any("assumed" in a.lower() for a in result.assumptions)


def test_organza_and_similar_structured_fabrics_rank_well_for_a_line():
    """Matches golden Case 7: multiple suitable fabrics for A-line, reasoned
    on drape/structure."""
    result = recommend_fabrics("a_line", garment_id="suit", context=RecommendationContext(top_n=10))
    best_use_ids = {c.fabric.id for c in result.candidates if c.recommendation_classification == "BEST_USE"}
    assert len(best_use_ids) >= 3
    assert "organza" in best_use_ids
