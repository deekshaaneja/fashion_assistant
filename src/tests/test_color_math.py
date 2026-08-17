from __future__ import annotations

import pytest

from src.fashion_engine.colors.color_math import hex_to_hsl, hsl_to_hex, rotate_hue, shift_lightness


def test_hex_hsl_round_trip():
    for hex_str in ("#8B0000", "#0F5132", "#FFFFFF", "#000000"):
        hue, sat, light = hex_to_hsl(hex_str)
        assert hsl_to_hex(hue, sat, light) == hex_str


def test_rotate_hue_180_is_exact_complement():
    base_hue, _, _ = hex_to_hsl("#1B3A6B")
    rotated = rotate_hue("#1B3A6B", 180)
    rotated_hue, _, _ = hex_to_hsl(rotated)
    assert rotated_hue == pytest.approx((base_hue + 180) % 360, abs=0.5)


def test_shift_lightness_preserves_hue():
    hue_before, sat_before, _ = hex_to_hsl("#8B0000")
    shifted = shift_lightness("#8B0000", 0.2)
    hue_after, sat_after, _ = hex_to_hsl(shifted)
    assert hue_after == pytest.approx(hue_before, abs=2.0)
    assert sat_after == pytest.approx(sat_before, abs=0.05)
