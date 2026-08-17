from __future__ import annotations

from src.domain.models.context import RecommendationContext
from src.tools.generate_colorways import generate_colorways


def test_generate_colorways_is_deterministic():
    ctx = RecommendationContext(occasion="festive")
    first = generate_colorways("georgette", context=ctx)
    second = generate_colorways("georgette", context=ctx)
    assert first.model_dump() == second.model_dump()


def test_dense_surface_fabric_gets_tonal_harmony():
    from src.domain.models.fabric import FabricProperties
    from src.fashion_engine.colors.generate import generate_colorways as engine_generate_colorways
    from src.fashion_engine.fabric.analyze import merge_fabric_properties
    from src.rules.repository import get_fabric_repository

    fabric = get_fabric_repository().resolve("banarasi").profile
    fabric = fabric.model_copy(
        update={"properties": merge_fabric_properties(fabric.properties, FabricProperties(surface_density="dense"))}
    )
    colorway = engine_generate_colorways(fabric, context=RecommendationContext(occasion="wedding_guest"))
    assert colorway.harmony_type == "tonal"


def test_bold_occasion_adds_metallic_accent():
    colorway = generate_colorways("georgette", context=RecommendationContext(occasion="wedding_guest"))
    assert len(colorway.metallic_accents) >= 1


def test_all_colors_are_valid_hex():
    colorway = generate_colorways("silk", context=RecommendationContext(occasion="reception"))
    all_colors = (
        colorway.main_colors + colorway.supporting_colors + colorway.metallic_accents + colorway.embroidery_colors
    )
    for color in all_colors:
        assert color.hex.startswith("#")
        assert len(color.hex) == 7


def test_low_tolerance_fabric_with_embroidery_colors_is_good_alternative_not_best_use():
    from src.domain.models.fabric import FabricProperties
    from src.fashion_engine.colors.generate import generate_colorways as engine_generate_colorways
    from src.fashion_engine.fabric.analyze import merge_fabric_properties
    from src.rules.repository import get_fabric_repository

    fabric = get_fabric_repository().resolve("chiffon").profile
    fabric = fabric.model_copy(
        update={"properties": merge_fabric_properties(fabric.properties, FabricProperties(embellishment_tolerance="low"))}
    )
    colorway = engine_generate_colorways(fabric, context=RecommendationContext(occasion="daytime"))
    if colorway.embroidery_colors:
        assert colorway.classification == "GOOD_ALTERNATIVE"
