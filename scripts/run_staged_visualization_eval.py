#!/usr/bin/env python3
"""Phase 4.1 live staged-visualization acceptance (sections 39-40).

Runs ONE real organza fabric through the full staged pipeline (Stage 1
material reference -> Stage 2 base garment -> Stage 3 design
transformation), and -- only if that succeeds -- repeats once with
georgette. Uses the selected provider (fal.ai, `fal-ai/flux-pro/kontext`,
after the section 18 spike) via `VISUALIZATION_PROVIDER=fal` / `FAL_KEY`.

Prints each stage's output image path so it can be reviewed by a human
(section 26 -- automatic validation alone cannot certify "still looks like
the same fabric").

Run from the repo root:

    .venv/bin/python scripts/run_staged_visualization_eval.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DESIGN_GENERATION_PROVIDER", "template")
os.environ.setdefault("VISUALIZATION_PROVIDER", "fal")

from src.domain.models.visualization import VisualizationOptions  # noqa: E402
from src.fashion_engine.fabric.vision_pipeline import (  # noqa: E402
    UploadedFabricImage,
    generate_design_directions_from_images,
)
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store  # noqa: E402
from src.fashion_engine.visualization.staged_pipeline import run_staged_visualization  # noqa: E402
from src.providers.settings import get_settings  # noqa: E402

EVAL_ROOT = REPO_ROOT / "eval_data" / "phase3"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OUTPUT_DIR = REPO_ROOT / "artifacts" / "staged_eval"

_ANCHORS = {
    "organza": {"garment_id": "suit", "silhouette_id": "panelled"},
    "georgette": {"garment_id": "suit", "silhouette_id": "anarkali"},
}


def _load_images(label: str) -> list[UploadedFabricImage]:
    folder = EVAL_ROOT / label
    paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS) if folder.exists() else []
    return [UploadedFabricImage(image_id=p.name, data=p.read_bytes()) for p in paths]


def run_anchor(label: str) -> bool:
    images = _load_images(label)
    if not images:
        print(f"=== {label}: no images found -- skipping ===")
        return False

    anchor = _ANCHORS[label]
    print(f"\n=== Anchor {label} ({', '.join(i.image_id for i in images)}) ===")

    design_result = generate_design_directions_from_images(
        images, selected_garment_id=anchor["garment_id"], selected_silhouette_id=anchor["silhouette_id"], count=1
    )
    design = design_result.design_directions.designs[0]
    image_analysis = design_result.image_analysis
    print(f"Fabric: {image_analysis.fabric_profile.fabric_name}")
    print(f"Design: {design.title}")
    print(
        f"  silhouette={design.garment.silhouette.name} flare={design.construction.flare_level}/"
        f"{design.construction.flare_construction} neckline={design.neckline.type} "
        f"sleeves={design.sleeves.length}"
    )

    result = run_staged_visualization(design, image_analysis, images, VisualizationOptions())
    meta = result.generation_metadata
    print(f"  provider={meta.provider} strategy={meta.strategy} timing_ms={meta.timing_ms}")
    if meta.provider_error:
        print(f"  PROVIDER ERROR: {meta.provider_error} ({meta.provider_error_code})")
        return False

    store = get_visualization_asset_store()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for image in result.images:
        data = store.read(image.uri)
        ext = image.uri.rsplit(".", 1)[-1]
        out_path = OUTPUT_DIR / f"{label}_{image.stage}.{ext}"
        out_path.write_bytes(data)
        print(f"  [{image.stage}] saved for human review -> {out_path}")

    print(f"  validation.overall={result.validation.overall}")
    for check in result.validation.checks:
        print(f"    {check.category:7s} {check.name:22s} {check.verdict} -- {check.detail}")
    return True


def main() -> int:
    settings = get_settings()
    if not settings.fal_api_key:
        print("FAL_KEY is not configured -- set it in .env to run the live staged acceptance.")
        return 1

    print("Phase 4.1 live staged visualization acceptance -- organza first, georgette only if it succeeds.\n")
    organza_ok = run_anchor("organza")
    if organza_ok:
        run_anchor("georgette")
    else:
        print("\nOrganza did not succeed -- per section 40, not proceeding to georgette.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
