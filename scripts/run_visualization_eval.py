#!/usr/bin/env python3
"""Phase 4 anchor evaluation (sections 35-40, 51).

Runs the two required real-fabric anchors --

    eval_data/phase3/organza/*.jpeg   (Anchor A -- embroidered organza)
    eval_data/phase3/georgette/*.jpg  (Anchor B -- georgette)

end to end: real fabric photo(s) -> Phase 3 (blind inference) -> Phase 2
(one deliberately test-worthy design) -> Phase 4 visualization.

First attempts the LIVE `qwen-image-edit` provider (requires
VISUALIZATION_ENABLED=true and a working VISUALIZATION_*/LLM_API_KEY
config in .env) and reports exactly what came back -- per the Phase 4
report's Provider Evaluation section, this account's image-generation
models accept the request (validated reference-image count, HTTP 200) but
return no image payload, so this is expected to surface a structured
VISUALIZATION_OUTPUT_EMPTY failure, not a hang or a crash.

Then runs the SAME specification through the mock provider, clearly
labeled as a mechanical pipeline demonstration only -- never a substitute
for real visual acceptance evidence (mirrors Phase 3's
`MockFabricVisionProvider` honesty convention).

Run from the repo root:

    .venv/bin/python scripts/run_visualization_eval.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.domain.models.visualization import VisualizationOptions  # noqa: E402
from src.fashion_engine.fabric.vision_pipeline import (  # noqa: E402
    UploadedFabricImage,
    generate_design_directions_from_images,
)
from src.providers.settings import get_settings  # noqa: E402
from src.tools.visualize_design import visualize_design  # noqa: E402

EVAL_ROOT = REPO_ROOT / "eval_data" / "phase3"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Section 36-37: garment/silhouette deliberately chosen to exercise the
# properties each anchor is supposed to test, not just whatever Phase 1
# would auto-recommend.
_ANCHORS = {
    "organza": {
        "garment_id": "suit",
        "silhouette_id": "panelled",  # controlled construction -- crisp/structured fabric, embroidery, border
        "note": "structured/crisp fabric, embroidery, transparency, controlled silhouette, restrained decoration",
    },
    "georgette": {
        "garment_id": "suit",
        "silhouette_id": "anarkali",  # gathered construction -- needs fluid drape, lined body, dupatta
        "note": "fluid drape, flare, lined body, dupatta/layering",
    },
}


def _load_images(label: str) -> list[UploadedFabricImage]:
    folder = EVAL_ROOT / label
    paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS) if folder.exists() else []
    return [UploadedFabricImage(image_id=p.name, data=p.read_bytes()) for p in paths]


def _print_result(label: str, tag: str, result) -> None:
    meta = result.generation_metadata
    print(f"  [{tag}] provider={meta.provider} model={meta.model} strategy={meta.strategy}")
    print(f"  [{tag}] attempts={meta.attempts} timing_ms={meta.timing_ms}")
    if meta.provider_error:
        print(f"  [{tag}] PROVIDER ERROR: {meta.provider_error} ({meta.provider_error_code})")
    print(f"  [{tag}] images={[img.uri for img in result.images]}")
    print(f"  [{tag}] validation.overall={result.validation.overall}")
    for check in result.validation.checks:
        print(
            f"  [{tag}]   {check.category:7s} {check.name:22s} {check.verdict} "
            f"(conf={check.confidence}) -- {check.detail}"
        )
    if result.validation.warnings:
        print(f"  [{tag}] warnings={result.validation.warnings}")


def run_anchor(label: str) -> None:
    images = _load_images(label)
    if not images:
        print(f"=== {label}: no images found under {EVAL_ROOT / label} -- skipping ===")
        return

    anchor = _ANCHORS[label]
    print(f"\n=== Anchor {label} ({', '.join(i.image_id for i in images)}) ===")
    print(f"Testing: {anchor['note']}")

    design_result = generate_design_directions_from_images(
        images,
        selected_garment_id=anchor["garment_id"],
        selected_silhouette_id=anchor["silhouette_id"],
        count=1,
    )
    design = design_result.design_directions.designs[0]
    image_analysis = design_result.image_analysis
    identity_status = image_analysis.fabric_profile.identity_status
    print(f"Fabric: {image_analysis.fabric_profile.fabric_name} (identity_status={identity_status})")
    print(f"Design: {design.title} -- {design.design_intent[:160]}")
    print(
        f"  construction: {design.construction.bodice_style} / {design.construction.flare_level} "
        f"{design.construction.flare_construction} / {design.construction.garment_length}"
    )
    print(f"  neckline={design.neckline.type} sleeves={design.sleeves.length}/{design.sleeves.style}")
    print(f"  dupatta={design.dupatta.model_dump() if design.dupatta else None}")
    treatments = [t.material for t in design.decoration.treatments]
    print(f"  decoration={design.decoration.level} treatments={treatments}")

    options = VisualizationOptions()

    settings = get_settings()
    if settings.visualization_enabled:
        live_result = visualize_design(design, image_analysis, images, options)
        _print_result(label, "LIVE", live_result)
    else:
        print("  [LIVE] VISUALIZATION_ENABLED is false -- skipping live attempt.")

    os.environ["VISUALIZATION_PROVIDER"] = "mock"
    get_settings.cache_clear()
    try:
        mock_result = visualize_design(design, image_analysis, images, options)
    finally:
        os.environ.pop("VISUALIZATION_PROVIDER", None)
        get_settings.cache_clear()
    print("  [MOCK] mechanical pipeline demonstration only -- NOT real visual evidence:")
    _print_result(label, "MOCK", mock_result)


def main() -> int:
    print(
        "Phase 4 anchor evaluation -- organza and georgette, real Phase 3 photographs, "
        "blind design selection.\n"
    )
    for label in ("organza", "georgette"):
        run_anchor(label)
    print(
        "\nDone. Review the structured validation checks above for the qualitative rubric dimensions "
        "(fabric identity, color, surface, silhouette, construction, neckline, sleeves, length, bottom, "
        "dupatta, decoration, overall usefulness)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
