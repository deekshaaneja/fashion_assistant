from __future__ import annotations

from src.rules.repository import (
    get_consumption_rule_repository,
    get_embellishment_repository,
    get_fabric_repository,
    get_garment_repository,
    get_silhouette_repository,
)


def test_all_seed_catalogs_load_and_validate():
    assert len(get_fabric_repository().all()) == 20
    assert len(get_garment_repository().all()) == 17
    assert len(get_silhouette_repository().all()) == 16
    assert len(get_consumption_rule_repository().all()) > 0
    assert len(get_embellishment_repository().all()) == 13


def test_fabric_resolve_exact_match():
    resolution = get_fabric_repository().resolve("organza")
    assert resolution.method == "exact"
    assert resolution.profile.id == "organza"
    assert resolution.confidence >= 0.9


def test_fabric_resolve_partial_match():
    resolution = get_fabric_repository().resolve("embroidered organza")
    assert resolution.method == "partial"
    assert resolution.profile.id == "organza"


def test_fabric_resolve_unresolved_degrades_gracefully():
    resolution = get_fabric_repository().resolve("totally made up fabric xyz")
    assert resolution.method == "unresolved"
    assert resolution.profile.id == "unknown_fabric"
    assert resolution.confidence < 0.3


def test_silhouette_for_garment():
    silhouettes = get_silhouette_repository().for_garment("suit")
    ids = {s.id for s in silhouettes}
    assert "straight" in ids
    assert "a_line" in ids
    assert "anarkali" in ids


def test_consumption_rule_lookup():
    rule = get_consumption_rule_repository().get("suit", "anarkali")
    assert rule is not None
    assert rule.base_metres == 5.0  # matches section 10's "Medium Anarkali ~5m"


def test_blouse_base_metres_matches_product_brief_example():
    rule = get_consumption_rule_repository().get("blouse", "draped")
    assert rule is not None
    assert rule.base_metres == 1.0  # matches section 10's "Medium blouse ~1m"


def test_a_line_suit_base_metres_matches_product_brief_example():
    rule = get_consumption_rule_repository().get("suit", "a_line")
    assert rule is not None
    assert rule.base_metres == 3.0  # matches section 10's "Medium A-line ~3m"
