"""FabricReferenceSelector: Phase 4, section 11. Not every fabric photograph
should be sent to the image generator -- pick the images that actually
carry design-relevant visual information for THIS design, record which were
chosen and why, and respect the provider's reference-image limit (this
account's `qwen-image-edit` accepts 1-3 -- see
`src/providers/visualization.py`)."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.models.fabric_vision import ImageRole
from src.domain.models.visualization import FabricReferenceSelection, SelectedFabricReference

# Priority order when references must be trimmed to fit the provider limit.
# FULL_VIEW carries overall pattern/color -- always the anchor reference.
# CLOSE_UP is next for embroidery/texture detail. BORDER only matters when
# the design actually uses the border. DRAPE only when material behavior
# (how it falls/moves) is genuinely relevant to this construction.
_BASE_PRIORITY = [ImageRole.FULL_VIEW, ImageRole.CLOSE_UP, ImageRole.BORDER, ImageRole.DRAPE]
_LOW_PRIORITY = [ImageRole.REVERSE, ImageRole.TRANSPARENCY, ImageRole.UNKNOWN]

_REASONS = {
    ImageRole.FULL_VIEW: "full view -- carries overall pattern/color.",
    ImageRole.CLOSE_UP: "close-up -- carries embroidery/surface texture detail.",
    ImageRole.BORDER: "border view -- this design uses the fabric's border.",
    ImageRole.DRAPE: "drape view -- material fall/movement is relevant to this construction.",
    ImageRole.REVERSE: "reverse view -- lower priority, included only if reference slots remain.",
    ImageRole.TRANSPARENCY: "transparency/backlit view -- lower priority, included only if slots remain.",
    ImageRole.UNKNOWN: "unlabeled role -- lower priority, included only if slots remain.",
}


@dataclass
class CandidateFabricImage:
    """Lightweight metadata this selector needs -- deliberately decoupled
    from raw image bytes (those stay at the pipeline/provider boundary,
    matching Phase 3's convention)."""

    image_id: str
    role: ImageRole
    usable: bool
    duplicate_of: str | None = None


def select_fabric_references(
    candidates: list[CandidateFabricImage],
    max_references: int,
    uses_border: bool,
    flare_construction_uses_drape: bool = True,
) -> FabricReferenceSelection:
    """Deterministic, explainable selection -- never silent. Unusable or
    duplicate images are never selected regardless of role."""
    eligible = [c for c in candidates if c.usable and c.duplicate_of is None]
    excluded = [c.image_id for c in candidates if c not in eligible]

    def _priority(role: ImageRole) -> int:
        if role == ImageRole.BORDER and not uses_border:
            return len(_BASE_PRIORITY) + len(_LOW_PRIORITY)  # deprioritized -- design doesn't use the border
        if role == ImageRole.DRAPE and not flare_construction_uses_drape:
            return len(_BASE_PRIORITY) + len(_LOW_PRIORITY)
        if role in _BASE_PRIORITY:
            return _BASE_PRIORITY.index(role)
        if role in _LOW_PRIORITY:
            return len(_BASE_PRIORITY) + _LOW_PRIORITY.index(role)
        return len(_BASE_PRIORITY) + len(_LOW_PRIORITY)

    ranked = sorted(eligible, key=lambda c: _priority(c.role))
    chosen = ranked[:max_references]
    excluded += [c.image_id for c in ranked[max_references:]]

    selected = [
        SelectedFabricReference(image_id=c.image_id, role=c.role, reason=_REASONS.get(c.role, "selected."))
        for c in chosen
    ]
    return FabricReferenceSelection(selected=selected, excluded_image_ids=excluded, max_references=max_references)
