"""Visual validation: Phase 4, sections 15-19. Deterministic comparison
between a compact `GeneratedImageObservation` (section 16 -- "what is
visibly present," produced by `GeneratedImageValidator`) and the
`VisualizationSpecification` that was actually requested. This module never
asks "is this a good design" -- only "does what's visible match what was
asked for," exactly like Phase 3's evidence-vs-declaration comparisons."""
from __future__ import annotations

from src.domain.models.visualization import (
    GeneratedImageObservation,
    MaterialFabricSummary,
    ValidationVerdict,
    VisualizationSpecification,
    VisualValidationCheck,
)

_TEXT_MATCH_CONFIDENCE = 0.6
_STRUCTURED_MATCH_CONFIDENCE = 0.85

# Coarse color-family buckets -- free-text color comparison ("deep wine" vs
# "pink") is otherwise unreliable string matching; section 19's own example
# is exactly this kind of family-level mismatch, not a precise-hex compare.
_COLOR_FAMILIES: dict[str, str] = {
    "wine": "red",
    "maroon": "red",
    "crimson": "red",
    "red": "red",
    "burgundy": "red",
    "rose": "pink",
    "pink": "pink",
    "blush": "pink",
    "magenta": "pink",
    "blue": "blue",
    "navy": "blue",
    "teal": "blue",
    "green": "green",
    "olive": "green",
    "emerald": "green",
    "yellow": "yellow",
    "gold": "yellow",
    "mustard": "yellow",
    "orange": "orange",
    "rust": "orange",
    "purple": "purple",
    "lavender": "purple",
    "violet": "purple",
    "black": "neutral",
    "white": "neutral",
    "ivory": "neutral",
    "beige": "neutral",
    "grey": "neutral",
    "gray": "neutral",
    "brown": "neutral",
    "tan": "neutral",
}

_SURFACE_DENSITY_ORDER = ["none", "sparse", "moderate", "dense"]


def _color_family(name: str | None) -> str | None:
    if not name:
        return None
    lowered = name.lower()
    for keyword, family in _COLOR_FAMILIES.items():
        if keyword in lowered:
            return family
    return None


