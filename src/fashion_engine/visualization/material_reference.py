"""prepare_fabric_reference: Phase 4.1, Stage 1 (sections 3-6). Turns the
selected Phase 3 fabric photographs into a clean, reusable
`FabricMaterialReference` -- deterministically wherever possible (section
4). The actual photograph is the strongest evidence of the fabric; this
stage normalizes/orients/resizes it, it does not reinterpret or "beautify"
it in a way that could change its identity. Generative cleanup is
deliberately NOT the default path.

Never forces a fabric into a seamless tile (section 6) -- every reference
here is a `SURFACE_REFERENCE`; `TILEABLE_REFERENCE` exists in the domain
model as an explicit opt-in for a future case that actually needs one."""
from __future__ import annotations

import io

from PIL import Image, ImageOps

from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.domain.models.visualization import (
    FabricMaterialReference,
    FabricReferenceSelection,
    FabricSurfaceReference,
)
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store, new_image_id
from src.fashion_engine.visualization.spec_builder import material_fabric_summary

_MAX_DIMENSION = 2048  # normalize resolution -- never upscale, only cap runaway-large originals


def _normalize(image_bytes: bytes) -> tuple[bytes, str] | None:
    """Deterministic prep only: auto-orient via EXIF, cap resolution, and
    re-encode to a consistent format. Never raises -- an image that can't
    be decoded is simply not usable as a reference (section 34's "invalid
    reference image")."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except Exception:
        return None

    width, height = image.size
    if max(width, height) > _MAX_DIMENSION:
        scale = _MAX_DIMENSION / max(width, height)
        image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), "image/jpeg"


def prepare_fabric_reference(
    image_analysis: FabricImageAnalysisResult,
    fabric_images: list[UploadedFabricImage],
    selection: FabricReferenceSelection,
) -> FabricMaterialReference:
    """`selection` is computed once by the caller (`reference_selector.
    select_fabric_references`) and shared with spec-building, rather than
    recomputed here -- the same convention the one-shot Phase 4 pipeline
    already uses."""
    bytes_by_id = {img.image_id: img for img in fabric_images}
    store = get_visualization_asset_store()

    references: list[FabricSurfaceReference] = []
    warnings: list[str] = []
    for selected in selection.selected:
        upload = bytes_by_id.get(selected.image_id)
        if upload is None:
            continue
        normalized = _normalize(upload.data)
        if normalized is None:
            warnings.append(f"{selected.image_id}: could not be prepared as a material reference -- skipped.")
            continue
        data, content_type = normalized
        image_id = new_image_id()
        asset_uri = store.save(image_id, data, content_type)
        references.append(
            FabricSurfaceReference(
                role=selected.role,
                asset_id=asset_uri,
                source_image_id=selected.image_id,
                generated=False,
            )
        )

    return FabricMaterialReference(
        id=new_image_id(),
        references=references,
        fabric_summary=material_fabric_summary(image_analysis),
        warnings=warnings,
    )
