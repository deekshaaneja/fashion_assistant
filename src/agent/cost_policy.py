"""cost_policy: the single choke point enforcing LOW/MEDIUM/HIGH tool-call
policy (product brief section 6/29/57). LOW/MEDIUM tools may be called
whenever directly useful; a HIGH-cost tool (visualization) may only be
called on an explicit user request -- it must never auto-trigger after
design generation or modification.
"""
from __future__ import annotations

from src.agent.tool_registry import ToolSpec
from src.providers.settings import get_settings


def max_tool_calls_per_turn() -> int:
    return get_settings().agent_max_tool_calls_per_turn


def is_auto_allowed(spec: ToolSpec, explicit_request: bool) -> bool:
    if spec.cost_class == "HIGH":
        return explicit_request
    return True
