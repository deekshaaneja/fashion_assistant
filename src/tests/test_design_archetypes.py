from __future__ import annotations

from src.domain.models.design_dna import DesignDNA
from src.fashion_engine.design.archetypes import get_design_archetypes, score_archetype_fit, select_diverse
from src.rules.repository import get_garment_repository, get_silhouette_repository


def test_archetypes_load_and_are_structurally_distinct():
    archetypes = get_design_archetypes()
    assert len(archetypes) >= 4
    # No two archetypes should be identical in construction language
    bodice_styles = [a.bodice_style for a in archetypes]
    assert len(set(bodice_styles)) == len(bodice_styles)


def test_select_diverse_respects_count_and_distinctness():
    garment = get_garment_repository().get("suit")
    silhouette = get_silhouette_repository().get("anarkali")
    target = DesignDNA()
    archetypes = get_design_archetypes()
    scored = [(a, garment, silhouette, score_archetype_fit(a, target, garment, silhouette)) for a in archetypes]
    selected = select_diverse(scored, count=3)
    assert len(selected) == 3
    chosen_ids = {row[0].id for row in selected}
    assert len(chosen_ids) == 3  # no archetype picked twice


def test_score_archetype_fit_rewards_matching_flare_construction():
    garment = get_garment_repository().get("suit")
    panelled = get_silhouette_repository().get("panelled")  # controlled
    anarkali = get_silhouette_repository().get("anarkali")  # gathered
    architectural = next(a for a in get_design_archetypes() if a.id == "architectural_panelled_contemporary")
    target = DesignDNA()
    score_vs_controlled = score_archetype_fit(architectural, target, garment, panelled)
    score_vs_gathered = score_archetype_fit(architectural, target, garment, anarkali)
    assert score_vs_controlled > score_vs_gathered
