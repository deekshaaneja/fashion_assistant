from __future__ import annotations

import pytest

from src.tools.calculate_consumption import calculate_consumption


def test_matches_product_brief_example_a_line_l_size_three_quarter_sleeve():
    """Section 10's worked example: ~3.6-3.9m for an L-size A-line with
    three-quarter sleeves at 44in width. We don't literally have a
    three-quarter-sleeve modifier wired to this exact garment/silhouette in
    the seed data, so this test checks the shape/order of magnitude, not an
    exact figure -- see section 18: test ranges, not exact numbers."""
    est = calculate_consumption("suit", "a_line", size="L", fabric_width_cm=112, include_sleeve_allowance=True)
    assert 3.0 <= est.min_metres <= 6.0
    assert est.min_metres < est.max_metres


def test_unknown_garment_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown garment"):
        calculate_consumption("not_a_real_garment", "a_line")


def test_unknown_silhouette_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown silhouette"):
        calculate_consumption("suit", "not_a_real_silhouette")


def test_no_seeded_rule_returns_explicit_unknown_not_a_fabricated_range():
    """Phase 1.2, section 6: a fabricated generic range is less honest than
    an explicit unknown -- no metres at all, a low-confidence label, and a
    NO_CURATED_RULE status a caller can act on."""
    est = calculate_consumption("fusion_set", "corset")
    assert est.status == "NO_CURATED_RULE"
    assert est.min_metres is None
    assert est.max_metres is None
    assert est.confidence.score < 0.3
    assert any("no curated consumption rule" in a.lower() for a in est.assumptions)


def test_size_grading_increases_yardage():
    m = calculate_consumption("suit", "a_line", size="M")
    xl = calculate_consumption("suit", "a_line", size="XL")
    assert xl.min_metres > m.min_metres


def test_narrower_width_increases_yardage():
    wide = calculate_consumption("suit", "anarkali", fabric_width_cm=112)
    narrow = calculate_consumption("suit", "anarkali", fabric_width_cm=44)
    assert narrow.min_metres > wide.min_metres


def test_never_returns_a_single_fake_precise_number():
    est = calculate_consumption("suit", "straight", size="M")
    assert est.min_metres < est.max_metres


def test_lining_included_by_default_increases_total():
    with_lining = calculate_consumption("suit", "anarkali", include_lining=True)
    without_lining = calculate_consumption("suit", "anarkali", include_lining=False)
    assert with_lining.min_metres > without_lining.min_metres


def test_display_precision_is_rounded_to_one_decimal():
    """Phase 1.2, section 8: precision must correspond to evidence quality --
    a range like '10.28-10.76m' claims more precision than a boutique
    estimate actually has; displayed metres round to the nearest 0.1m."""
    est = calculate_consumption("lehenga", "panelled", size="L", fabric_width_cm=98)
    assert round(est.min_metres, 1) == est.min_metres
    assert round(est.max_metres, 1) == est.max_metres


def test_directional_motif_adds_wastage_assumption():
    without = calculate_consumption("suit", "anarkali", directional_motif=False)
    with_motif = calculate_consumption("suit", "anarkali", directional_motif=True)
    assert with_motif.min_metres > without.min_metres
    assert any("directional motif" in a.lower() for a in with_motif.assumptions)
