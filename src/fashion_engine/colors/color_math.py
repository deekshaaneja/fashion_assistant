"""Deterministic HSL color math. No LLM is ever asked to invent a color
relationship -- every hue/tint/shade here is exact arithmetic (section 12)."""
from __future__ import annotations

import colorsys


def hex_to_hsl(hex_str: str) -> tuple[float, float, float]:
    """Returns (hue_degrees[0,360), saturation[0,1], lightness[0,1])."""
    hex_str = hex_str.lstrip("#")
    r, g, b = (int(hex_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    return (hue * 360.0) % 360.0, saturation, lightness


def hsl_to_hex(hue_degrees: float, saturation: float, lightness: float) -> str:
    saturation = min(max(saturation, 0.0), 1.0)
    lightness = min(max(lightness, 0.0), 1.0)
    r, g, b = colorsys.hls_to_rgb((hue_degrees % 360.0) / 360.0, lightness, saturation)
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def rotate_hue(hex_str: str, degrees: float) -> str:
    hue, saturation, lightness = hex_to_hsl(hex_str)
    return hsl_to_hex(hue + degrees, saturation, lightness)


def shift_lightness(hex_str: str, delta: float) -> str:
    hue, saturation, lightness = hex_to_hsl(hex_str)
    return hsl_to_hex(hue, saturation, lightness + delta)


def desaturate(hex_str: str, delta: float) -> str:
    hue, saturation, lightness = hex_to_hsl(hex_str)
    return hsl_to_hex(hue, saturation + delta, lightness)
