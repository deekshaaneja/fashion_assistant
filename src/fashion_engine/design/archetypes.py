"""Design archetype repository + matching/selection (Phase 2, section 8).
Archetypes are the deterministic "playing field" -- structurally distinct
design languages (construction, neckline family, sleeve family, decoration
and dupatta philosophy) with their own DesignDNA. A generative provider
picks/adapts within this field; it never invents construction language from
nothing (section 30: "rules define the playing field; the model designs
within it")."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.domain.models.design_dna import DesignDNA
from src.domain.models.garment import Garment, Silhouette
from src.rules.loader import load_seed


@dataclass(frozen=True)
class SleeveFamily:
    length: str
    style: str


@dataclass(frozen=True)
class DesignArchetype:
    id: str
    name: str
    description: str
    design_dna: DesignDNA
    preferred_flare_construction: tuple[str, ...]
    preferred_flare_level: tuple[str, ...]
    preferred_structure_affinity: tuple[str, ...]
    preferred_wear_categories: tuple[str, ...]
    bodice_style: str
    panelling: str | None
    neckline_families: tuple[str, ...]
    neckline_depth_tendency: str
    sleeve_families: tuple[SleeveFamily, ...]
    decoration_philosophy: str
    dupatta_philosophy: str
    garment_length: str
    waist_placement: str
    hem_treatment: str
    style_keywords: tuple[str, ...]


def _load_archetypes() -> tuple[DesignArchetype, ...]:
    raw = load_seed("design_archetypes.yaml")["archetypes"]
    archetypes = []
    for row in raw:
        archetypes.append(
            DesignArchetype(
                id=row["id"],
                name=row["name"],
                description=row["description"].strip(),
                design_dna=DesignDNA(**row["design_dna"]),
                preferred_flare_construction=tuple(row["preferred_flare_construction"]),
                preferred_flare_level=tuple(row["preferred_flare_level"]),
                preferred_structure_affinity=tuple(row["preferred_structure_affinity"]),
                preferred_wear_categories=tuple(row["preferred_wear_categories"]),
                bodice_style=row["bodice_style"],
                panelling=row.get("panelling"),
                neckline_families=tuple(row["neckline_families"]),
                neckline_depth_tendency=row["neckline_depth_tendency"],
                sleeve_families=tuple(SleeveFamily(**sf) for sf in row["sleeve_families"]),
                decoration_philosophy=row["decoration_philosophy"],
                dupatta_philosophy=row["dupatta_philosophy"],
                garment_length=row["garment_length"],
                waist_placement=row["waist_placement"],
                hem_treatment=row["hem_treatment"],
                style_keywords=tuple(row["style_keywords"]),
            )
        )
    return tuple(archetypes)


@lru_cache
def get_design_archetypes() -> tuple[DesignArchetype, ...]:
    return _load_archetypes()


def score_archetype_fit(
    archetype: DesignArchetype, target_dna: DesignDNA, garment: Garment, silhouette: Silhouette
) -> float:
    """How well this archetype fits the client's aesthetic target AND the
    actual (garment, silhouette)'s own structural character -- an
    aesthetically-perfect archetype that fights the silhouette's real
    construction (e.g. wanting gathered volume on a controlled-only
    silhouette) scores lower. Not a public-facing score -- purely for
    candidate-generation selection."""
    dna_distance = archetype.design_dna.distance(target_dna)
    dna_score = max(0.0, 100.0 - dna_distance * 40.0)

    structure_match = 25.0 if silhouette.structure_affinity in archetype.preferred_structure_affinity else 0.0
    flare_construction_match = (
        20.0 if silhouette.flare_construction in archetype.preferred_flare_construction else 0.0
    )
    flare_level_match = 10.0 if silhouette.default_flare_level in archetype.preferred_flare_level else 0.0
    wear_category_match = 15.0 if garment.wear_category in archetype.preferred_wear_categories else 0.0

    return dna_score * 0.5 + structure_match + flare_construction_match + flare_level_match + wear_category_match


def select_diverse(
    scored: list[tuple[DesignArchetype, Garment, Silhouette, float]],
    count: int,
    min_dna_distance: float = 0.35,
) -> list[tuple[DesignArchetype, Garment, Silhouette, float]]:
    """Greedy diverse-subset selection (section 29): take the best-scoring
    candidate, then only accept the next one if its DesignDNA is at least
    `min_dna_distance` from every already-selected candidate. If the
    threshold can't be satisfied `count` times, relax it rather than
    returning fewer directions than requested -- a slightly-less-diverse
    third direction beats silently returning only two."""
    ranked = sorted(scored, key=lambda row: row[3], reverse=True)
    selected: list[tuple[DesignArchetype, Garment, Silhouette, float]] = []

    for row in ranked:
        if len(selected) >= count:
            break
        archetype = row[0]
        if all(archetype.design_dna.distance(s[0].design_dna) >= min_dna_distance for s in selected):
            selected.append(row)

    if len(selected) < count:
        for row in ranked:
            if len(selected) >= count:
                break
            if row not in selected:
                selected.append(row)

    return selected[:count]
