"""run_turn: Phase 5's bounded orchestration loop (product brief section
28). Each iteration asks the current `ConversationProvider` for ONE
`TurnDecision`, dispatches at most one tool call through the fixed
`TOOL_REGISTRY` (never any other code path), commits the resulting session
mutation only after the tool call succeeds (section 43 -- a failure never
corrupts already-committed state), and stops after
`AGENT_MAX_TOOL_CALLS_PER_TURN` iterations or when the provider signals
`done`. This module never reimplements Phase 1-4 logic -- it only sequences
and merges the existing tools' own results into `DesignSession`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.agent.brief_extraction import apply_brief_signals
from src.agent.cost_policy import is_auto_allowed, max_tool_calls_per_turn
from src.agent.design_changes import apply_design_change, register_design_proposal
from src.agent.models import TurnContext
from src.agent.session_store import get_session_store
from src.agent.tool_registry import get_tool
from src.domain.models.fabric_vision import ImageRole
from src.domain.models.session import (
    DesignChange,
    DesignSession,
    FabricRef,
    StoredImageRef,
    active_fabric_ref,
    current_node,
    new_id,
)
from src.domain.models.visualization import VisualizationOptions
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage
from src.fashion_engine.visualization.asset_store import get_visualization_asset_store, new_image_id
from src.providers.agent import get_conversation_provider

logger = logging.getLogger(__name__)


@dataclass
class DispatchOutcome:
    ok: bool
    error: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TurnResult:
    session: DesignSession
    message: str
    artifacts: list[dict[str, Any]]
    current_design_version: str | None
    turn_id: str


def _apply_undo(session: DesignSession) -> str | None:
    family_id = session.selected_design_family_id
    if family_id is None:
        return "There's no selected design to undo."
    node = current_node(session, family_id)
    if node is None or node.parent_version_id is None:
        return "Already at the earliest version -- nothing to undo."
    session.redo_hint[family_id] = node.version_id
    session.current_version_id[family_id] = node.parent_version_id
    return None


def _apply_redo(session: DesignSession) -> str | None:
    family_id = session.selected_design_family_id
    if family_id is None:
        return "There's no selected design to redo."
    hint = session.redo_hint.get(family_id)
    if hint is None:
        return "Nothing to redo."
    session.current_version_id[family_id] = hint
    del session.redo_hint[family_id]
    return None


def _dispatch_analyze_fabric_image(session: DesignSession, images: list[UploadedFabricImage]) -> DispatchOutcome:
    if not images:
        return DispatchOutcome(ok=False, error="No fabric image was attached to analyze.")
    spec = get_tool("analyze_fabric_image")
    result = spec.fn(images)
    if result.generation_metadata.provider_error_code:
        error = result.generation_metadata.provider_error or "fabric analysis failed"
        return DispatchOutcome(ok=False, error=error)

    store = get_visualization_asset_store()
    stored_images = [
        StoredImageRef(uri=store.save(new_image_id(), img.data, img.content_type), content_type=img.content_type)
        for img in images
    ]
    analysis_id = new_id("analysis")
    fabric_ref = FabricRef(
        fabric_id=new_id("fabric"),
        fabric_name=result.fabric_profile.fabric_name,
        declared_properties=result.fabric_profile.properties,
        source="image_analyzed",
        image_analysis_id=analysis_id,
        source_images=stored_images,
    )
    session.fabric_image_analyses[analysis_id] = result
    session.fabric_refs.append(fabric_ref)
    return DispatchOutcome(ok=True)


def _dispatch_generate_design_directions(
    session: DesignSession, arguments: dict[str, Any], turn_id: str
) -> DispatchOutcome:
    fabric_ref = active_fabric_ref(session)
    if fabric_ref is None:
        return DispatchOutcome(ok=False, error="No fabric on file yet -- analyze or declare one first.")
    spec = get_tool("generate_design_directions")
    count = int(arguments.get("count", 3))
    result = spec.fn(
        fabric_ref.fabric_name,
        fabric_ref.declared_properties,
        session.fashion_context,
        session.client_brief,
        count=count,
    )
    if not result.designs:
        error = result.generation_metadata.provider_error or "no valid design directions were generated"
        return DispatchOutcome(ok=False, error=error)

    nodes = [register_design_proposal(session, proposal, turn_id) for proposal in result.designs]
    session.last_design_batch = [node.design_family_id for node in nodes]
    artifacts = [
        {"kind": "design_version", "id": node.version_id, "design_family_id": node.design_family_id}
        for node in nodes
    ]
    return DispatchOutcome(ok=True, artifacts=artifacts)


def _dispatch_apply_design_change(
    session: DesignSession, arguments: dict[str, Any], turn_id: str
) -> DispatchOutcome:
    family_id = session.selected_design_family_id
    if family_id is None:
        return DispatchOutcome(ok=False, error="No design is currently selected to modify.")
    base = current_node(session, family_id)
    if base is None:
        return DispatchOutcome(ok=False, error="Selected design has no current version.")
    try:
        change = DesignChange(
            base_version_id=base.version_id,
            component=arguments["component"],
            operation=arguments["operation"],
            value=arguments.get("value", {}),
        )
    except (KeyError, ValueError) as exc:  # malformed change -- reject, never guess
        return DispatchOutcome(ok=False, error=f"Could not build a valid design change: {exc}")

    result = apply_design_change(session, change, turn_id)
    if not result.ok:
        return DispatchOutcome(ok=False, error="; ".join(result.rejection_issues) or "change rejected")
    node = result.new_version
    return DispatchOutcome(
        ok=True,
        artifacts=[{"kind": "design_version", "id": node.version_id, "design_family_id": node.design_family_id}],
    )


def _dispatch_visualize_design(session: DesignSession, arguments: dict[str, Any]) -> DispatchOutcome:
    family_id = arguments.get("family_id") or session.selected_design_family_id
    if family_id is None:
        return DispatchOutcome(ok=False, error="No design selected to visualize.")
    node = current_node(session, family_id)
    if node is None:
        return DispatchOutcome(ok=False, error="Selected design has no current version.")

    fabric_ref = active_fabric_ref(session)
    if fabric_ref is None or fabric_ref.source != "image_analyzed" or not fabric_ref.source_images:
        error = "Visualization needs a fabric photo on file -- none was analyzed yet."
        return DispatchOutcome(ok=False, error=error)
    image_analysis = session.fabric_image_analyses.get(fabric_ref.image_analysis_id or "")
    if image_analysis is None:
        return DispatchOutcome(ok=False, error="Original fabric analysis is no longer on file.")

    store = get_visualization_asset_store()
    fabric_images = [
        UploadedFabricImage(
            image_id=new_id("img"), data=store.read(ref.uri), content_type=ref.content_type, role=ImageRole.UNKNOWN
        )
        for ref in fabric_ref.source_images
    ]

    spec = get_tool("visualize_design")
    result = spec.fn(node.proposal, image_analysis, fabric_images, VisualizationOptions())
    if not result.images:
        error = result.generation_metadata.provider_error or "visualization did not produce an image"
        return DispatchOutcome(ok=False, error=error)

    session.visualizations.append(result)
    return DispatchOutcome(
        ok=True, artifacts=[{"kind": "visualization", "id": result.id, "design_family_id": family_id}]
    )


def _dispatch(
    session: DesignSession,
    tool_name: str,
    arguments: dict[str, Any],
    images: list[UploadedFabricImage],
    turn_id: str,
) -> DispatchOutcome:
    if tool_name == "analyze_fabric_image":
        return _dispatch_analyze_fabric_image(session, images)
    if tool_name == "generate_design_directions":
        return _dispatch_generate_design_directions(session, arguments, turn_id)
    if tool_name == "apply_design_change":
        return _dispatch_apply_design_change(session, arguments, turn_id)
    if tool_name == "visualize_design":
        return _dispatch_visualize_design(session, arguments)
    return DispatchOutcome(ok=False, error=f"'{tool_name}' is not orchestrated by the conversational loop yet.")


def run_turn(
    session: DesignSession,
    message: str,
    images: list[UploadedFabricImage] | None = None,
    persist: bool = True,
) -> TurnResult:
    images = images or []
    turn_id = new_id("turn")
    apply_brief_signals(session, message)

    provider = get_conversation_provider()
    prior_decisions: list = []
    response_parts: list[str] = []
    artifacts: list[dict[str, Any]] = []

    for _ in range(max_tool_calls_per_turn()):
        context = TurnContext(
            message=message, has_images=bool(images), session=session, prior_decisions=prior_decisions
        )
        decision = provider.decide(context)
        prior_decisions.append(decision)
        session.conversation_state.last_intent = decision.intent

        note: str | None = None
        if decision.intent == "DESIGN_SELECTION" and decision.selection_ref:
            if decision.selection_ref in session.designs:
                session.selected_design_family_id = decision.selection_ref
        elif decision.intent == "UNDO":
            note = _apply_undo(session)
        elif decision.intent == "REDO":
            note = _apply_redo(session)
        elif decision.intent == "RESET":
            session.selected_design_family_id = None

        if note:
            response_parts.append(note)
            break

        if decision.tool_call is None:
            if decision.user_message_draft:
                response_parts.append(decision.user_message_draft)
            break

        spec = get_tool(decision.tool_call.tool_name)
        if spec is None:
            logger.warning("agent loop: rejected call to unregistered tool '%s'", decision.tool_call.tool_name)
            response_parts.append("I can't do that.")
            break

        explicit_request = decision.intent == "VISUALIZATION_REQUEST"
        if not is_auto_allowed(spec, explicit_request):
            response_parts.append("I'd only do that with an explicit request to visualize.")
            break

        outcome = _dispatch(session, spec.name, decision.tool_call.arguments, images, turn_id)
        if not outcome.ok:
            response_parts.append(outcome.error or f"{spec.name} did not succeed.")
            break

        if persist:
            get_session_store().save(session)
        artifacts.extend(outcome.artifacts)
        if decision.user_message_draft:
            response_parts.append(decision.user_message_draft)

        if decision.done:
            break

    session.conversation_state.turn_count += 1
    session.updated_at = datetime.now(timezone.utc)
    if persist:
        get_session_store().save(session)

    current_version = (
        session.current_version_id.get(session.selected_design_family_id)
        if session.selected_design_family_id
        else None
    )
    message_out = " ".join(part for part in response_parts if part) or "Okay."
    return TurnResult(
        session=session,
        message=message_out,
        artifacts=artifacts,
        current_design_version=current_version,
        turn_id=turn_id,
    )
