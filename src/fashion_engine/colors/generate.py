"""generate_colorways: structured colorway engine. No image generation here
(section 12) -- deterministic HSL relationships only."""
from __future__ import annotations

from src.domain.enums import Classification, ColorHarmonyType
from src.domain.models.colorway import ColorSpec, Colorway
from src.domain.models.context import RecommendationContext
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment
from src.fashion_engine.colors.color_math import rotate_hue, shift_lightness
from src.rules.loader import load_seed

_BOLD_OCCASIONS = {"wedding_guest", "reception", "festive"}
_SOFT_OCCASIONS = {"engagement", "daytime"}


def _base_color(context: RecommendationContext) -> ColorSpec:
    palettes = load_seed("occasion_palettes.yaml")
    if context.occasion and context.occasion in palettes["occasion_palettes"]:
        entry = palettes["occasion_palettes"][context.occasion]
    else:
        entry = palettes["default_palette"]
    return ColorSpec(name=entry["name"], hex=entry["hex"], role="main")


def _choose_harmony(context: RecommendationContext, fabric: Fabric) -> ColorHarmonyType:
    if fabric.properties.surface_density == "dense":
        return ColorHarmonyType.TONAL  # already-decorated fabric: keep the palette calm
    if context.occasion in _BOLD_OCCASIONS:
        if fabric.properties.sheen == "metallic":
            return ColorHarmonyType.METALLIC_PLUS_BASE
        return ColorHarmonyType.COMPLEMENTARY
    if context.occasion in _SOFT_OCCASIONS:
        return ColorHarmonyType.ANALOGOUS
    return ColorHarmonyType.NEUTRAL_PLUS_ACCENT


def _metallic_accent() -> ColorSpec:
    palettes = load_seed("occasion_palettes.yaml")
    entry = palettes["metallic_accent"]
    return ColorSpec(name=entry["name"], hex=entry["hex"], role="metallic_accent")


def generate_colorways(
    fabric: Fabric, garment: Garment | None = None, context: RecommendationContext | None = None
) -> Colorway:
    context = context or RecommendationContext()
    base = _base_color(context)
    harmony = _choose_harmony(context, fabric)
    reasoning: list[str] = [f"Base color chosen for the {context.occasion or 'requested'} occasion: {base.name}."]

    supporting_colors: list[ColorSpec] = []
    embroidery_colors: list[ColorSpec] = []
    metallic_accents: list[ColorSpec] = []

    if harmony == ColorHarmonyType.TONAL:
        supporting_colors.append(
            ColorSpec(name=f"{base.name} (tonal)", hex=shift_lightness(base.hex, -0.15), role="supporting")
        )
        reasoning.append(
            f"{fabric.name} already carries dense surface work -- a tonal palette avoids visual competition."
        )
    elif harmony == ColorHarmonyType.MONOCHROMATIC:
        supporting_colors.append(
            ColorSpec(name=f"{base.name} (lighter)", hex=shift_lightness(base.hex, 0.20), role="supporting")
        )
    elif harmony == ColorHarmonyType.ANALOGOUS:
        supporting_colors.append(
            ColorSpec(name=f"{base.name} +30", hex=rotate_hue(base.hex, 30), role="supporting")
        )
        supporting_colors.append(
            ColorSpec(name=f"{base.name} -30", hex=rotate_hue(base.hex, -30), role="supporting")
        )
    elif harmony == ColorHarmonyType.COMPLEMENTARY:
        complement_hex = rotate_hue(base.hex, 180)
        supporting_colors.append(ColorSpec(name=f"{base.name} complement", hex=complement_hex, role="supporting"))
        embroidery_colors.append(
            ColorSpec(
                name=f"{base.name} complement (deep)",
                hex=shift_lightness(complement_hex, -0.2),
                role="embroidery",
            )
        )
    elif harmony == ColorHarmonyType.NEUTRAL_PLUS_ACCENT:
        supporting_colors.append(ColorSpec(name="ivory neutral", hex="#FFFDD0", role="supporting"))
        embroidery_colors.append(ColorSpec(name=f"{base.name} accent", hex=base.hex, role="embroidery"))
    elif harmony == ColorHarmonyType.METALLIC_PLUS_BASE:
        metallic_accents.append(_metallic_accent())

    if context.occasion in _BOLD_OCCASIONS and not metallic_accents:
        metallic_accents.append(_metallic_accent())

    if harmony == ColorHarmonyType.TONAL:
        dupatta_direction = f"{base.name}, tonal to the main color"
    else:
        accent_name = metallic_accents[0].name if metallic_accents else "a supporting accent"
        dupatta_direction = f"{base.name} with a contrast border in {accent_name}"

    classification = Classification.BEST_USE
    if fabric.properties.embellishment_tolerance == "low" and embroidery_colors:
        classification = Classification.GOOD_ALTERNATIVE
        reasoning.append(
            f"{fabric.name} has low embellishment tolerance -- keep any embroidery-color accents minimal."
        )

    return Colorway(
        harmony_type=harmony,
        main_colors=[base],
        supporting_colors=supporting_colors,
        metallic_accents=metallic_accents,
        embroidery_colors=embroidery_colors,
        dupatta_direction=dupatta_direction,
        classification=classification,
        reasoning=reasoning,
    )
