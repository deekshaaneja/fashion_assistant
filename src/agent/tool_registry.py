"""Tool registry: Phase 5's fixed catalog of orchestrator-invokable
capabilities (product brief sections 4-5) -- every one of Phase 1-4's
existing `src.tools.*` functions, plus the one Phase-5-only synthetic tool
(`apply_design_change`, section 9) that composes them. This is the ONLY
place the orchestration loop is allowed to invoke a tool from: a name that
is not a key in `TOOL_REGISTRY` is never dispatched (section 44/6's
security requirement -- the LLM may only invoke registered tools, and the
tool set is fixed, never dynamically generated from model output).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from src.agent.design_changes import apply_design_change
from src.tools.analyze_fabric import analyze_fabric
from src.tools.analyze_fabric_image import analyze_fabric_image
from src.tools.calculate_consumption import calculate_consumption
from src.tools.check_fabric_feasibility import check_fabric_feasibility
from src.tools.design_ensemble import design_ensemble
from src.tools.generate_colorways import generate_colorways
from src.tools.generate_design_colorways import generate_design_colorways
from src.tools.generate_design_directions import generate_design_directions
from src.tools.recommend_decoration import recommend_decoration
from src.tools.recommend_dupatta import recommend_dupatta
from src.tools.recommend_fabrics import recommend_fabrics
from src.tools.recommend_neckline import recommend_neckline
from src.tools.recommend_proportions import recommend_proportions
from src.tools.recommend_silhouettes import recommend_silhouettes
from src.tools.recommend_sleeves import recommend_sleeves
from src.tools.recommend_styling import recommend_styling
from src.tools.visualize_design import visualize_design

CostClass = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable
    description: str
    cost_class: CostClass
    mutates_state: bool


_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "recommend_silhouettes", recommend_silhouettes,
        "Given a fabric, rank which garment/silhouette combinations suit it.", "LOW", False,
    ),
    ToolSpec(
        "recommend_fabrics", recommend_fabrics,
        "Given a silhouette, rank which fabrics suit it.", "LOW", False,
    ),
    ToolSpec(
        "recommend_styling", recommend_styling,
        "Full structured styling spec for a (garment, silhouette, fabric).", "LOW", False,
    ),
    ToolSpec(
        "calculate_consumption", calculate_consumption,
        "Estimate fabric yardage needed for a garment/silhouette/size.", "LOW", False,
    ),
    ToolSpec(
        "check_fabric_feasibility", check_fabric_feasibility,
        "Check whether the available fabric metres are enough for a garment.", "LOW", False,
    ),
    ToolSpec(
        "generate_colorways", generate_colorways,
        "Propose a single-palette main+supporting color story for a fabric.", "LOW", False,
    ),
    ToolSpec(
        "analyze_fabric", analyze_fabric,
        "Infer fabric properties from a text-declared observation (no photo).", "LOW", True,
    ),
    ToolSpec(
        "recommend_neckline", recommend_neckline,
        "Recommend a neckline for a fabric+silhouette.", "LOW", False,
    ),
    ToolSpec(
        "recommend_sleeves", recommend_sleeves,
        "Recommend a sleeve treatment for a fabric.", "LOW", False,
    ),
    ToolSpec(
        "recommend_dupatta", recommend_dupatta,
        "Recommend whether/how to include a dupatta.", "LOW", False,
    ),
    ToolSpec(
        "recommend_decoration", recommend_decoration,
        "Recommend a decoration/embellishment treatment for a fabric.", "LOW", False,
    ),
    ToolSpec(
        "recommend_proportions", recommend_proportions,
        "Recommend descriptive proportion decisions for a design.", "LOW", False,
    ),
    ToolSpec(
        "generate_design_colorways", generate_design_colorways,
        "Propose coordinated per-component color stories for an existing design.", "LOW", False,
    ),
    ToolSpec(
        "design_ensemble", design_ensemble,
        "Propose full-look components (blouse, jacket, etc.) for an existing design.", "LOW", False,
    ),
    ToolSpec(
        "analyze_fabric_image", analyze_fabric_image,
        "Analyze uploaded fabric photograph(s) into a structured fabric profile.", "MEDIUM", True,
    ),
    ToolSpec(
        "generate_design_directions", generate_design_directions,
        "Generate one or more validated, ranked DesignProposals for a fabric.", "MEDIUM", True,
    ),
    ToolSpec(
        "apply_design_change", apply_design_change,
        "Apply one structured component change to a design version, producing a new immutable version.",
        "LOW", True,
    ),
    ToolSpec(
        "visualize_design", visualize_design,
        "Render a fabric-preserving concept image of one specific DesignProposal version. Expensive -- "
        "only call when the user explicitly asks to see/render/visualize a design.",
        "HIGH", True,
    ),
)

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _SPECS}


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())
