"""Orchestration-protocol shapes for Phase 5's turn loop -- NOT domain facts
about fashion (those stay in `src/domain/models/session.py`), so they live
here rather than under `src/domain/models/`. `TurnDecision` is the single
structured object a `ConversationProvider` emits per loop iteration (product
brief section 27-28): at most ONE tool call per decision -- "show me all
three" is handled by the orchestrator looping, never by a decision
containing several calls at once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.models.session import DesignSession, IntentType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TurnToolCall(_StrictModel):
    tool_name: str
    arguments: dict[str, Any] = {}


class TurnDecision(_StrictModel):
    intent: IntentType
    tool_call: TurnToolCall | None = None
    selection_ref: str | None = None
    done: bool = True
    user_message_draft: str = ""


@dataclass
class TurnContext:
    message: str
    has_images: bool
    session: DesignSession
    prior_decisions: list[TurnDecision] = field(default_factory=list)