def _text_contains_either_way(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    a, b = a.lower().replace("_", " "), b.lower().replace("_", " ")
    return a in b or b in a


def _check(
    category: str, name: str, verdict: ValidationVerdict, confidence: float, detail: str
) -> VisualValidationCheck:
    return VisualValidationCheck(
        category=category, name=name, verdict=verdict, confidence=confidence, detail=detail
    )


def _silhouette_check(
    observation: GeneratedImageObservation, spec: VisualizationSpecification
) -> VisualValidationCheck:
    match = _text_contains_either_way(observation.garment_subject, spec.garment.silhouette_name) or (
        _text_contains_either_way(observation.garment_subject, spec.garment.category_name)
    )
    if match is None:
        return _check("design", "silhouette_match", ValidationVerdict.UNKNOWN, 0.0, "no garment_subject observed")
    verdict = ValidationVerdict.PASS if match else ValidationVerdict.FAIL
    return _check(
        "design",
        "silhouette_match",
        verdict,
        _TEXT_MATCH_CONFIDENCE,
        f"observed subject {observation.garment_subject!r} vs expected "
        f"{spec.garment.silhouette_name!r}/{spec.garment.category_name!r}",
    )


def _neckline_check(
    observation: GeneratedImageObservation, spec: VisualizationSpecification
) -> VisualValidationCheck:
    match = _text_contains_either_way(observation.neckline, str(spec.neckline.type))
    if match is None:
        return _check("design", "neckline_match", ValidationVerdict.UNKNOWN, 0.0, "no neckline observed")
    verdict = ValidationVerdict.PASS if match else ValidationVerdict.FAIL
    return _check(
        "design", "neckline_match", verdict, _TEXT_MATCH_CONFIDENCE,
        f"observed {observation.neckline!r} vs expected {spec.neckline.type!r}",
    )


def _sleeve_check(
    observation: GeneratedImageObservation, spec: VisualizationSpecification
) -> VisualValidationCheck:
    match = _text_contains_either_way(observation.sleeve_length, str(spec.sleeves.length))
    if match is None:
        return _check("design", "sleeve_match", ValidationVerdict.UNKNOWN, 0.0, "no sleeve_length observed")
    verdict = ValidationVerdict.PASS if match else ValidationVerdict.FAIL
    return _check(
        "design", "sleeve_match", verdict, _TEXT_MATCH_CONFIDENCE,
        f"observed {observation.sleeve_length!r} vs expected {spec.sleeves.length!r}",
    )


def _dupatta_check(
    observation: GeneratedImageObservation, spec: VisualizationSpecification
) -> VisualValidationCheck:
    expected_present = spec.dupatta.included if spec.dupatta is not None else False
    if observation.dupatta_present is None:
        return _check("design", "dupatta_match", ValidationVerdict.UNKNOWN, 0.0, "dupatta presence not observed")
    verdict = (
        ValidationVerdict.PASS if observation.dupatta_present == expected_present else ValidationVerdict.FAIL
    )
    return _check(
        "design", "dupatta_match", verdict, _STRUCTURED_MATCH_CONFIDENCE,
        f"observed dupatta_present={observation.dupatta_present} vs expected {expected_present}",
    )


def _color_check(
    observation: GeneratedImageObservation, fabric: MaterialFabricSummary | None
) -> VisualValidationCheck:
    expected_family = _color_family(fabric.dominant_color if fabric else None)
    observed_family = _color_family(observation.dominant_color)
    if expected_family is None or observed_family is None:
        return _check(
            "fabric", "color_match", ValidationVerdict.UNKNOWN, 0.0,
            f"observed={observation.dominant_color!r} expected={(fabric.dominant_color if fabric else None)!r}",
        )
    verdict = ValidationVerdict.PASS if expected_family == observed_family else ValidationVerdict.FAIL
    return _check(
        "fabric", "color_match", verdict, _TEXT_MATCH_CONFIDENCE,
        f"observed family={observed_family!r} vs expected family={expected_family!r}",
    )


def _surface_density_check(
    observation: GeneratedImageObservation, fabric: MaterialFabricSummary | None
) -> VisualValidationCheck:
    expected = fabric.surface_density if fabric else None
    observed = observation.surface_density
    if not expected or not observed or observed not in _SURFACE_DENSITY_ORDER:
        return _check(
            "fabric", "surface_density_match", ValidationVerdict.UNKNOWN, 0.0,
            f"observed={observed!r} expected={expected!r}",
        )
    gap = abs(_SURFACE_DENSITY_ORDER.index(str(expected)) - _SURFACE_DENSITY_ORDER.index(observed))
    if gap == 0:
        verdict = ValidationVerdict.PASS
    elif gap == 1:
        verdict = ValidationVerdict.PARTIAL
    else:
        verdict = ValidationVerdict.FAIL
    return _check(
        "fabric", "surface_density_match", verdict, _STRUCTURED_MATCH_CONFIDENCE,
        f"observed={observed!r} vs expected={expected!r}",
    )


def _border_check(
    observation: GeneratedImageObservation, fabric: MaterialFabricSummary | None, spec: VisualizationSpecification
) -> VisualValidationCheck:
    if not spec.preservation_requirements.preserve_border:
        return _check(
            "fabric", "border_presence_match", ValidationVerdict.UNKNOWN, 0.0, "border not used by this design"
        )
    expected = fabric.border_present if fabric else None
    if expected is None or observation.border_present is None:
        return _check(
            "fabric", "border_presence_match", ValidationVerdict.UNKNOWN, 0.0,
            f"observed={observation.border_present!r} expected={expected!r}",
        )
    verdict = ValidationVerdict.PASS if observation.border_present == expected else ValidationVerdict.FAIL
    return _check(
        "fabric", "border_presence_match", verdict, _STRUCTURED_MATCH_CONFIDENCE,
        f"observed={observation.border_present!r} vs expected={expected!r}",
    )


def _transparency_check(
    observation: GeneratedImageObservation, fabric: MaterialFabricSummary | None
) -> VisualValidationCheck:
    expected = str(fabric.transparency) if fabric and fabric.transparency else None
    if not expected or not observation.transparency:
        return _check(
            "fabric", "transparency_match", ValidationVerdict.UNKNOWN, 0.0,
            f"observed={observation.transparency!r} expected={expected!r}",
        )
    verdict = ValidationVerdict.PASS if observation.transparency == expected else ValidationVerdict.FAIL
    return _check(
        "fabric", "transparency_match", verdict, _STRUCTURED_MATCH_CONFIDENCE,
        f"observed={observation.transparency!r} vs expected={expected!r}",
    )


def _overall_verdict(checks: list[VisualValidationCheck]) -> ValidationVerdict:
    known = [c for c in checks if c.verdict != ValidationVerdict.UNKNOWN]
    if not known:
        return ValidationVerdict.UNKNOWN
    fails = sum(1 for c in known if c.verdict == ValidationVerdict.FAIL)
    if fails == 0:
        return ValidationVerdict.PASS
    if fails == 1 and fails < len(known):
        return ValidationVerdict.PARTIAL
    return ValidationVerdict.FAIL


def compare_observation_to_specification(
    observation: GeneratedImageObservation,
    spec: VisualizationSpecification,
) -> tuple[ValidationVerdict, list[VisualValidationCheck]]:
    """Section 15: structured invariants, never an LLM asked "is this
    correct" (section 16). `fabric` checks compare against the hero
    material's `MaterialFabricSummary`; a design with no photographed hero
    fabric (shouldn't happen in practice) degrades those checks to UNKNOWN
    rather than guessing."""
    hero = next((m.fabric_summary for m in spec.materials if m.use_hero_fabric and m.fabric_summary), None)

    checks = [
        _silhouette_check(observation, spec),
        _neckline_check(observation, spec),
        _sleeve_check(observation, spec),
        _dupatta_check(observation, spec),
        _color_check(observation, hero),
        _surface_density_check(observation, hero),
        _border_check(observation, hero, spec),
        _transparency_check(observation, hero),
    ]
    return _overall_verdict(checks), checks
