"""ConversationProvider: Phase 5's turn-decision boundary (product brief
section 26-28). Mirrors the established pattern in this codebase (`
src/providers/llm.py`, `src/providers/design_generation.py`): one narrow
abstract contract, a deterministic Mock default that needs no network call,
and a live implementation gated by `AGENT_ENABLED`.

Tool-calling mechanism: reuses the PROVEN `response_format: json_schema`
structured-output pattern `OpenAICompatibleDesignGenerationProvider` already
uses successfully against this account's endpoint, rather than real OpenAI
`tools=[...]` function-calling (unverified on this account, and every other
provider in this codebase already needed its own account-specific deviation
from generic vendor docs -- see `docs/vision-engine.md`/
`docs/visualization-engine.md`). The model emits ONE structured
`TurnDecision` per loop iteration; the orchestrator (`src/agent/loop.py`),
not the model, decides whether to keep looping.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from src.agent.intent import classify_intent
from src.agent.mock_brain import extract_count, extract_design_change, extract_visualization_targets
from src.agent.models import TurnContext, TurnDecision, TurnToolCall
from src.agent.reference_resolution import resolve_design_selection
from src.agent.tool_registry import list_tools
from src.providers.settings import get_settings

logger = logging.getLogger(__name__)

_HTTP_CALL_TIMEOUT_S = 20
_RESPONSE_JSON_SCHEMA = TurnDecision.model_json_schema()


class ConversationProvider(ABC):
    @abstractmethod
    def decide(self, context: TurnContext) -> TurnDecision:
        """Never raises -- a provider failure degrades to a safe, done=True
        decision so the orchestration loop can always terminate cleanly."""


class MockConversationProvider(ConversationProvider):
    """Deterministic, immediate provider -- no network call. Delegates to
    the same rule-based classification/extraction helpers a live provider's
    output would otherwise be produced by, so all required test scenarios
    (product brief section 47) run end-to-end offline."""

    def decide(self, context: TurnContext) -> TurnDecision:
        session = context.session
        message = context.message
        intent = classify_intent(message, session, has_images=context.has_images)

        if intent == "FABRIC_ANALYSIS":
            return TurnDecision(
                intent=intent,
                tool_call=TurnToolCall(tool_name="analyze_fabric_image"),
                user_message_draft="Got it -- let me take a look at that fabric.",
            )

        if intent == "DESIGN_GENERATION":
            count = extract_count(message)
            return TurnDecision(
                intent=intent,
                tool_call=TurnToolCall(tool_name="generate_design_directions", arguments={"count": count}),
                user_message_draft=f"Here are {count} directions for this fabric.",
            )

        if intent == "DESIGN_SELECTION":
            family_id = resolve_design_selection(message, session.last_design_batch)
            return TurnDecision(
                intent=intent,
                selection_ref=family_id,
                user_message_draft="Got it, noted your pick." if family_id else "Which option did you mean?",
            )

        if intent == "DESIGN_MODIFICATION":
            change = extract_design_change(message)
            tool_call = TurnToolCall(tool_name="apply_design_change", arguments=change) if change else None
            draft = (
                "Updating that now."
                if tool_call
                else "I didn't catch a specific change to make -- could you say which attribute and value?"
            )
            return TurnDecision(intent=intent, tool_call=tool_call, user_message_draft=draft)

        if intent == "VISUALIZATION_REQUEST":
            targets = extract_visualization_targets(message, session)
            done_targets = {
                d.tool_call.arguments.get("family_id")
                for d in context.prior_decisions
                if d.tool_call is not None and d.tool_call.tool_name == "visualize_design"
            }
            remaining = [t for t in targets if t not in done_targets]
            if not remaining:
                return TurnDecision(intent=intent, done=True, user_message_draft="Here you go.")
            next_target = remaining[0]
            return TurnDecision(
                intent=intent,
                tool_call=TurnToolCall(tool_name="visualize_design", arguments={"family_id": next_target}),
                done=len(remaining) == 1,
                user_message_draft="Rendering that now.",
            )

        if intent == "UNDO":
            return TurnDecision(intent=intent, user_message_draft="Undone -- back to the previous version.")

        if intent == "REDO":
            return TurnDecision(intent=intent, user_message_draft="Redone.")

        if intent == "RESET":
            draft = "Starting fresh -- previous designs are still on file if you want them."
            return TurnDecision(intent=intent, user_message_draft=draft)

        return TurnDecision(intent=intent, user_message_draft="Noted.")


def _state_summary(session) -> str:
    families = list(session.designs.keys())
    return (
        f"fabric_on_file={bool(session.fabric_refs)}; design_families={families}; "
        f"selected_design={session.selected_design_family_id}; "
        f"current_versions={session.current_version_id}; "
        f"visualization_count={len(session.visualizations)}"
    )


def _tool_menu() -> str:
    lines = [f"- {t.name} (cost={t.cost_class}, mutates={t.mutates_state}): {t.description}" for t in list_tools()]
    return "\n".join(lines)


_SYSTEM_PROMPT_TEMPLATE = (
    "You are an AI co-designer for an Indian fashion boutique. You orchestrate the registered tools below -- "
    "you never invent fabric properties, design facts, or trend/designer claims yourself. Respond with ONLY a "
    "single JSON object matching the given schema, no prose outside the JSON.\n\n"
    "Registered tools (call by exact name only -- no other tool exists):\n{tools}\n\n"
    "Cost policy: LOW/MEDIUM tools may be called whenever useful. HIGH-cost tools (visualization) may ONLY be "
    "called when the user has explicitly asked to see/render/visualize something -- never automatically after "
    "generating or modifying a design.\n\n"
    "Current session state: {state}\n"
)


class OpenAICompatibleConversationProvider(ConversationProvider):
    """Talks to the same OpenAI-compatible /chat/completions endpoint as
    every other live provider in this kernel (`LLM_BASE_URL`/`LLM_MODEL`/
    `LLM_API_KEY`) using `response_format: json_schema` -- never a new LLM
    vendor, never real function-calling (see module docstring)."""

    def decide(self, context: TurnContext) -> TurnDecision:
        settings = get_settings()
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            tools=_tool_menu(), state=_state_summary(context.session)
        )
        transcript_lines = [f"USER: {context.message}"]
        for prior in context.prior_decisions:
            transcript_lines.append(f"PRIOR_DECISION: {prior.model_dump_json()}")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(transcript_lines)},
        ]
        try:
            response = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": settings.agent_max_tokens,
                    "enable_thinking": settings.agent_thinking,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "turn_decision", "schema": _RESPONSE_JSON_SCHEMA, "strict": True},
                    },
                },
                timeout=_HTTP_CALL_TIMEOUT_S,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return TurnDecision(**parsed)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Conversation provider call failed: %s", exc)
            return TurnDecision(
                intent="QUESTION",
                done=True,
                user_message_draft="I ran into a problem understanding that -- could you rephrase?",
            )


def get_conversation_provider() -> ConversationProvider:
    settings = get_settings()
    mode = (settings.agent_provider or "auto").strip().lower()

    if mode == "mock":
        return MockConversationProvider()
    if mode in ("live", "openai_compatible", "alibaba", "aliyun", "dashscope"):
        return OpenAICompatibleConversationProvider()

    # "auto" (default): agent_enabled must be explicitly on before this
    # branch will ever select the live provider -- matches the
    # enabled-before-credential-presence convention every other provider
    # factory in this kernel follows.
    if not settings.agent_enabled:
        return MockConversationProvider()
    return OpenAICompatibleConversationProvider()