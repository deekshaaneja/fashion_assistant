"""DesignSession: Phase 5's structured session/state model (product brief
sections 7-13). The LLM conversation transcript is NEVER the state of
record -- every fact the orchestrator needs to act on comes from here.
Fabric/design/visualization facts are stored by reference or as the exact
existing Phase 1-4 domain models, never duplicated into a second parallel
representation.

Design versioning (section 8-9, 20): `DesignVersionNode` is one immutable
snapshot in a design's version tree. A `design_family_id` groups every
version/branch of "the same design" (D1); `session.designs[family_id]` is a
flat list of nodes each carrying its own `parent_version_id` -- a tree
encoded as a flat list with parent pointers, so branching (two children of
the same parent) needs no separate recursive structure. A version is never
mutated in place; a `DesignChange` always produces a NEW node.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from src.domain.models.client_brief import ClientBrief
from src.domain.models.common import DomainModel
from src.domain.models.context import RecommendationContext
from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.domain.models.visualization import VisualizationResult

IntentType = Literal[
    "FABRIC_ANALYSIS",
    "SILHOUETTE_RECOMMENDATION",
    "DESIGN_GENERATION",
    "DESIGN_SELECTION",
    "DESIGN_MODIFICATION",
    "DESIGN_COMPARISON",
    "COLORWAY_REQUEST",
    "DECORATION_REQUEST",
    "DUPATTA_REQUEST",
    "VISUALIZATION_REQUEST",
    "QUESTION",
    "CLARIFICATION",
    "UNDO",
    "REDO",
    "RESET",
]

DesignChangeComponent = Literal[
    "neckline", "sleeves", "construction", "bottom", "dupatta", "decoration", "design_dna"
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class StoredImageRef(DomainModel):
    """A pointer into the existing Phase 4 asset store -- raw image bytes
    never live inside session state itself (section 45: don't log/store
    image bytes in the session blob)."""

    uri: str
    content_type: str = "image/jpeg"


class FabricRef(DomainModel):
    """A fabric fact by reference, never duplicated in full into session
    state (section 7). `source_images` are the ORIGINAL uploaded photograph
    references -- every later visualization call reloads from here, never
    from a previously generated image (section 11, 15)."""

    fabric_id: str
    fabric_name: str
    declared_properties: FabricProperties | None = None
    source: Literal["text_declared", "image_analyzed"]
    image_analysis_id: str | None = None
    source_images: list[StoredImageRef] = Field(default_factory=list)


class DesignChange(DomainModel):
    """The ONLY shape a design modification is expressed in (section 9) --
    an agent proposes this typed object, never a raw DesignProposal patch
    applied blindly. `value` is validated against the target component's
    own Pydantic model before it is ever used (see
    `src/agent/design_changes.py`)."""

    base_version_id: str
    component: DesignChangeComponent
    operation: Literal["replace", "set"]
    value: dict[str, Any] = Field(default_factory=dict)


class DesignVersionNode(DomainModel):
    """One immutable snapshot in a design's version tree (section 8, 11)."""

    version_id: str
    design_family_id: str
    parent_version_id: str | None = None
    proposal: DesignProposal
    change: DesignChange | None = None
    root_risks: list[str] = Field(
        default_factory=list,
        description="the risks/notes captured once at V1 -- carried forward unchanged on every later "
        "modification so bookkeeping strings never re-accumulate across versions",
    )
    created_turn_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class DesignChangeResult(DomainModel):
    ok: bool
    new_version: DesignVersionNode | None = None
    rejection_issues: list[str] = Field(default_factory=list)


class ConversationState(DomainModel):
    """Structured pointers only (section 13) -- never a substitute for the
    transcript, and never relied on to reconstruct it either."""

    turn_count: int = 0
    last_intent: str | None = None
    pending_clarification: str | None = None


class DesignSession(DomainModel):
    session_id: str = Field(default_factory=lambda: new_id("session"))
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    fabric_refs: list[FabricRef] = Field(default_factory=list)
    fabric_image_analyses: dict[str, FabricImageAnalysisResult] = Field(default_factory=dict)

    client_brief: ClientBrief = Field(default_factory=ClientBrief)
    fashion_context: RecommendationContext = Field(default_factory=RecommendationContext)

    designs: dict[str, list[DesignVersionNode]] = Field(default_factory=dict)
    last_design_batch: list[str] = Field(
        default_factory=list,
        description="design_family_ids from the most recent generate_design_directions call, in "
        "presentation order -- what 'option 2' resolves against",
    )
    selected_design_family_id: str | None = None
    current_version_id: dict[str, str] = Field(default_factory=dict)
    redo_hint: dict[str, str] = Field(default_factory=dict)

    visualizations: list[VisualizationResult] = Field(default_factory=list)
    conversation_state: ConversationState = Field(default_factory=ConversationState)


# --- pure helper functions over a DesignSession -- logic stays in plain
# module-level functions, matching this codebase's convention; the models
# above stay pure data. -------------------------------------------------


def active_fabric_ref(session: DesignSession) -> FabricRef | None:
    return session.fabric_refs[-1] if session.fabric_refs else None


def find_version_node(session: DesignSession, version_id: str) -> DesignVersionNode | None:
    for nodes in session.designs.values():
        for node in nodes:
            if node.version_id == version_id:
                return node
    return None


def children_of(session: DesignSession, version_id: str) -> list[DesignVersionNode]:
    node = find_version_node(session, version_id)
    if node is None:
        return []
    return [n for n in session.designs.get(node.design_family_id, []) if n.parent_version_id == version_id]


def current_node(session: DesignSession, design_family_id: str) -> DesignVersionNode | None:
    version_id = session.current_version_id.get(design_family_id)
    if version_id is None:
        return None
    return find_version_node(session, version_id)
