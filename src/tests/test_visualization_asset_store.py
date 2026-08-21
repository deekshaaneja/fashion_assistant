from __future__ import annotations

import pytest

from src.fashion_engine.visualization.asset_store import FilesystemVisualizationAssetStore, new_image_id


def test_save_and_read_roundtrip(tmp_path):
    store = FilesystemVisualizationAssetStore(base_dir=str(tmp_path))
    image_id = new_image_id()
    uri = store.save(image_id, b"fake-png-bytes", "image/png")
    assert uri == f"visualizations/{image_id}.png"
    assert store.read(uri) == b"fake-png-bytes"


def test_save_picks_extension_from_content_type(tmp_path):
    store = FilesystemVisualizationAssetStore(base_dir=str(tmp_path))
    uri = store.save("abc", b"data", "image/jpeg")
    assert uri.endswith(".jpg")


def test_read_missing_asset_raises_file_not_found(tmp_path):
    store = FilesystemVisualizationAssetStore(base_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        store.read("visualizations/does-not-exist.png")


def test_store_never_exposes_raw_absolute_path_in_uri(tmp_path):
    store = FilesystemVisualizationAssetStore(base_dir=str(tmp_path))
    uri = store.save("abc", b"data", "image/png")
    assert str(tmp_path) not in uri
    assert uri.startswith("visualizations/")


def test_new_image_id_is_unique():
    assert new_image_id() != new_image_id()
