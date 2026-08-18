#!/usr/bin/env python3
"""Phase 3 BLIND evaluation harness (sections 39-44, 51).

Runs the REAL live vision provider against real fabric photographs under

    eval_data/phase3/{organza,georgette,difficult,negative}/*.jpg

Directory names are human-provided ground-truth labels for SCORING ONLY.
They are NEVER passed to the vision model as an inference hint --
`analyze_fabric_images` is always called with `fabric_name_hint=None` here,
so inference runs completely blind. Labels are compared against the result
only AFTER inference, in `_print_case_report` below.

Run from the repo root (requires VISION_ENABLED=true and a working
LLM_API_KEY/VISION_* config in .env -- this is the real qwen3-vl-plus
endpoint, not the mock provider):

    .venv/bin/python scripts/run_vision_eval.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.fashion_engine.fabric.vision_pipeline import (  # noqa: E402
    UploadedFabricImage,
    analyze_fabric_images,
    generate_design_directions_from_images,
    recommend_silhouettes_from_images,
)
from src.providers.settings import get_settings  # noqa: E402

EVAL_ROOT = REPO_ROOT / "eval_data" / "phase3"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Human ground truth, used ONLY for post-hoc scoring below -- never sent to
# the model.
_FAMILY_SYNONYMS = {
    "organza": {"organza", "tissue", "tissue organza", "crisp sheer", "sheer synthetic"},
    "georgette": {"georgette", "chiffon", "crepe georgette"},
}


def _discover_cases() -> dict[str, list[Path]]:
    cases: dict[str, list[Path]] = {}
    if not EVAL_ROOT.exists():
        return cases
    for sub in sorted(p for p in EVAL_ROOT.iterdir() if p.is_dir()):
        images = sorted(p for p in sub.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
        if images:
            cases[sub.name] = images
    return cases


def _load_images(paths: list[Path]) -> list[UploadedFabricImage]:
    return [UploadedFabricImage(image_id=p.name, data=p.read_bytes()) for p in paths]


def _family_match(label: str, inferred_family) -> bool | None:
    if label not in _FAMILY_SYNONYMS or not inferred_family:
        return None
    inferred = str(inferred_family).strip().lower()
    return any(s in inferred or inferred in s for s in _FAMILY_SYNONYMS[label])


def _print_case_report(label: str, image_paths: list[Path], elapsed_ms: float, result) -> None:
    meta = result.generation_metadata
    print(f"\n=== {label} ({', '.join(p.name for p in image_paths)}) ===")
    print(
        f"provider={meta.provider} model={meta.model} attempts={meta.attempts} "
        f"images_submitted={meta.images_submitted} duplicates_dropped={meta.duplicate_images_dropped}"
    )
    print(f"harness wall clock: {elapsed_ms}ms | provider_ms={meta.timing_ms.get('vision.provider_ms')}")
    print(f"tokens: input={meta.input_tokens} output={meta.output_tokens}")
    if meta.provider_error:
        print(f"PROVIDER ERROR: {meta.provider_error} ({meta.provider_error_code})")

    print(f"image_subject={result.analysis.image_subject} (confidence={result.analysis.subject_confidence})")
    for e in result.evidence:
        alt = f" alt={e.alternatives[0].value!r}" if e.alternatives else ""
        line = f"  [{e.evidence_type:14s}] {e.property:22s} = {e.value!r:>18} (conf={e.confidence}){alt}"
        print(f"{line} -- {e.reason}")
    if result.analysis.dominant_colors:
        print("  colors:", [(c.name, c.hex_estimate, c.role) for c in result.analysis.dominant_colors])
    if result.analysis.motifs:
        print("  motifs:", [(m.motif_type, m.placement, m.density) for m in result.analysis.motifs])
    if result.analysis.border:
        print("  border:", result.analysis.border.model_dump())
    if result.warnings:
        print("  warnings:", result.warnings)
    if result.analysis.suggested_additional_photos:
        print("  suggested additional photos:", result.analysis.suggested_additional_photos)

    # --- post-hoc scoring against the human label (never seen by the model) ---
    inferred_family = next((e.value for e in result.evidence if e.property == "fabric_family"), None)
    match = _family_match(label, inferred_family)
    if match is not None:
        verdict = "MATCH" if match else "MISMATCH"
        print(f"  SCORING: inferred family={inferred_family!r} vs. human label={label!r} -> {verdict}")
    if label == "negative":
        ok = result.analysis.image_subject != "fabric_swatch"
        print(f"  SCORING: correctly avoided a confident fabric profile -> {'PASS' if ok else 'FAIL'}")
    if label == "difficult":
        hedged = any(e.evidence_type == "unknown" for e in result.evidence) or bool(result.warnings)
        print(f"  SCORING: appropriately hedged on a poor-quality photo -> {'PASS' if hedged else 'FAIL'}")


def main() -> int:
    settings = get_settings()
    if not settings.vision_enabled:
        print("VISION_ENABLED is false -- set VISION_ENABLED=true in .env to run the real evaluation.")
        return 1

    cases = _discover_cases()
    if not cases:
        print(f"No evaluation images found under {EVAL_ROOT}.")
        print("Expected: eval_data/phase3/{organza,georgette,difficult,negative}/*.jpg")
        return 1

    print(f"Found {len(cases)} case(s): {list(cases)}")
    print("Running BLIND inference -- directory labels are never sent to the model.\n")

    loaded: dict[str, list[UploadedFabricImage]] = {}
    for label, paths in cases.items():
        images = _load_images(paths)
        loaded[label] = images
        t0 = time.monotonic()
        result = analyze_fabric_images(images)  # fabric_name_hint intentionally omitted -- blind inference
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        _print_case_report(label, paths, elapsed_ms, result)

    if "organza" in loaded:
        print("\n=== Phase 1 handoff (organza) ===")
        rec = recommend_silhouettes_from_images(loaded["organza"])
        for c in rec.silhouette_recommendation.candidates[:5]:
            print(f"  {c.garment.name} / {c.silhouette.name}: {c.recommendation_classification}")

        print("\n=== Phase 2 handoff (organza, template provider -- deterministic, no second live LLM call) ===")
        os.environ["DESIGN_GENERATION_PROVIDER"] = "template"
        get_settings.cache_clear()
        top = rec.silhouette_recommendation.candidates[0]
        design = generate_design_directions_from_images(
            loaded["organza"],
            selected_garment_id=top.garment.id,
            selected_silhouette_id=top.silhouette.id,
            count=1,
        )
        for d in design.design_directions.designs:
            print(f"  {d.title}: {d.design_intent[:160]}")

    print(
        "\nDone. Review the structured evidence above for the qualitative Phase 3 evaluation dimensions "
        "(visual correctness, textile-family usefulness, surface/color/structure understanding, appropriate "
        "uncertainty, downstream usefulness)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
