#!/usr/bin/env python3
"""Phase 2 golden design review (section 27) -- NOT an automated pass/fail
test. For each anchor fabric scenario, generates `count` design directions
via the real `generate_design_directions` pipeline (whatever
`DesignGenerationProvider` is configured -- live if `LLM_ENABLED=true`, the
deterministic template provider otherwise) and prints a human-readable
DESIGN 1/2/3 review block for manual evaluation, plus the validation report
(what was rejected and why) and generation metadata.

Run from the repo root:

    .venv/bin/python scripts/run_design_golden_review.py [--anchor A|B|both]

This is a genuinely slow script when the live provider is enabled (each
anchor can take several minutes) -- see docs/design-engine.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.domain.models.client_brief import ClientBrief  # noqa: E402
from src.domain.models.context import RecommendationContext  # noqa: E402
from src.domain.models.design_generation import DesignDirectionsResult  # noqa: E402
from src.domain.models.fabric import FabricProperties  # noqa: E402
from src.tools.generate_design_directions import generate_design_directions  # noqa: E402

ANCHORS = {
    "A": dict(
        fabric_name="embroidered korean organza",
        declared_properties=FabricProperties(
            drape="crisp",
            stiffness="stiff",
            structure="structured",
            transparency="sheer",
            sheen="high_sheen",
            stretch="none",
            embellishment_tolerance="low",
            surface_density="dense",
            border_available=True,
            motif_directional=True,
        ),
        fashion_context=RecommendationContext(
            occasion="engagement", wear_category_preference="indian", size="L", available_metres=4.0
        ),
        client_brief=ClientBrief(desired_aesthetic=["elegant", "contemporary"], occasion="engagement"),
    ),
    "B": dict(
        fabric_name="georgette",
        declared_properties=FabricProperties(
            drape="fluid",
            stiffness="soft",
            transparency="semi_sheer",
            sheen="matte",
            stretch="none",
            weight_class="light",
            structure="fluid",
            embellishment_tolerance="medium",
            surface_density="none",
        ),
        fashion_context=RecommendationContext(
            occasion="wedding_guest", wear_category_preference="indian", size="M"
        ),
        client_brief=ClientBrief(desired_aesthetic=["elegant", "contemporary"], occasion="wedding_guest"),
    ),
}


def _print_review(label: str, result: DesignDirectionsResult) -> None:
    print(f"\n{'=' * 70}\nANCHOR {label}\n{'=' * 70}")
    print(
        f"provider={result.generation_metadata.provider} "
        f"fallback_to_template={result.generation_metadata.fallback_to_template}"
    )
    print(
        f"generated={result.validation.candidates_generated} "
        f"accepted={result.validation.candidates_accepted} "
        f"diversity_rejections={result.validation.diversity_regenerations}"
    )
    if result.validation.candidates_rejected:
        print("REJECTED CANDIDATES:")
        for rejected in result.validation.candidates_rejected:
            print(f"  - {rejected.title}:")
            for reason in rejected.reasons:
                print(f"      {reason}")

    for design in result.designs:
        print(f"\nDESIGN {design.rank}")
        print(f"Title: {design.title}")
        print(f"Intent: {design.design_intent}")
        print(f"Garment/Silhouette: {design.garment.garment.name} / {design.garment.silhouette.name}")
        print(
            f"Construction: {design.construction.bodice_style} | panelling={design.construction.panelling} | "
            f"flare={design.construction.flare_level} ({design.construction.flare_construction}) | "
            f"length={design.construction.garment_length}"
        )
        print(f"Neckline: {design.neckline.type} (depth={design.neckline.depth})")
        print(f"Sleeve: {design.sleeves.length} / {design.sleeves.style} (sheer={design.sleeves.sheer})")
        if design.bottom:
            print(f"Bottom: {design.bottom.type}")
        if design.dupatta:
            print(f"Dupatta: included={design.dupatta.included} {design.dupatta.fabric_description or ''}")
        print(f"Palette: {design.palette.harmony_strategy if design.palette else 'n/a'}")
        print(f"Decoration: {design.decoration.level}")
        if design.fabric_usage.components:
            supporting = [c for c in design.fabric_usage.components if not c.use_main_fabric]
            if supporting:
                print(f"Supporting fabrics: {[c.fabric_description for c in supporting]}")
        print("Why it works:")
        for line in design.rationale:
            print(f"  - {line}")
        print("Risks:")
        for line in design.risks:
            print(f"  - {line}")
        print(f"Scores: overall={design.scores.overall} confidence={design.confidence.label}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", choices=["A", "B", "both"], default="both")
    parser.add_argument("--count", type=int, default=3)
    args = parser.parse_args()

    labels = ["A", "B"] if args.anchor == "both" else [args.anchor]
    for label in labels:
        anchor = ANCHORS[label]
        result = generate_design_directions(
            anchor["fabric_name"],
            anchor["declared_properties"],
            anchor["fashion_context"],
            anchor["client_brief"],
            count=args.count,
        )
        _print_review(label, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
