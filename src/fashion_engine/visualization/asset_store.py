"""VisualizationAssetStore: Phase 4, sections 27-28. Generated images need a
stable application reference -- unlike Phase 3's temporary analysis images,
Phase 4 output is the actual deliverable. A provider's own output URL (often
a short-lived signed URL) is NEVER the permanent identity; it is downloaded/
copied into this store first (section 28).

Filesystem storage for local development (section 27) -- kept behind a
narrow interface so a future cloud-backed store is a drop-in replacement,
never a reason to touch calling code."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from src.providers.settings import get_settings

_CONTENT_TYPE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class VisualizationAssetStore(ABC):
    @abstractmethod
    def save(self, image_id: str, data: bytes, content_type: str) -> str:
        """Persists the image and returns a stable, storable application
        reference (never a raw filesystem path exposed to a public API --
        section 34)."""

    @abstractmethod
    def read(self, uri: str) -> bytes:
        """Never raises for a missing/invalid uri caused by caller error --
        raises only `FileNotFoundError` for genuinely missing assets, so
        callers can distinguish "not found" from other failures."""


class FilesystemVisualizationAssetStore(VisualizationAssetStore):
    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir or get_settings().visualization_storage_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, image_id: str, data: bytes, content_type: str) -> str:
        ext = _CONTENT_TYPE_EXT.get(content_type, "bin")
        filename = f"{image_id}.{ext}"
        path = self._base_dir / filename
        path.write_bytes(data)
        # A stable, storage-internal reference -- never the raw absolute
        # filesystem path (section 34: don't expose internal paths through
        # a public API response).
        return f"visualizations/{filename}"

    def read(self, uri: str) -> bytes:
        filename = uri.rsplit("/", 1)[-1]
        path = self._base_dir / filename
        if not path.is_file():
            raise FileNotFoundError(uri)
        return path.read_bytes()


def new_image_id() -> str:
    return uuid.uuid4().hex


_store: VisualizationAssetStore | None = None


def get_visualization_asset_store() -> VisualizationAssetStore:
    global _store
    if _store is None:
        _store = FilesystemVisualizationAssetStore()
    return _store
