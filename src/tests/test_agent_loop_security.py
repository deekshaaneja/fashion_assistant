"""Security: the orchestration loop may only ever dispatch a tool that is a
key in `TOOL_REGISTRY` -- an unregistered/hallucinated tool name in a
`TurnDecision` must be rejected, never dispatched (product brief section
6/44)."""
from __future__ import annotations

import pytest

from src.agent import loop as loop_module
from src.agent.loop import run_turn
from src.agent.models import TurnDecision, TurnToolCall
from src.domain.models.session import DesignSession
from src.providers.settings import get_settings


@pytest.fixture(autouse=True)
def _deterministic_providers(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("DESIGN_GENERATION_PROVIDER", "template")
    monkeypatch.setenv("VISUALIZATION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _MaliciousProvider:
    """Simulates a compromised/hallucinating model output -- a tool name
    that was never registered."""

    def decide(self, context):
        return TurnDecision(
            intent="QUESTION",
            tool_call=TurnToolCall(tool_name="run_shell_command", arguments={"cmd": "rm -rf /"}),
            done=True,
        )


def test_unregistered_tool_call_is_rejected_never_dispatched(monkeypatch):
    monkeypatch.setattr(loop_module, "get_conversation_provider", lambda: _MaliciousProvider())
    session = DesignSession()

    result = run_turn(session, "anything", persist=False)

    assert "can't do that" in result.message.lower()
    assert result.artifacts == []
    # nothing was mutated on the session as a side effect of the rejected call
    assert session.designs == {}
    assert session.visualizations == []


def test_tool_registry_get_tool_returns_none_for_unregistered_names():
    from src.agent.tool_registry import get_tool

    assert get_tool("run_shell_command") is None
    assert get_tool("read_file") is None
    assert get_tool("") is None