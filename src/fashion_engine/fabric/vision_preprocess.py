"""Phase 3, section 7 & 26: image preprocessing/validation BEFORE any vision
model call -- resolution, blur, exposure, color cast, corruption, and
near-duplicate detection. Pure Pillow, no ML model involved; these are
facts we can determine deterministically without spending a single vision
-model token on a photo that's unusable or a repeat of one already sent.

Deliberately permissive: only truly broken images (corrupt, blank, huge,
tiny) are marked unusable. Everything else stays usable with warnings --
"do not reject imperfect boutique photographs unnecessarily" (section 7)."""
from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageStat

from src.domain.models.fabric_vision import ImageQualityAssessment

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20MB -- section 34's "huge file" failure mode
MIN_USABLE_DIMENSION = 50  # px -- below this, there isn't enough signal to call it usable at all
LOW_RESOLUTION_WARNING_DIMENSION = 400
BLUR_STDDEV_THRESHOLD = 6.0
BLANK_STDDEV_THRESHOLD = 1.0
UNDEREXPOSED_MEAN = 40.0
OVEREXPOSED_MEAN = 215.0
COLOR_CAST_DELTA = 25.0
DUPLICATE_HAMMING_THRESHOLD = 5  # out of 64 bits -- near-identical, not just similarly-colored


def decode_image(image_bytes: bytes) -> Image.Image | None:
    """Never raises -- returns None for corrupt/unsupported/unreadable
    bytes (section 34's "unsupported image format"/"corrupt image")."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()  # force full decode now, not lazily later
        return image.convert("RGB")
    except Exception:
        return None


def assess_quality(image_id: str, image_bytes: bytes) -> ImageQualityAssessment:
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return ImageQualityAssessment(
            image_id=image_id,
            usable=False,
            warnings=[f"File exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)}MB size limit."],
        )

    image = decode_image(image_bytes)
    if image is None:
        return ImageQualityAssessment(
            image_id=image_id,
            usable=False,
            warnings=["Could not decode this file -- unsupported or corrupt image format."],
        )

    width, height = image.size
    if width < MIN_USABLE_DIMENSION or height < MIN_USABLE_DIMENSION:
        return ImageQualityAssessment(
            image_id=image_id,
            usable=False,
            warnings=[f"Image is only {width}x{height}px -- too small to analyze reliably."],
            width=width,
            height=height,
        )

    grayscale = image.convert("L")
    brightness = ImageStat.Stat(grayscale).mean[0]
    overall_stddev = ImageStat.Stat(grayscale).stddev[0]
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    sharpness = ImageStat.Stat(edges).stddev[0]

    warnings: list[str] = []
    usable = True

    if overall_stddev < BLANK_STDDEV_THRESHOLD:
        usable = False
        warnings.append("Image appears blank or nearly uniform -- no fabric detail visible.")

    if width < LOW_RESOLUTION_WARNING_DIMENSION or height < LOW_RESOLUTION_WARNING_DIMENSION:
        warnings.append(f"Low resolution ({width}x{height}px) -- fine surface detail may not be reliable.")

    if sharpness < BLUR_STDDEV_THRESHOLD:
        warnings.append("Image appears blurry or soft-focus -- surface/texture detail may be unreliable.")

    if brightness < UNDEREXPOSED_MEAN:
        warnings.append("Image is underexposed/dark -- color and surface detail may be distorted.")
    elif brightness > OVEREXPOSED_MEAN:
        warnings.append("Image is overexposed/bright -- color and surface detail may be distorted.")

    r_mean, g_mean, b_mean = ImageStat.Stat(image).mean
    other_avg_for_r = (g_mean + b_mean) / 2
    other_avg_for_b = (r_mean + g_mean) / 2
    if r_mean - other_avg_for_r > COLOR_CAST_DELTA:
        warnings.append("Warm indoor lighting may distort the actual fabric color.")
    elif b_mean - other_avg_for_b > COLOR_CAST_DELTA:
        warnings.append("Cool/blue-toned lighting may distort the actual fabric color.")

    return ImageQualityAssessment(
        image_id=image_id,
        usable=usable,
        warnings=warnings,
        width=width,
        height=height,
        sharpness_score=round(sharpness, 1),
        brightness_score=round(brightness, 1),
    )


def average_hash(image: Image.Image, hash_size: int = 8) -> str:
    """A simple perceptual hash (section 26) -- good enough to catch exact
    or near-exact duplicate uploads, not a general similarity search."""
    small = image.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())
    average = sum(pixels) / len(pixels)
    return "".join("1" if p >= average else "0" for p in pixels)


def hamming_distance(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b, strict=True) if x != y)


def detect_duplicates(
    hashes: dict[str, str], threshold: int = DUPLICATE_HAMMING_THRESHOLD
) -> dict[str, str | None]:
    """Returns {image_id: duplicate_of_image_id | None}. Processes in
    insertion order so the FIRST occurrence of a repeated photo is always
    the one kept as independent evidence (section 26 -- five copies of the
    same photo must not count as five independent pieces of evidence)."""
    kept: list[str] = []
    result: dict[str, str | None] = {}
    for image_id, h in hashes.items():
        duplicate_of = next((k for k in kept if hamming_distance(h, hashes[k]) <= threshold), None)
        result[image_id] = duplicate_of
        if duplicate_of is None:
            kept.append(image_id)
    return result
