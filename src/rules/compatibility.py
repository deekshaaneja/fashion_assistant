"""Fabric<->Silhouette compatibility scoring: general property-based rules
(data/rules/fabric_silhouette_rules.yaml) plus curated per-fabric anchors
(Fabric.strong_fit_silhouettes/avoid_silhouettes). Pure, deterministic,
inspectable -- every point of the score traces back to a named rule. See
docs/rule-engine.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.models.fabric import Fabric
from src.domain.models.garment import Silhouette
from src.rules.loader import load_rules

_BASELINE_SCORE = 50.0
_STRONG_FIT_ANCHOR_DELTA = 25.0
_AVOID_ANCHOR_DELTA = -30.0

# Silhouette fields that are lists (membership/intersection check) rather
# than scalars (exact-match check).
_LIST_SILHOUETTE_FIELDS = {"aesthetic_tags"}


@dataclass(frozen=True)
class CompatibilityResult:
    score: float  # 0-100, not yet weighted into the overall ScoreBreakdown
    positive_reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    source_rules: list[str] = field(default_factory=list)


def _fabric_property_matches(fabric: Fabric, property_name: str, accepted_values: list[str]) -> bool:
    value = getattr(fabric.properties, property_name, None)
    return value is not None and value in accepted_values


def _silhouette_property_matches(silhouette: Silhouette, property_name: str, accepted_values: list[str]) -> bool:
    value = getattr(silhouette, property_name, None)
    if value is None:
        return False
    if property_name in _LIST_SILHOUETTE_FIELDS:
        return bool(set(value) & set(accepted_values))
    return value in accepted_values


def _general_rules(fabric: Fabric, silhouette: Silhouette) -> list[tuple[str, float, str]]:
    """Returns (rule_id, delta, reason) for every general rule that fires."""
    rule_set = load_rules("fabric_silhouette_rules.yaml")["rules"]
    fired: list[tuple[str, float, str]] = []

    for rule in rule_set:
        fabric_conditions: dict = rule.get("fabric_conditions", {})
        silhouette_conditions: dict = rule.get("silhouette_conditions", {})

        fabric_ok = all(
            _fabric_property_matches(fabric, prop, values) for prop, values in fabric_conditions.items()
        )
        silhouette_ok = all(
            _silhouette_property_matches(silhouette, prop, values)
            for prop, values in silhouette_conditions.items()
        )

        if fabric_ok and silhouette_ok:
            fired.append((rule["id"], float(rule["delta"]), rule["reason"]))

    return fired


def score_fabric_silhouette(fabric: Fabric, silhouette: Silhouette) -> CompatibilityResult:
    score = _BASELINE_SCORE
    positive_reasons: list[str] = []
    risks: list[str] = []
    source_rules: list[str] = []

    if silhouette.id in fabric.strong_fit_silhouettes:
        score += _STRONG_FIT_ANCHOR_DELTA
        positive_reasons.append(f"{fabric.name} is a curated strong pairing for {silhouette.name.lower()}")
        source_rules.append("curated_strong_fit_anchor")
    elif silhouette.id in fabric.avoid_silhouettes:
        score += _AVOID_ANCHOR_DELTA
        risks.append(f"{fabric.name} is a curated poor pairing for {silhouette.name.lower()}")
        source_rules.append("curated_avoid_anchor")

    for rule_id, delta, reason in _general_rules(fabric, silhouette):
        score += delta
        source_rules.append(rule_id)
        full_reason = f"{fabric.name} {reason}"
        if delta >= 0:
            positive_reasons.append(full_reason)
        else:
            risks.append(full_reason)

    return CompatibilityResult(
        score=max(0.0, min(100.0, score)),
        positive_reasons=positive_reasons,
        risks=risks,
        source_rules=source_rules,
    )
