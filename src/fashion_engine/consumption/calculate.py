"""calculate_consumption: deterministic yardage estimation. Never claims
false precision -- always a min/max range with stated assumptions and a
confidence score, never a single fake-exact number. Every modifier that
fires is surfaced numerically (`modifiers`), not just as prose, and the
result exposes exactly the `ConstructionAssumptions` it was generated FROM.

Phase 1.2, section 6: when no curated rule exists for a (garment, silhouette)
pair, this returns an explicit `NO_CURATED_RULE` status with no metres at
all -- a fabricated generic range is less honest, and less useful, than a
plain "we don't know" (a caller can act on "I need more information," but
not on a range that turns out not to bound the true requirement anyway).
"""
from __future__ import annotations

from src.domain.enums import ConsumptionStatus, FlareLevel, StandardSize
from src.domain.models.common import Confidence
from src.domain.models.consumption import ConstructionAssumptions, ConsumptionEstimate
from src.rules.repository import get_consumption_rule_repository, get_silhouette_repository

_SIZE_ORDER = [s.value for s in StandardSize]
_FLARE_ORDER = [f.value for f in FlareLevel]

# Confidence assigned when there's no curated rule to estimate from at all --
# deliberately low; this is not a real estimate, just a labeled absence.
_NO_CURATED_RULE_CONFIDENCE = 0.15

# Applied when the caller declares a directional motif and the specific rule
# doesn't override its own wastage bump for that.
_DEFAULT_DIRECTIONAL_MOTIF_WASTAGE_PCT = 0.05

# The min/max band narrows as confidence rises -- a well-established seeded
# rule should not carry the same range width as a shakier one. Floor of 3%
# keeps even a very confident rule from claiming a single fake-exact number.
_MIN_BAND_PCT = 0.03
_BAND_SPREAD_PCT = 0.15

# Displayed yardage is rounded to this many decimal places regardless of the
# arithmetic's raw precision -- a boutique cuts to the nearest ~10cm, not the
# nearest centimetre, so a range like "10.28-10.76m" claims precision the
# underlying estimate doesn't have (section 8: "remove false precision").
_DISPLAY_DECIMALS = 1


def _size_steps_from_reference(size: str, reference_size: str) -> int:
    try:
        return _SIZE_ORDER.index(size) - _SIZE_ORDER.index(reference_size)
    except ValueError:
        return 0


def _flare_steps(requested_flare: str | None, natural_flare: str) -> int:
    if requested_flare is None:
        return 0
    try:
        return _FLARE_ORDER.index(requested_flare) - _FLARE_ORDER.index(natural_flare)
    except ValueError:
        return 0


