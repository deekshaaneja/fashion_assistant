from __future__ import annotations

from src.agent.cost_policy import is_auto_allowed, max_tool_calls_per_turn
from src.agent.tool_registry import get_tool
from src.providers.settings import get_settings


def test_low_and_medium_tools_are_always_allowed():
    low = get_tool("recommend_silhouettes")
    medium = get_tool("generate_design_directions")
    assert is_auto_allowed(low, explicit_request=False) is True
    assert is_auto_allowed(medium, explicit_request=False) is True


def test_high_cost_tool_requires_explicit_request():
    high = get_tool("visualize_design")
    assert is_auto_allowed(high, explicit_request=False) is False
    assert is_auto_allowed(high, explicit_request=True) is True


def test_default_budget_is_five(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_TOOL_CALLS_PER_TURN", raising=False)
    get_settings.cache_clear()
    assert max_tool_calls_per_turn() == 5
    get_settings.cache_clear()


def test_budget_is_configurable(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS_PER_TURN", "2")
    get_settings.cache_clear()
    assert max_tool_calls_per_turn() == 2
    get_settings.cache_clear()
