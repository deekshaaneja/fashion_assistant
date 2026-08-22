from __future__ import annotations

import pytest

from src.agent.tool_registry import TOOL_REGISTRY, get_tool, list_tools

_EXPECTED = {
    "recommend_silhouettes": ("LOW", False),
    "recommend_fabrics": ("LOW", False),
    "recommend_styling": ("LOW", False),
    "calculate_consumption": ("LOW", False),
    "check_fabric_feasibility": ("LOW", False),
    "generate_colorways": ("LOW", False),
    "analyze_fabric": ("LOW", True),
    "recommend_neckline": ("LOW", False),
    "recommend_sleeves": ("LOW", False),
    "recommend_dupatta": ("LOW", False),
    "recommend_decoration": ("LOW", False),
    "recommend_proportions": ("LOW", False),
    "generate_design_colorways": ("LOW", False),
    "design_ensemble": ("LOW", False),
    "analyze_fabric_image": ("MEDIUM", True),
    "generate_design_directions": ("MEDIUM", True),
    "apply_design_change": ("LOW", True),
    "visualize_design": ("HIGH", True),
}


def test_registry_contains_exactly_the_expected_tools():
    assert set(TOOL_REGISTRY.keys()) == set(_EXPECTED.keys())


@pytest.mark.parametrize("name,expected", list(_EXPECTED.items()))
def test_cost_class_and_mutates_state_match_the_declared_table(name, expected):
    spec = get_tool(name)
    assert spec is not None
    assert (spec.cost_class, spec.mutates_state) == expected


def test_visualize_design_is_the_only_high_cost_tool():
    high_cost = [t.name for t in list_tools() if t.cost_class == "HIGH"]
    assert high_cost == ["visualize_design"]


def test_unregistered_tool_name_is_not_found():
    assert get_tool("delete_everything") is None
    assert get_tool("run_shell_command") is None
