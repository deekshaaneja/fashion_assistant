"""Structured diversity checking (Phase 2, section 29; strengthened by the
multi-direction generation fix, section 9). Compares candidates primarily on
STRUCTURAL attributes -- construction architecture, panelling, waist
placement, flare construction, garment length, neckline family, sleeve
architecture, layering (dupatta), dupatta strategy, bottom, and decoration
strategy -- with DesignDNA numeric distance only as a secondary signal.
Two candidates that only differ cosmetically (e.g. reworded rationale, a
different color word in the title) must read as similar; two candidates
built from genuinely different construction language must read as
different even if their DesignDNA vectors happen to land close together."""
from __future__ import annotations

from difflib import SequenceMatcher

from src.domain.models.design_proposal import DesignCandidate

_MAX_DNA_DISTANCE = 8**0.5
# Calibrated against real candidates: two archetypes sharing panelling
# vocabulary ("kalidar...") plus every axis that's structurally FORCED
# identical within one request (flare_construction, often bottom/waist_
# placement) still land ~0.75 apart when their neckline/decoration genuinely
# differ -- only candidates matching on nearly everything should be rejected
# as merely cosmetic variations.
_DEFAULT_SIMILARITY_THRESHOLD = 0.82


def _text_similarity(a: str | None, b: str | None) -> float:
    """Free-text construction fields (bodice_style, panelling, waist
    placement, garment length) are creative prose now, not a fixed
    vocabulary -- exact equality is nearly useless as a signal, so these are
    compared by lexical overlap instead."""
    a_norm = (a or "").strip().lower()
    b_norm = (b or "").strip().lower()
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _match(a, b) -> float:
    return 1.0 if a == b else 0.0


def structural_similarity(a: DesignCandidate, b: DesignCandidate) -> float:
    """0.0 = no structural overlap, 1.0 = identical on every structural axis
    checked. Pure structural comparison -- no DesignDNA involved (see
    `similarity` for the blended score)."""
    a_dupatta_included = bool(a.dupatta and a.dupatta.included)
    b_dupatta_included = bool(b.dupatta and b.dupatta.included)
    a_dupatta_strategy = a.dupatta.color_strategy if a.dupatta else None
    b_dupatta_strategy = b.dupatta.color_strategy if b.dupatta else None
    a_bottom = a.bottom.type if a.bottom else None
    b_bottom = b.bottom.type if b.bottom else None

    axes = [
        _text_similarity(a.construction.bodice_style, b.construction.bodice_style),  # construction architecture
        _text_similarity(a.construction.panelling, b.construction.panelling),
        _text_similarity(a.construction.waist_placement, b.construction.waist_placement),
        _match(a.construction.flare_construction, b.construction.flare_construction),
        _text_similarity(a.construction.garment_length, b.construction.garment_length),
        _match(a.neckline.type, b.neckline.type),  # neckline family
        _match((a.sleeves.length, a.sleeves.style), (b.sleeves.length, b.sleeves.style)),  # sleeve architecture
        _match(a_dupatta_included, b_dupatta_included),  # layering
        _text_similarity(a_bottom, b_bottom),
        _match(a_dupatta_strategy, b_dupatta_strategy),  # dupatta strategy
        _match(a.decoration.level, b.decoration.level),  # decoration strategy
    ]
    return sum(axes) / len(axes)


def similarity(a: DesignCandidate, b: DesignCandidate) -> float:
    """Structural attributes dominate (0.75) -- DesignDNA distance is only a
    secondary nudge (0.25). A genuinely different construction language must
    read as different even if both candidates' DNA vectors land close
    together; two structurally near-identical candidates must read as
    similar even if their DNA differs, since DNA alone can't be trusted to
    catch a merely cosmetic variation (different color/title, same cut)."""
    dna_similarity = 1.0 - min(1.0, a.design_dna.distance(b.design_dna) / _MAX_DNA_DISTANCE)
    return min(1.0, structural_similarity(a, b) * 0.75 + dna_similarity * 0.25)


def too_similar(a: DesignCandidate, b: DesignCandidate, threshold: float = _DEFAULT_SIMILARITY_THRESHOLD) -> bool:
    return similarity(a, b) >= threshold


def filter_diverse(
    candidates: list[DesignCandidate], count: int, threshold: float = _DEFAULT_SIMILARITY_THRESHOLD
) -> tuple[list[DesignCandidate], int]:
    """Greedy selection: keep the first candidate, then only add the next
    one if it isn't too similar to anything already kept. Returns
    (selected, rejected_count). Does NOT backfill with near-duplicates if
    fewer than `count` survive -- returning fewer honest directions beats
    padding with cosmetic variations (section 8)."""
    selected: list[DesignCandidate] = []
    rejected = 0
    for candidate in candidates:
        if len(selected) >= count:
            break
        if all(not too_similar(candidate, kept, threshold) for kept in selected):
            selected.append(candidate)
        else:
            rejected += 1
    return selected, rejected
