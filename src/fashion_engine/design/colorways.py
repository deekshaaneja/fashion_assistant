"""generate_design_colorways: Phase 2, section 15. Expands Phase 1's
`generate_colorways` (single main+supporting colors) into complete,
per-component coordinated color stories -- reuses the same deterministic HSL
math (`color_math.py`), never invents a color relationship via an LLM."""
from __future__ import annotations

from src.domain.enums import ColorHarmonyType
from src.domain.models.client_brief import ClientBrief
from src.domain.models.colorway import ColorSpec
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import DesignColorway
from src.domain.models.fabric import Fabric
from src.fashion_engine.colors.color_math import rotate_hue, shift_lightness
from src.rules.loader import load_seed

_ALL_STRATEGIES = [
    ColorHarmonyType.TONAL,
    ColorHarmonyType.MONOCHROMATIC,
    ColorHarmonyType.ANALOGOUS,
    ColorHarmonyType.COMPLEMENTARY,
    ColorHarmonyType.SPLIT_COMPLEMENTARY,
    ColorHarmonyType.NEUTRAL_PLUS_ACCENT,
    ColorHarmonyType.METALLIC_PLUS_BASE,
]
_DENSE_SURFACE_STRATEGIES = [ColorHarmonyType.TONAL, ColorHarmonyType.MONOCHROMATIC, ColorHarmonyType.ANALOGOUS]


def _base_color(context: RecommendationContext, client_brief: ClientBrief) -> ColorSpec:
    palettes = load_seed("occasion_palettes.yaml")
    if client_brief.color_preferences:
        wanted = client_brief.color_preferences[0].lower()
        for entry in palettes["occasion_palettes"].values():
            if entry["name"].lower() == wanted:
                return ColorSpec(name=entry["name"], hex=entry["hex"], role="main")
    if context.occasion and context.occasion in palettes["occasion_palettes"]:
        entry = palettes["occasion_palettes"][context.occasion]
    else:
        entry = palettes["default_palette"]
    return ColorSpec(name=entry["name"], hex=entry["hex"], role="main")


def _build_harmony_colors(base: ColorSpec, harmony: ColorHarmonyType) -> dict[str, ColorSpec]:
    colors: dict[str, ColorSpec] = {"main_garment": base}
    if harmony == ColorHarmonyType.TONAL:
        tonal = shift_lightness(base.hex, -0.1)
        light_tonal = shift_lightness(base.hex, 0.15)
        colors["bottom"] = ColorSpec(name=f"{base.name} (tonal)", hex=tonal, role="supporting")
        colors["dupatta"] = ColorSpec(name=f"{base.name} (light tonal)", hex=light_tonal, role="supporting")
    elif harmony == ColorHarmonyType.MONOCHROMATIC:
        lighter = shift_lightness(base.hex, 0.2)
        colors["bottom"] = base
        colors["dupatta"] = ColorSpec(name=f"{base.name} (lighter)", hex=lighter, role="supporting")
    elif harmony == ColorHarmonyType.ANALOGOUS:
        plus_30 = rotate_hue(base.hex, 30)
        minus_30 = rotate_hue(base.hex, -30)
        colors["bottom"] = ColorSpec(name=f"{base.name} +30", hex=plus_30, role="supporting")
        colors["dupatta"] = ColorSpec(name=f"{base.name} -30", hex=minus_30, role="supporting")
    elif harmony == ColorHarmonyType.COMPLEMENTARY:
        comp = rotate_hue(base.hex, 180)
        comp_deep = shift_lightness(comp, -0.2)
        colors["bottom"] = base
        colors["dupatta"] = ColorSpec(name=f"{base.name} complement", hex=comp, role="supporting")
        colors["embroidery"] = ColorSpec(name=f"{base.name} complement (deep)", hex=comp_deep, role="embroidery")
    elif harmony == ColorHarmonyType.SPLIT_COMPLEMENTARY:
        split_1 = rotate_hue(base.hex, 150)
        split_2 = rotate_hue(base.hex, 210)
        colors["bottom"] = base
        colors["dupatta"] = ColorSpec(name=f"{base.name} split-1", hex=split_1, role="supporting")
        colors["embroidery"] = ColorSpec(name=f"{base.name} split-2", hex=split_2, role="embroidery")
    elif harmony == ColorHarmonyType.NEUTRAL_PLUS_ACCENT:
        colors["bottom"] = ColorSpec(name="ivory neutral", hex="#FFFDD0", role="supporting")
        colors["dupatta"] = ColorSpec(name="ivory neutral", hex="#FFFDD0", role="supporting")
        colors["embroidery"] = ColorSpec(name=f"{base.name} accent", hex=base.hex, role="embroidery")
    elif harmony == ColorHarmonyType.METALLIC_PLUS_BASE:
        colors["bottom"] = base
        colors["trim_metallic"] = ColorSpec(name="antique gold", hex="#C9A24B", role="metallic_accent")

    lining_tone = shift_lightness(base.hex, 0.05)
    colors["lining"] = ColorSpec(name=f"{base.name} (lining tone)", hex=lining_tone, role="supporting")
    return colors


def generate_design_colorways(
    fabric: Fabric,
    design_title: str,
    design_flare_construction: str,
    client_brief: ClientBrief,
    context: RecommendationContext | None = None,
    count: int = 3,
) -> list[DesignColorway]:
    context = context or RecommendationContext()
    base = _base_color(context, client_brief)

    is_dense = fabric.properties.surface_density == "dense"
    strategies = list(_DENSE_SURFACE_STRATEGIES) if is_dense else list(_ALL_STRATEGIES)
    if client_brief.embellishment_preference == "none" and ColorHarmonyType.METALLIC_PLUS_BASE in strategies:
        strategies.remove(ColorHarmonyType.METALLIC_PLUS_BASE)

    slug = design_title.lower().replace(" ", "-")
    colorways: list[DesignColorway] = []
    for i, harmony in enumerate(strategies[:count]):
        colors = _build_harmony_colors(base, harmony)
        ombre_direction = None
        if design_flare_construction in ("gathered", "dramatic") and harmony in (
            ColorHarmonyType.TONAL,
            ColorHarmonyType.MONOCHROMATIC,
        ):
            ombre_direction = "vertical, deeper toward the hem"

        rationale = f"{harmony.value.replace('_', ' ').title()} story built from {base.name}."
        if fabric.properties.surface_density == "dense":
            rationale += f" Kept calm/tonal since {fabric.name} already carries its own surface richness."

        colorways.append(
            DesignColorway(
                id=f"{slug}-colorway-{i + 1}",
                harmony_strategy=harmony.value,
                colors=colors,
                ombre_direction=ombre_direction,
                rationale=rationale,
            )
        )
    return colorways