def calculate_consumption(
    garment_id: str,
    silhouette_id: str,
    size: str | None = None,
    fabric_width_cm: float = 112.0,
    flare_level: str | None = None,
    include_sleeve_allowance: bool = False,
    include_lining: bool = True,
    include_border: bool = False,
    directional_motif: bool = False,
    batch_quantity: int = 1,
) -> ConsumptionEstimate:
    rule_repo = get_consumption_rule_repository()
    silhouette_repo = get_silhouette_repository()

    rule = rule_repo.get(garment_id, silhouette_id)
    size_used = size or "M"

    if rule is None:
        return ConsumptionEstimate(
            garment_id=garment_id,
            silhouette_id=silhouette_id,
            status=ConsumptionStatus.NO_CURATED_RULE,
            assumptions=[
                f"No curated consumption rule exists for ({garment_id}, {silhouette_id}) -- required yardage "
                "cannot be honestly estimated for this combination yet."
            ],
            confidence=Confidence.of(_NO_CURATED_RULE_CONFIDENCE),
        )

    assumptions: list[str] = []
    modifiers_applied: list[str] = []
    if not size:
        assumptions.append("No size given -- assumed Medium.")

    silhouette = silhouette_repo.get(silhouette_id)
    natural_flare = silhouette.default_flare_level if silhouette else FlareLevel.MODERATE.value
    flare_level_used = flare_level or natural_flare

    modifiers: dict[str, float] = {}

    steps = _size_steps_from_reference(size_used, rule.reference_size)
    size_grading_pct = steps * rule.grading_increment_pct
    graded = rule.base_metres * (1 + size_grading_pct)
    if steps:
        modifiers["size_grading_pct"] = round(size_grading_pct, 4)
        modifiers_applied.append(f"size grading: {steps:+d} step(s) from {rule.reference_size}")

    flare_steps = _flare_steps(flare_level_used, natural_flare)
    flare_adjustment_pct = flare_steps * rule.flare_modifier_pct
    after_flare = graded * (1 + flare_adjustment_pct)
    if flare_steps:
        modifiers["flare_adjustment_pct"] = round(flare_adjustment_pct, 4)
        assumptions.append(
            f"Consumption reflects '{flare_level_used}' flare, not this silhouette's natural "
            f"'{natural_flare}' -- {'more' if flare_steps > 0 else 'less'} volume than the baseline cut."
        )
        modifiers_applied.append(f"flare adjustment: {flare_steps:+d} step(s)")

    width_ratio = rule.reference_width_cm / fabric_width_cm if fabric_width_cm else 1.0
    if fabric_width_cm and fabric_width_cm < rule.reference_width_cm:
        assumptions.append(
            f"Fabric width {fabric_width_cm:.0f}cm is narrower than the {rule.reference_width_cm:.0f}cm "
            "reference -- more metres required to compensate."
        )
    at_width = after_flare * width_ratio

    addons = 0.0
    if include_sleeve_allowance and rule.sleeve_modifier_m:
        sleeve_m = rule.sleeve_modifier_m * width_ratio
        addons += sleeve_m
        modifiers["sleeve_m"] = round(sleeve_m, 2)
        modifiers_applied.append(f"sleeve allowance: +{sleeve_m:.2f}m")
    if include_lining and rule.lining_modifier_m:
        lining_m = rule.lining_modifier_m * width_ratio
        addons += lining_m
        modifiers["lining_m"] = round(lining_m, 2)
        modifiers_applied.append(f"lining: +{lining_m:.2f}m")
    if include_border and rule.border_modifier_m:
        border_m = rule.border_modifier_m * width_ratio
        addons += border_m
        modifiers["border_m"] = round(border_m, 2)
        modifiers_applied.append(f"border: +{border_m:.2f}m")

    wastage = rule.wastage_allowance_pct
    if directional_motif:
        # A rule can override this via seed data; absent that, a sensible
        # universal default applies rather than silently having no effect.
        wastage += rule.directional_motif_wastage_pct or _DEFAULT_DIRECTIONAL_MOTIF_WASTAGE_PCT
        modifiers_applied.append("directional motif: extra wastage allowance for pattern matching")
        assumptions.append("Fabric has a directional motif -- panels must all face the same way, adding wastage.")
    modifiers["wastage_pct"] = round(wastage, 4)

    subtotal = at_width + addons
    final_metres = subtotal * (1 + wastage)

    # Band width scales inversely with the rule's own confidence -- a
    # well-established seeded rule doesn't need the same hedge as a shakier
    # one (section 3: "the range should be reasonably narrow when the inputs
    # are specific").
    band_pct = max(_MIN_BAND_PCT, _BAND_SPREAD_PCT * (1 - rule.confidence))
    final_low = final_metres * (1 - band_pct / 2)
    final_high = final_metres * (1 + band_pct / 2)

    construction_assumptions = ConstructionAssumptions(
        fabric_width_cm=fabric_width_cm,
        size=size_used,
        flare_level=flare_level_used,
        sleeve_allowance_included=include_sleeve_allowance,
        lining_included=include_lining,
        border_included=include_border,
        directional_motif=directional_motif,
        wastage_percent=round(wastage * 100, 1),
    )

    return ConsumptionEstimate(
        garment_id=garment_id,
        silhouette_id=silhouette_id,
        status=ConsumptionStatus.ESTIMATED,
        min_metres=round(final_low * batch_quantity, _DISPLAY_DECIMALS),
        max_metres=round(final_high * batch_quantity, _DISPLAY_DECIMALS),
        base_metres=rule.base_metres,
        modifiers=modifiers,
        modifiers_applied=modifiers_applied,
        construction_assumptions=construction_assumptions,
        assumptions=assumptions,
        rule_source=rule.source,
        confidence=Confidence.of(rule.confidence),
    )
