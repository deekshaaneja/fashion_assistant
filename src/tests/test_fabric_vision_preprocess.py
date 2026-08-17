from __future__ import annotations

from src.fashion_engine.fabric.vision_preprocess import (
    MAX_IMAGE_BYTES,
    MIN_USABLE_DIMENSION,
    assess_quality,
    average_hash,
    decode_image,
    detect_duplicates,
    hamming_distance,
)
from src.tests.conftest import make_blank_image, make_synthetic_fabric_image, make_tiny_image


def test_decode_image_valid_bytes_returns_image():
    image = decode_image(make_synthetic_fabric_image())
    assert image is not None
    assert image.mode == "RGB"


def test_decode_image_corrupt_bytes_returns_none():
    assert decode_image(b"this is not an image") is None


def test_assess_quality_usable_image_has_no_blocking_issues():
    quality = assess_quality("img1", make_synthetic_fabric_image(size=(500, 500)))
    assert quality.usable is True
    assert quality.width == 500
    assert quality.height == 500


def test_assess_quality_corrupt_image_is_unusable():
    quality = assess_quality("img1", b"not an image at all")
    assert quality.usable is False
    assert any("decode" in w.lower() for w in quality.warnings)


def test_assess_quality_huge_file_is_unusable_without_decoding():
    oversized = b"0" * (MAX_IMAGE_BYTES + 1)
    quality = assess_quality("img1", oversized)
    assert quality.usable is False
    assert any("size limit" in w.lower() for w in quality.warnings)


def test_assess_quality_tiny_image_is_unusable():
    quality = assess_quality("img1", make_tiny_image(size=(MIN_USABLE_DIMENSION - 1, MIN_USABLE_DIMENSION - 1)))
    assert quality.usable is False
    assert any("too small" in w.lower() for w in quality.warnings)


def test_assess_quality_blank_image_is_unusable():
    quality = assess_quality("img1", make_blank_image())
    assert quality.usable is False
    assert any("blank" in w.lower() for w in quality.warnings)


def test_assess_quality_low_resolution_gets_a_warning_but_stays_usable():
    quality = assess_quality("img1", make_synthetic_fabric_image(size=(250, 250)))
    assert quality.usable is True
    assert any("low resolution" in w.lower() for w in quality.warnings)


def test_average_hash_identical_images_hamming_distance_zero():
    data = make_synthetic_fabric_image()
    h1 = average_hash(decode_image(data))
    h2 = average_hash(decode_image(data))
    assert hamming_distance(h1, h2) == 0


def test_average_hash_different_images_are_far_apart():
    h1 = average_hash(decode_image(make_synthetic_fabric_image(background=(120, 20, 60))))
    h2 = average_hash(decode_image(make_synthetic_fabric_image(background=(20, 200, 30), accent=None)))
    assert hamming_distance(h1, h2) > 5


def test_detect_duplicates_flags_exact_repeats_but_not_originals():
    data_a = make_synthetic_fabric_image(background=(120, 20, 60))
    data_b = make_synthetic_fabric_image(background=(20, 200, 30), accent=None)
    hashes = {
        "a1": average_hash(decode_image(data_a)),
        "a2": average_hash(decode_image(data_a)),  # exact repeat of a1
        "b1": average_hash(decode_image(data_b)),
    }
    result = detect_duplicates(hashes)
    assert result["a1"] is None
    assert result["a2"] == "a1"
    assert result["b1"] is None
