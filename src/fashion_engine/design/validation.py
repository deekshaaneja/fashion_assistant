"""Design validation: Phase 2, section 18. Hard, deterministic checks a
generated DesignCandidate must pass regardless of which provider produced
it -- a provider proposes, this disposes. A candidate failing any check here
is rejected outright, never silently patched -- the LLM must never be able
to silently override a fabric/construction constraint (section 2)."""
from __future__ import annotations

from src.domain.enums import DecorationLevel
from src.domain.models.design_generation import DesignGenerationRequest
from src.domain.models.design_proposal import DesignCandidate

_DECORATION_ORDER = [
    DecorationLevel.NO_ADDITIONAL_DECORATION,
    DecorationLevel.MINIMAL,
    DecorationLevel.MODERATE,
    DecorationLevel.STATEMENT,
]


def validate_candidate(candidate: DesignCandidate, request: DesignGenerationRequest) -> list[str]:
    """Returns a list of violation reasons -- empty means the candidate
    passed every hard check."""
    issues: list[str] = []
    constraints = request.constraints

    # --- fabric/construction coherence --------------------------------
    if (
        candidate.garment.garment.id != request.garment_id
        or candidate.garment.silhouette.id != request.silhouette_id
    ):
        issues.append(
            f"garment/silhouette mismatch: expected ({request.garment_id}, {request.silhouette_id}), got "
            f"({candidate.garment.garment.id}, {candidate.garment.silhouette.id})"
        )
    if candidate.construction.flare_construction != constraints.flare_construction:
        issues.append(
            f"flare_construction '{candidate.construction.flare_construction}' does not match this "
            f"silhouette's actual '{constraints.flare_construction}'"
        )
    if candidate.construction.flare_level != constraints.effective_flare_level:
        issues.append(
            f"flare_level '{candidate.construction.flare_level}' ignores the fabric-appropriate "
            f"'{constraints.effective_flare_level}' ceiling"
        )
    if constraints.requires_lining and candidate.lining is not None and not candidate.lining.required:
        issues.append("lining marked not required, but this fabric's transparency requires it")
    if candidate.sleeves.length == "sleeveless" and candidate.sleeves.sheer:
        issues.append("sleeves marked sheer while also sleeveless -- there is no sleeve fabric to be sheer")

    # --- surface coherence ---------------------------------------------
    ceiling_idx = _DECORATION_ORDER.index(DecorationLevel(constraints.max_embellishment_intensity))
    level_idx = _DECORATION_ORDER.index(DecorationLevel(candidate.decoration.level))
    if level_idx > ceiling_idx:
        issues.append(
            f"decoration level '{candidate.decoration.level}' exceeds this fabric's "
            f"'{constraints.max_embellishment_intensity}' ceiling"
        )

    # --- brief coherence -------------------------------------------------
    brief = request.client_brief
    if brief.preferred_neckline is not None and candidate.neckline.type != brief.preferred_neckline:
        issues.append(
            f"neckline '{candidate.neckline.type}' conflicts with the client's stated "
            f"'{brief.preferred_neckline}' preference"
        )
    if brief.preferred_sleeve is not None and candidate.sleeves.length != brief.preferred_sleeve:
        issues.append(
            f"sleeve length '{candidate.sleeves.length}' conflicts with the client's stated "
            f"'{brief.preferred_sleeve}' preference"
        )
    if (
        brief.embellishment_preference == "none"
        and candidate.decoration.level != DecorationLevel.NO_ADDITIONAL_DECORATION
    ):
        issues.append("client asked for no embellishment, but decoration was proposed anyway")

    return issues
