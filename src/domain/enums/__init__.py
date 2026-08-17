"""Controlled vocabularies for the fashion intelligence kernel.

These are the small, stable, closed classification axes. Open catalogs
(specific fabrics, garments, silhouettes, embellishment techniques) live as
seed data in `data/seed/*.yaml`, not as enum members here -- see
docs/domain-model.md for the rationale.
"""
from __future__ import annotations

from enum import Enum


class WearCategory(str, Enum):
    INDIAN = "indian"
    WESTERN = "western"
    FUSION = "fusion"


class Drape(str, Enum):
    CRISP = "crisp"
    STRUCTURED = "structured"
    FLUID = "fluid"
    SOFT = "soft"
    STIFF = "stiff"
    FLUID_TO_STRUCTURED = "fluid_to_structured"


class Stiffness(str, Enum):
    SOFT = "soft"
    MEDIUM = "medium"
    STIFF = "stiff"


class Transparency(str, Enum):
    OPAQUE = "opaque"
    SEMI_SHEER = "semi_sheer"
    SHEER = "sheer"


class Sheen(str, Enum):
    MATTE = "matte"
    SUBTLE_SHEEN = "subtle_sheen"
    HIGH_SHEEN = "high_sheen"
    METALLIC = "metallic"


class Stretch(str, Enum):
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class WeightClass(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class StructureLevel(str, Enum):
    FLUID = "fluid"
    SEMI_STRUCTURED = "semi_structured"
    STRUCTURED = "structured"


class EmbellishmentTolerance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SurfaceDensity(str, Enum):
    """How much existing surface work (motifs/embroidery/sequins/weave
    pattern) the fabric already carries, before any new embellishment."""

    NONE = "none"
    SPARSE = "sparse"
    MODERATE = "moderate"
    DENSE = "dense"


class Season(str, Enum):
    SUMMER = "summer"
    MONSOON = "monsoon"
    WINTER = "winter"
    ALL_SEASON = "all_season"


class FlareLevel(str, Enum):
    MINIMAL = "minimal"
    MODERATE = "moderate"
    HIGH = "high"
    DRAMATIC = "dramatic"


class Classification(str, Enum):
    """Decisive tiering used for every ranked candidate (silhouette or
    fabric) -- never a hedge across multiple tiers. Phase 1.2: this describes
    the quality of the *design recommendation* (design suitability + context
    suitability), never whether the client happens to have enough fabric on
    hand right now -- see `material_feasibility`/`actionability` for that."""

    BEST_USE = "BEST_USE"
    GOOD_ALTERNATIVE = "GOOD_ALTERNATIVE"
    POSSIBLE_NOT_IDEAL = "POSSIBLE_NOT_IDEAL"
    AVOID = "AVOID"


class SuitabilityTier(str, Enum):
    """Human-readable tier for a `SuitabilityAssessment` score (design
    suitability or context suitability) -- a five-point scale, deliberately
    distinct from `Classification`'s four-point scale so the two concepts are
    never visually confusable in output."""

    EXCELLENT = "EXCELLENT"
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    POOR = "POOR"


class MaterialFeasibilityStatus(str, Enum):
    """Can this specific design actually be cut from the fabric currently on
    hand? Phase 1.2, section 1C -- deliberately a *different* question from
    `Classification` (is this a good design at all). `UNKNOWN` covers both
    "no available quantity was given" and "no curated consumption rule
    exists to estimate required yardage" -- in neither case can feasibility
    be honestly claimed one way or the other."""

    FEASIBLE = "FEASIBLE"
    MARGINAL = "MARGINAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class Actionability(str, Enum):
    """What the client should actually do next, derived from classification +
    material feasibility together (Phase 1.2, section 3) -- distinct from
    both, since "great design, but you're short a metre" and "poor design"
    call for entirely different next steps even though neither is
    READY_TO_MAKE."""

    READY_TO_MAKE = "READY_TO_MAKE"
    REQUIRES_ADDITIONAL_FABRIC = "REQUIRES_ADDITIONAL_FABRIC"
    REQUIRES_DESIGN_MODIFICATION = "REQUIRES_DESIGN_MODIFICATION"
    REQUIRES_MISSING_INFORMATION = "REQUIRES_MISSING_INFORMATION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class ConsumptionStatus(str, Enum):
    """Phase 1.2, section 6: a fabricated generic range is less honest than
    an explicit unknown. `NO_CURATED_RULE` replaces the old fallback band."""

    ESTIMATED = "ESTIMATED"
    NO_CURATED_RULE = "NO_CURATED_RULE"


class FlareConstruction(str, Enum):
    """Phase 1.2, section 9: flare is not one undifferentiated "amount" --
    how the volume is actually built changes which fabrics suit it.
    CONTROLLED volume (panel/godet-built, held by the cut) can genuinely
    favor a crisp/stiff fabric's own body (architectural lines); GATHERED
    volume (fullness gathered from a seam/yoke) needs some drape to move
    rather than stand stiffly; DRAMATIC is maximum-volume circular/godet
    flare, where a crisp/stiff/heavy fabric's bulk becomes a real problem."""

    CONTROLLED = "controlled"
    GATHERED = "gathered"
    DRAMATIC = "dramatic"


class Occasion(str, Enum):
    WEDDING_GUEST = "wedding_guest"
    ENGAGEMENT = "engagement"
    RECEPTION = "reception"
    FESTIVE = "festive"
    COCKTAIL = "cocktail"
    DAYTIME = "daytime"
    EVENING = "evening"


class StandardSize(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XXL = "XXL"


class NecklineType(str, Enum):
    ROUND = "round"
    BOAT = "boat"
    SWEETHEART = "sweetheart"
    HALTER = "halter"
    OFF_SHOULDER = "off_shoulder"
    COLLARED = "collared"
    V_NECK = "v_neck"
    HIGH_NECK = "high_neck"
    # Phase 2 additions (section 10) -- deliberately no body-shape framing,
    # purely construction/garment-architecture vocabulary.
    JEWEL = "jewel"
    DEEP_V = "deep_v"
    SQUARE = "square"
    SCOOP = "scoop"
    KEYHOLE = "keyhole"
    ASYMMETRIC = "asymmetric"


class SleeveLength(str, Enum):
    SLEEVELESS = "sleeveless"
    CAP = "cap"
    SHORT = "short"
    ELBOW = "elbow"
    THREE_QUARTER = "three_quarter"
    FULL = "full"
    BELL = "bell"
    BISHOP = "bishop"


class SleeveStyle(str, Enum):
    """A modifier on `SleeveLength` (Phase 2, section 11) -- e.g. "3/4
    length, fitted style, sheer" rather than trying to cram every
    combination into one flat enum."""

    STRAIGHT = "straight"
    FITTED = "fitted"
    CAPE = "cape"
    STATEMENT = "statement"


class DupattaColorStrategy(str, Enum):
    """Phase 2, section 16."""

    TONAL = "tonal"
    LIGHTER_TONAL = "lighter_tonal"
    DARKER_TONAL = "darker_tonal"
    CONTRAST = "contrast"
    COMPLEMENTARY = "complementary"
    NEUTRAL = "neutral"
    METALLIC = "metallic"
    OMBRE = "ombre"


class DecorationLevel(str, Enum):
    """Phase 2, section 13 -- the engine must be able to genuinely recommend
    no additional decoration at all, not just a low amount of it."""

    NO_ADDITIONAL_DECORATION = "NO_ADDITIONAL_DECORATION"
    MINIMAL = "MINIMAL"
    MODERATE = "MODERATE"
    STATEMENT = "STATEMENT"


class EmbellishmentType(str, Enum):
    ZARI = "zari"
    ZARDOZI = "zardozi"
    AARI = "aari"
    THREADWORK = "threadwork"
    MIRROR_WORK = "mirror_work"
    SEQUINS = "sequins"
    CUTDANA = "cutdana"
    BEADS = "beads"
    PEARLS = "pearls"
    GOTA_PATTI = "gota_patti"
    APPLIQUE = "applique"
    LACE = "lace"
    EMBROIDERY = "embroidery"
    PIPING = "piping"
    BUTTONS = "buttons"
    TASSELS = "tassels"
    LATKANS = "latkans"
    NONE = "none"


class ColorHarmonyType(str, Enum):
    TONAL = "tonal"
    MONOCHROMATIC = "monochromatic"
    ANALOGOUS = "analogous"
    COMPLEMENTARY = "complementary"
    SPLIT_COMPLEMENTARY = "split_complementary"
    NEUTRAL_PLUS_ACCENT = "neutral_plus_accent"
    METALLIC_PLUS_BASE = "metallic_plus_base"
