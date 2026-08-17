from __future__ import annotations

import re

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.fashion_engine.design.colorways import generate_design_colorways
from src.rules.repository import get_fabric_repository

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_colorways_have_valid_hex_and_main_garment_color():
    fabric = get_fabric_repository().resolve("georgette").profile
    colorways = generate_design_colorways(
        fabric, "Test Design", "gathered", ClientBrief(), RecommendationContext(occasion="wedding_guest"), count=3
    )
    assert len(colorways) == 3
    for cw in colorways:
        assert "main_garment" in cw.colors
        for color in cw.colors.values():
            assert _HEX_RE.match(color.hex)


def test_dense_surface_fabric_restricts_to_calm_strategies():
    fabric = get_fabric_repository().resolve("banarasi").profile
    colorways = generate_design_colorways(fabric, "Test", "gathered", ClientBrief(), count=3)
    calm = {"tonal", "monochromatic", "analogous"}
    assert all(cw.harmony_strategy in calm for cw in colorways)


def test_no_embellishment_preference_excludes_metallic_strategy():
    fabric = get_fabric_repository().resolve("georgette").profile
    brief = ClientBrief(embellishment_preference="none")
    colorways = generate_design_colorways(fabric, "Test", "gathered", brief, count=10)
    assert all(cw.harmony_strategy != "metallic_plus_base" for cw in colorways)
