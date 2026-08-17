"""Maps a ClientBrief's free-form/explicit aesthetic signals onto a target
DesignDNA -- the internal aesthetic language every archetype and candidate
is compared against (section 6). Never a designer name; designer/aesthetic
references would map INTO this representation in a later phase, not replace
it."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_dna import DesignDNA

# Free-form aesthetic tag -> DNA axis nudges. Deliberately moderate values
# (not 0.0/1.0) so multiple tags compose into a blended target rather than
# each fighting to dominate the vector; a tag that doesn't interact with an
# axis simply isn't listed for it.
_AESTHETIC_TAG_NUDGES: dict[str, dict[str, float]] = {
    "elegant": {"understated_glamorous": 0.55, "romantic_sharp": 0.4},
    "contemporary": {"traditional_contemporary": 0.85, "heritage_modern": 0.8},
    "traditional": {"traditional_contemporary": 0.15, "heritage_modern": 0.2},
    "modern": {"heritage_modern": 0.85, "traditional_contemporary": 0.8},
    "minimal": {"minimal_maximal": 0.15, "subtle_statement": 0.2},
    "maximal": {"minimal_maximal": 0.85, "subtle_statement": 0.8},
    "romantic": {"romantic_sharp": 0.15, "soft_architectural": 0.2},
    "sharp": {"romantic_sharp": 0.85, "soft_architectural": 0.8},
    "architectural": {"soft_architectural": 0.85, "fluid_structured": 0.8},
    "soft": {"soft_architectural": 0.15, "fluid_structured": 0.2},
    "glamorous": {"understated_glamorous": 0.85, "subtle_statement": 0.75},
    "understated": {"understated_glamorous": 0.2, "subtle_statement": 0.2},
    "statement": {"subtle_statement": 0.85, "understated_glamorous": 0.7},
    "heritage": {"heritage_modern": 0.15, "traditional_contemporary": 0.2},
    "bridal": {"heritage_modern": 0.2, "minimal_maximal": 0.75},
    "festive": {"minimal_maximal": 0.7, "subtle_statement": 0.65},
    "fluid": {"fluid_structured": 0.15},
    "structured": {"fluid_structured": 0.85},
    "clean": {"minimal_maximal": 0.2, "soft_architectural": 0.6},
}


def derive_target_dna(client_brief: ClientBrief) -> DesignDNA:
    axis_samples: dict[str, list[float]] = {}
    for tag in client_brief.desired_aesthetic:
        nudges = _AESTHETIC_TAG_NUDGES.get(tag.lower().strip())
        if not nudges:
            continue
        for axis, value in nudges.items():
            axis_samples.setdefault(axis, []).append(value)

    values: dict[str, float] = {axis: sum(samples) / len(samples) for axis, samples in axis_samples.items()}

    if client_brief.traditional_contemporary_lean is not None:
        values["traditional_contemporary"] = client_brief.traditional_contemporary_lean
    if client_brief.understated_statement_lean is not None:
        values["subtle_statement"] = client_brief.understated_statement_lean

    if client_brief.embellishment_preference == "heavy":
        values["subtle_statement"] = max(values.get("subtle_statement", 0.5), 0.7)
        values["minimal_maximal"] = max(values.get("minimal_maximal", 0.5), 0.7)
    elif client_brief.embellishment_preference in ("none", "minimal"):
        values["minimal_maximal"] = min(values.get("minimal_maximal", 0.5), 0.35)

    return DesignDNA(**values)
