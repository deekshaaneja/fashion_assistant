"""Design coherence: Phase 3.1, section 9. A reusable layer for cross-field
structural invariants over an already-assembled `DesignCandidate` -- kept
separate from `validation.py`'s fabric/constraint checks and from
`assembly.py`'s per-component logic so these invariants are checked in
exactly one place rather than scattered across both.

Two halves, deliberately different in what they do on failure:

- `normalize_coherence`: cheaply auto-fixable contradictions (a leftover
  attribute on an excluded component, decoration treatments surviving a
  NO_ADDITIONAL_DECORATION level) are corrected in place -- these are
  bookkeeping slips, not meaningful creative decisions, so silently
  rejecting the whole candidate over them would be wasteful. Every
  correction is recorded as a note (never silent).
- `check_coherence`: genuine structural contradictions that aren't safely
  auto-fixable (e.g. a flare_construction that is physically incoherent
  with the assigned flare_level) are returned as hard issues for
  `validate_candidate` to reject on.

No natural-language "is this coherent?" critique here (section 10) -- only
structural invariants over typed fields.
"""
from __future__ import annotations

from src.domain.enums import DecorationLevel, FlareConstruction
from src.domain.models.design_proposal import DesignCandidate

# A DRAMATIC (max-volume, circular/godet) construction cannot coherently
# carry only minimal/moderate flare -- if the construction is that, the
# amount of flare must be at least "high". CONTROLLED/GATHERED have no such
# floor (a controlled or gathered cut can be built at any flare amount).
_FLARE_CONSTRUCTION_MIN_LEVEL: dict[FlareConstruction, tuple[str, ...]] = {
    FlareConstruction.DRAMATIC: ("high", "dramatic"),
}


def normalize_coherence(candidate: DesignCandidate) -> tuple[DesignCandidate, list[str]]:
    """Auto-fixes cheaply-correctable cross-field contradictions. Returns the
    (possibly updated) candidate plus a list of human-readable notes
    describing what was normalized -- callers should surface these (e.g. in
    `risks`), never discard them silently."""
    notes: list[str] = []
    updates: dict[str, object] = {}

    if candidate.sleeves.length == "sleeveless" and candidate.sleeves.cuff_treatment:
        updates["sleeves"] = candidate.sleeves.model_copy(update={"cuff_treatment": None})
        notes.append("Dropped a cuff treatment proposed on a sleeveless design -- there is no cuff to treat.")

    if candidate.dupatta is not None and not candidate.dupatta.included:
        contradictory = {
            name: getattr(candidate.dupatta, name)
            for name in (
                "fabric_description",
                "weight",
                "transparency",
                "color_strategy",
                "border",
                "embellishment",
                "ombre_direction",
            )
            if getattr(candidate.dupatta, name) is not None
        }
        if contradictory:
            updates["dupatta"] = candidate.dupatta.model_copy(update=dict.fromkeys(contradictory, None))
            notes.append(
                "Cleared dupatta attributes (" + ", ".join(sorted(contradictory)) + ") proposed on a dupatta "
                "marked not included."
            )

    if (
        candidate.decoration.level == DecorationLevel.NO_ADDITIONAL_DECORATION
        and candidate.decoration.treatments
    ):
        updates["decoration"] = candidate.decoration.model_copy(update={"treatments": []})
        notes.append("Cleared decoration treatments proposed alongside NO_ADDITIONAL_DECORATION.")

    if not updates:
        return candidate, notes
    return candidate.model_copy(update=updates), notes


def check_coherence(candidate: DesignCandidate) -> list[str]:
    """Hard, structurally-testable invariants that survive normalization --
    genuine contradictions rather than bookkeeping slips. Returns violation
    reasons; empty means coherent."""
    issues: list[str] = []

    min_level = _FLARE_CONSTRUCTION_MIN_LEVEL.get(candidate.construction.flare_construction)
    if min_level is not None and candidate.construction.flare_level not in min_level:
        issues.append(
            f"flare_construction '{candidate.construction.flare_construction}' is not physically coherent with "
            f"flare_level '{candidate.construction.flare_level}' -- dramatic circular/godet construction needs "
            f"at least a high flare amount"
        )

    if candidate.sleeves.length == "sleeveless" and candidate.sleeves.cuff_treatment:
        issues.append(
            "sleeveless design still carries a cuff treatment after normalization -- inconsistent output"
        )

    if candidate.dupatta is not None and not candidate.dupatta.included:
        leftover = [
            name
            for name in (
                "fabric_description",
                "weight",
                "transparency",
                "color_strategy",
                "border",
                "embellishment",
                "ombre_direction",
            )
            if getattr(candidate.dupatta, name) is not None
        ]
        if leftover:
            issues.append(
                f"dupatta marked not included but still carries {', '.join(leftover)} after normalization"
            )

    if candidate.decoration.level == DecorationLevel.NO_ADDITIONAL_DECORATION and candidate.decoration.treatments:
        issues.append("NO_ADDITIONAL_DECORATION still carries decoration treatments after normalization")

    return issues