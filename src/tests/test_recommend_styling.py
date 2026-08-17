from __future__ import annotations

import pytest

from src.domain.models.context import RecommendationContext
from src.tools.recommend_styling import recommend_styling


def test_matches_product_brief_example_embroidered_organza_a_line_suit():
    """Section 9's worked example: sheer fabric -> three-quarter sleeves,
    V-neck (sheer rule), moderate flare, restrained embellishment since the
    fabric is already densely worked, lightweight dupatta."""
    spec = recommend_styling("suit", "a_line", "organza", context=RecommendationContext(occasion="engagement"))
    assert spec.sleeve == "three_quarter"  # sheer fabric rule
    assert spec.neckline == "v_neck"  # sheer fabric rule
    assert spec.flare == "moderate"  # a_line's default flare level
    assert spec.dupatta is not None
    assert spec.lining is not None  # organza's typical_components includes lining


def test_dense_surface_fabric_gets_restrained_decoration():
    spec = recommend_styling(
        "suit",
        "anarkali",
        "banarasi",
        context=RecommendationContext(occasion="wedding_guest"),
    )
    assert spec.decoration_intensity == "restrained"
    assert spec.reasoning


def test_heavy_fabric_gets_lightweight_contrast_dupatta():
    spec = recommend_styling("suit", "anarkali", "banarasi", context=RecommendationContext())
    assert spec.dupatta is not None
    assert "lightweight" in spec.dupatta.lower()


def test_no_dupatta_for_garment_without_dupatta_component():
    spec = recommend_styling("gown", "fitted", "satin", context=RecommendationContext())
    assert spec.dupatta is None


def test_unknown_garment_raises():
    with pytest.raises(ValueError, match="Unknown garment"):
        recommend_styling("not_a_real_garment", "a_line", "silk")


def test_unknown_silhouette_raises():
    with pytest.raises(ValueError, match="Unknown silhouette"):
        recommend_styling("suit", "not_a_real_silhouette", "silk")
