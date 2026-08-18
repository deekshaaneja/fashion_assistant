"""Shared test fixtures/helpers. Phase 3 image tests use procedurally
generated synthetic images ONLY -- never the real photographs under
`eval_data/phase3/` (those are reserved for the blind evaluation harness,
see scripts/run_vision_eval.py)."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw


def make_synthetic_fabric_image(
    size: tuple[int, int] = (300, 300),
    background: tuple[int, int, int] = (120, 20, 60),
    accent: tuple[int, int, int] | None = (230, 200, 80),
    fmt: str = "JPEG",
) -> bytes:
    """A deterministic, procedurally generated stand-in "fabric photo" --
    solid background plus an optional accent shape. Good enough to exercise
    decoding/quality/dedup/mock-provider logic; NOT a substitute for a real
    photograph."""
    image = Image.new("RGB", size, color=background)
    if accent is not None:
        draw = ImageDraw.Draw(image)
        w, h = size
        draw.ellipse((w * 0.2, h * 0.2, w * 0.8, h * 0.8), fill=accent)
    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=85)
    return buf.getvalue()


def make_blank_image(size: tuple[int, int] = (300, 300), color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def make_tiny_image(size: tuple[int, int] = (20, 20)) -> bytes:
    return make_synthetic_fabric_image(size=size)


def make_non_fabric_image() -> bytes:
    """Stands in for "a photo of a shoe/person/room" -- a simple synthetic
    silhouette shape, distinct in structure from the plain-swatch helper
    above so tests can exercise a fake provider's non_fabric classification
    path without depending on real object-detection."""
    image = Image.new("RGB", (300, 300), color=(240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.polygon([(60, 220), (240, 220), (220, 260), (80, 260)], fill=(40, 40, 40))
    draw.rectangle((100, 60, 200, 220), fill=(90, 60, 30))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()
