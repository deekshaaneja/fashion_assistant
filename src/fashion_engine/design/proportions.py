"""recommend_proportions: Phase 2, section 12. Descriptive/normalized
proportion decisions -- garment length, waist placement, flare, slit, panel
category, bodice length, sleeve proportion, dupatta scale, overlay length.
Not pattern drafting -- no exact measurements."""
from __future__ import annotations

from src.domain.enums import FlareLevel
from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import ProportionSpec

_PANEL_CATEGORY_BY_FLARE_CONSTRUCTION = {
    "controlled": "4-6 panel, tailored",
    "gathered": "many-panel gathered (kalidar-style)",
    "dramatic": "full-circle/many-panel gathered",
}


def recommend_proportions(
    garment_length: str,
    waist_placement: str,
    effective_flare_level: str,
    flare_construction: str,
    client_brief: ClientBrief,
    has_dupatta: bool,
    has_overlay: bool,
) -> ProportionSpec:
    reasons: list[str] = []

    length = client_brief.preferred_length or garment_length
    if client_brief.preferred_length:
        reasons.append(f"Client specified a {client_brief.preferred_length.replace('_', ' ')} length.")

    panel_category = _PANEL_CATEGORY_BY_FLARE_CONSTRUCTION.get(flare_construction)

    dupatta_scale = None
    if has_dupatta:
        dupatta_scale = "oversized, statement drape" if client_brief.understated_statement_lean and (
            client_brief.understated_statement_lean >= 0.7
        ) else "standard"
        reasons.append(f"Dupatta scaled '{dupatta_scale}' to match the overall statement level of this direction.")

    overlay_length = "hip-length structured overlay" if has_overlay else None

    return ProportionSpec(
        garment_length=length,
        waist_placement=waist_placement,
        flare_level=FlareLevel(effective_flare_level),
        panel_category=panel_category,
        dupatta_scale=dupatta_scale,
        overlay_length=overlay_length,
        rationale=" ".join(reasons) or "Proportions follow this direction's own construction language.",
    )
