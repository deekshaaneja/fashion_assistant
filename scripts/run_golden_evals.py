#!/usr/bin/env python3
"""Standalone golden-scenario runner (section 18/25 Step 5-6).

Complements src/tests/ with a fast, human-readable pass/fail report for
representative fashion scenarios -- whether recommendations make sense, not
just whether functions execute. Run from the repo root:

    .venv/bin/python scripts/run_golden_evals.py

Exits non-zero if any case fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.domain.models.common import Range  # noqa: E402
from src.domain.models.context import RecommendationContext  # noqa: E402
from src.domain.models.fabric import FabricProperties  # noqa: E402
from src.fashion_engine.scoring.engine import evaluate_candidate  # noqa: E402
from src.rules.repository import (  # noqa: E402
    get_fabric_repository,
    get_garment_repository,
    get_silhouette_repository,
)
from src.tools.calculate_consumption import calculate_consumption  # noqa: E402
from src.tools.check_fabric_feasibility import check_fabric_feasibility  # noqa: E402
from src.tools.generate_colorways import generate_colorways  # noqa: E402
from src.tools.recommend_fabrics import recommend_fabrics  # noqa: E402
from src.tools.recommend_silhouettes import recommend_silhouettes  # noqa: E402
from src.tools.recommend_styling import recommend_styling  # noqa: E402


def _context_from(raw: dict | None) -> RecommendationContext:
    return RecommendationContext(**(raw or {}))


def _run_candidate_score_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    fabric = get_fabric_repository().resolve(inp["fabric_name"]).profile
    if inp.get("declared_properties"):
        from src.fashion_engine.fabric.analyze import merge_fabric_properties

        merged = merge_fabric_properties(fabric.properties, FabricProperties(**inp["declared_properties"]))
        fabric = fabric.model_copy(update={"properties": merged})
    garment = get_garment_repository().get(inp["garment_id"])
    silhouette = get_silhouette_repository().get(inp["silhouette_id"])
    context = _context_from(inp.get("context"))

    evaluation = evaluate_candidate(fabric, garment, silhouette, context)
    tier = evaluation.recommendation_classification

    results = []
    for check in case["checks"]:
        if check["type"] == "classification_in":
            ok = tier in check["expected"]
            results.append((ok, check["type"], f"classification={tier}, expected one of {check['expected']}"))
        elif check["type"] == "risk_mentions":
            ok = any(check["text"].lower() in r.lower() for r in evaluation.risks)
            results.append((ok, check["type"], f"risks={evaluation.risks}"))
        elif check["type"] == "reason_mentions":
            ok = any(check["text"].lower() in r.lower() for r in evaluation.reasons)
            results.append((ok, check["type"], f"reasons={evaluation.reasons}"))
        else:
            raise ValueError(f"Unknown check type for candidate_score: {check['type']}")
    return results


def _run_recommend_silhouettes_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    declared = FabricProperties(**inp["declared_properties"]) if inp.get("declared_properties") else None
    result = recommend_silhouettes(inp["fabric_name"], declared, _context_from(inp.get("context")))

    results = []
    for check in case["checks"]:
        if check["type"] == "top_classification_in":
            top_tier = result.candidates[0].recommendation_classification if result.candidates else None
            ok = bool(result.candidates) and top_tier in check["expected"]
            got = top_tier
            results.append((ok, check["type"], f"top classification={got}, expected one of {check['expected']}"))
        elif check["type"] == "top_garment_in":
            ok = bool(result.candidates) and result.candidates[0].garment.id in check["expected"]
            got = result.candidates[0].garment.id if result.candidates else None
            results.append((ok, check["type"], f"top garment={got}, expected one of {check['expected']}"))
        elif check["type"] == "silhouette_ranked_below_top":
            ranks = {c.silhouette.id: c.rank for c in result.candidates}
            target_rank = ranks.get(check["silhouette_id"])
            ok = target_rank is None or target_rank > 1
            results.append((ok, check["type"], f"{check['silhouette_id']} rank={target_rank}"))
        else:
            raise ValueError(f"Unknown check type for recommend_silhouettes: {check['type']}")
    return results


def _run_recommend_fabrics_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    result = recommend_fabrics(inp["silhouette_id"], inp.get("garment_id"), _context_from(inp.get("context")))

    results = []
    for check in case["checks"]:
        if check["type"] == "best_use_count_at_least":
            count = sum(1 for c in result.candidates if c.recommendation_classification == "BEST_USE")
            results.append((count >= check["count"], check["type"], f"BEST_USE count={count}"))
        elif check["type"] == "fabric_in_best_use":
            best_use_ids = {
                c.fabric.id for c in result.candidates if c.recommendation_classification == "BEST_USE"
            }
            ok = check["fabric_id"] in best_use_ids
            results.append((ok, check["type"], f"BEST_USE fabrics={best_use_ids}"))
        else:
            raise ValueError(f"Unknown check type for recommend_fabrics: {check['type']}")
    return results


def _run_consumption_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    estimate = calculate_consumption(**inp)

    results = []
    for check in case["checks"]:
        if check["type"] == "min_metres_between":
            ok = check["low"] <= estimate.min_metres <= check["high"]
            results.append((ok, check["type"], f"min_metres={estimate.min_metres}"))
        elif check["type"] == "min_less_than_max":
            results.append((estimate.min_metres < estimate.max_metres, check["type"], "range check"))
        else:
            raise ValueError(f"Unknown check type for calculate_consumption: {check['type']}")
    return results


def _run_feasibility_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    extra_kwargs = {k: v for k, v in inp.items() if k not in ("available_metres", "required_range")}
    result = check_fabric_feasibility(inp["available_metres"], Range(**inp["required_range"]), **extra_kwargs)

    results = []
    for check in case["checks"]:
        if check["type"] == "status_equals":
            results.append((result.status == check["expected"], check["type"], f"status={result.status}"))
        elif check["type"] == "redesign_options_at_least":
            ok = len(result.redesign_options) >= check["count"]
            results.append((ok, check["type"], f"redesign_options count={len(result.redesign_options)}"))
        else:
            raise ValueError(f"Unknown check type for check_fabric_feasibility: {check['type']}")
    return results


def _run_colorway_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    colorway = generate_colorways(inp["fabric_name"], inp.get("garment_id"), _context_from(inp.get("context")))

    results = []
    for check in case["checks"]:
        if check["type"] == "harmony_type_equals":
            ok = colorway.harmony_type == check["expected"]
            results.append((ok, check["type"], f"harmony={colorway.harmony_type}"))
        elif check["type"] == "has_metallic_accent":
            ok = len(colorway.metallic_accents) > 0
            results.append((ok, check["type"], f"metallic_accents={colorway.metallic_accents}"))
        else:
            raise ValueError(f"Unknown check type for generate_colorways: {check['type']}")
    return results


def _run_styling_case(case: dict) -> list[tuple[bool, str, str]]:
    inp = case["input"]
    spec = recommend_styling(
        inp["garment_id"], inp["silhouette_id"], inp["fabric_name"], _context_from(inp.get("context"))
    )

    results = []
    for check in case["checks"]:
        if check["type"] == "field_equals":
            got = getattr(spec, check["field"])
            results.append((got == check["expected"], check["type"], f"{check['field']}={got}"))
        elif check["type"] == "field_is_not_none":
            got = getattr(spec, check["field"])
            results.append((got is not None, check["type"], f"{check['field']}={got}"))
        elif check["type"] == "field_is_none":
            got = getattr(spec, check["field"])
            results.append((got is None, check["type"], f"{check['field']}={got}"))
        else:
            raise ValueError(f"Unknown check type for recommend_styling: {check['type']}")
    return results


_RUNNERS = {
    "candidate_score": _run_candidate_score_case,
    "recommend_silhouettes": _run_recommend_silhouettes_case,
    "recommend_fabrics": _run_recommend_fabrics_case,
    "calculate_consumption": _run_consumption_case,
    "check_fabric_feasibility": _run_feasibility_case,
    "generate_colorways": _run_colorway_case,
    "recommend_styling": _run_styling_case,
}


def main() -> int:
    cases = yaml.safe_load((REPO_ROOT / "data" / "golden" / "golden_cases.yaml").read_text())["cases"]

    total_checks = 0
    failed_checks = 0

    for case in cases:
        runner = _RUNNERS.get(case["tool"])
        if runner is None:
            raise ValueError(f"Unknown tool '{case['tool']}' in case '{case['name']}'")

        print(f"\n=== {case['name']} ({case['tool']}) ===")
        for ok, check_type, detail in runner(case):
            total_checks += 1
            status = "PASS" if ok else "FAIL"
            print(f"  {status} [{check_type}]: {detail}")
            if not ok:
                failed_checks += 1

    print(f"\n{total_checks - failed_checks}/{total_checks} checks passed across {len(cases)} golden cases.")
    return 1 if failed_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
