"""recommend_styling: structured construction-detail recommendation for an
already-chosen (garment, silhouette, fabric) combination. Deterministic
rule lookups over the fabric's own properties -- no LLM involved."""
from __future__ import annotations

from src.domain.enums import NecklineType, SleeveLength
from src.domain.models.context import RecommendationContext
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment, Silhouette
from src.domain.models.styling import StylingSpec

_LENGTH_BY_GARMENT: dict[str, str] = {
    "suit": "calf_length",
    "kurta_set": "knee_length",
    "gown": "floor_length",
    "evening_dress": "floor_length",
    "cocktail_dress": "knee_length",
    "lehenga": "floor_length",
    "sharara_set": "calf_length",
    "gharara_set": "calf_length",
}

_BOTTOM_STYLE_BY_GARMENT_SILHOUETTE: dict[tuple[str, str], str] = {
    ("suit", "straight"): "straight_trousers",
    ("suit", "relaxed"): "straight_trousers",
    ("suit", "a_line"): "straight_trousers",
    ("suit", "anarkali"): "churidar",
    ("suit", "kalidar"): "churidar",
    ("suit", "panelled"): "churidar",
    ("sharara_set", "straight"): "sharara_pants",
    ("gharara_set", "straight"): "gharara_pants",
    ("lehenga", "flared"): "flared_skirt",
    ("lehenga", "panelled"): "panelled_skirt",
    ("lehenga", "fish_cut"): "fish_cut_skirt",
    ("lehenga", "a_line"): "a_line_skirt",
    ("skirt_top", "a_line"): "a_line_skirt",
    ("skirt_top", "flared"): "flared_skirt",
    ("skirt_top", "asymmetric"): "asymmetric_skirt",
    ("corset_skirt", "corset"): "structured_skirt",
    ("corset_skirt", "fitted"): "fitted_skirt",
}


def _neckline(garment: Garment, silhouette: Silhouette, fabric: Fabric) -> NecklineType:
    if silhouette.id == "off_shoulder":
        return NecklineType.OFF_SHOULDER
    if silhouette.id == "corset":
        return NecklineType.SWEETHEART
    if "glamour" in silhouette.aesthetic_tags and garment.wear_category == "western":
        return NecklineType.SWEETHEART
    if garment.wear_category == "indian" and "heritage" in silhouette.aesthetic_tags:
        return NecklineType.BOAT
    if fabric.properties.transparency == "sheer":
        return NecklineType.V_NECK
    return NecklineType.ROUND


def _sleeve(fabric: Fabric, silhouette: Silhouette, garment: Garment) -> SleeveLength:
    if silhouette.id in ("corset", "off_shoulder"):
        return SleeveLength.SLEEVELESS
    if fabric.properties.transparency == "sheer":
        return SleeveLength.THREE_QUARTER
    if garment.wear_category == "western":
        return SleeveLength.CAP
    return SleeveLength.ELBOW


def _length(garment: Garment, silhouette: Silhouette) -> str:
    if silhouette.id == "anarkali":
        return "floor_length"
    return _LENGTH_BY_GARMENT.get(garment.id, "calf_length")


def _bottom_style(garment: Garment, silhouette: Silhouette) -> str | None:
    if "bottom" not in garment.typical_components and "blouse" not in garment.typical_components:
        return None
    return _BOTTOM_STYLE_BY_GARMENT_SILHOUETTE.get((garment.id, silhouette.id))


def _dupatta(garment: Garment, fabric: Fabric) -> str | None:
    if "dupatta" not in garment.typical_components:
        return None
    if fabric.properties.weight_class == "heavy":
        return (
            f"Lightweight contrast dupatta (a plain sheer fabric, since {fabric.name} itself is too heavy "
            "to drape well as a dupatta)."
        )
    return f"Lightweight {fabric.name.lower()} dupatta in a matching or tonal shade."


def _lining(garment: Garment, fabric: Fabric) -> str | None:
    if "lining" not in garment.typical_components:
        return None
    if fabric.properties.transparency in ("sheer", "semi_sheer"):
        return "Full inner lining required for coverage given the fabric's transparency."
    return "Standard matching lining."


def _decoration_intensity(fabric: Fabric, context: RecommendationContext) -> str:
    """Decoration follows the fabric's own surface density and embellishment
    tolerance, not the occasion in isolation -- a formal occasion can be
    entirely appropriate on a plain fabric through cut, color, and
    accessories rather than added embroidery (section 6 of the Phase 1.1
    brief). Occasion only narrows the range (e.g. keeping daytime restrained);
    it never on its own escalates a low-surface-interest fabric to "heavy"."""
    already_dense = fabric.properties.surface_density == "dense"
    low_tolerance = fabric.properties.embellishment_tolerance == "low"
    if already_dense or low_tolerance:
        return "restrained"

    high_tolerance = fabric.properties.embellishment_tolerance == "high"
    has_surface_interest = fabric.properties.surface_density != "none"

    if context.occasion in ("daytime",) and not high_tolerance:
        return "none"
    if high_tolerance and has_surface_interest:
        return "heavy"
    return "moderate"


def recommend_styling(
    garment: Garment, silhouette: Silhouette, fabric: Fabric, context: RecommendationContext | None = None
) -> StylingSpec:
    context = context or RecommendationContext()
    reasoning: list[str] = []

    decoration_intensity = _decoration_intensity(fabric, context)
    if decoration_intensity == "restrained":
        reasoning.append(
            f"{fabric.name} already carries significant surface interest or tolerates little more -- "
            "keeping embellishment restrained lets the fabric itself lead."
        )

    dupatta = _dupatta(garment, fabric)
    if dupatta:
        reasoning.append("A lighter-weight dupatta keeps the overall silhouette from feeling top-heavy.")

    if fabric.properties.transparency == "sheer":
        finishing = "Clean finished seams with piped edges."
    else:
        finishing = "Clean finished seams."

    return StylingSpec(
        neckline=_neckline(garment, silhouette, fabric),
        sleeve=_sleeve(fabric, silhouette, garment),
        length=_length(garment, silhouette),
        flare=silhouette.default_flare_level,
        waist_placement="empire" if silhouette.id == "empire" else "natural",
        bottom_style=_bottom_style(garment, silhouette),
        dupatta=dupatta,
        lining=_lining(garment, fabric),
        finishing=finishing,
        decoration_intensity=decoration_intensity,
        reasoning=reasoning,
    )
