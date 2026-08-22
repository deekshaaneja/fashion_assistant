"""apply_design_change: Phase 5's ONLY path for turning a structured
`DesignChange` into a new immutable `DesignProposal` version (product brief
section 9-10). Reuses the exact same deterministic pipeline
`generate_design_directions` already uses --
`assemble_candidate -> validate_candidate` (which itself runs
`check_coherence`) -- never a second design-generation/validation
implementation. A change that fails validation never commits: the base
version is untouched and the rejection reasons are returned, never silently
dropped or partially applied.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_generation import DesignGenerationRequest
from src.domain.models.design_proposal import (
    BottomSpec,
    ConstructionCreative,
    DecorationCreative,
    DesignProposal,
    DupattaCreative,
    GeneratedDesignContent,
    NecklineCreative,
    SleeveSpec,
    SupportingFabricSuggestion,
)
from src.domain.models.session import (
    DesignChange,
    DesignChangeResult,
    DesignSession,
    DesignVersionNode,
    active_fabric_ref,
    find_version_node,
    new_id,
)
from src.fashion_engine.design.assembly import assemble_candidate
from src.fashion_engine.design.constraints import build_design_constraints
from src.fashion_engine.design.scoring import score_candidate
from src.fashion_engine.design.validation import validate_candidate
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository

_COMPONENT_MODELS: dict[str, type] = {
    "neckline": NecklineCreative,
    "sleeves": SleeveSpec,
    "construction": ConstructionCreative,
    "bottom": BottomSpec,
    "dupatta": DupattaCreative,
    "decoration": DecorationCreative,
    "design_dna": DesignDNA,
}


def _to_generated_content(proposal: DesignProposal, root_risks: list[str]) -> GeneratedDesignContent:
    """The inverse of `assemble_candidate`'s split -- reconstructs the
    model-facing creative subset from an already-assembled `DesignProposal`,
    so a modification starts from the SAME creative surface a
    `DesignGenerationProvider` would have produced, not from the fully
    deterministic-assembled shape."""
    dupatta_creative = DupattaCreative(**proposal.dupatta.model_dump()) if proposal.dupatta is not None else None
    decoration_creative = DecorationCreative(
        level=proposal.decoration.level,
        treatments=list(proposal.decoration.treatments),
        rationale=proposal.decoration.rationale,
    )
    supporting_fabrics = [
        SupportingFabricSuggestion(
            component=c.component,
            fabric_description=c.fabric_description or f"{c.component} fabric",
            rationale=c.rationale,
        )
        for c in proposal.fabric_usage.components
        if c.component not in ("main_garment", "lining", "dupatta")
    ]
    return GeneratedDesignContent(
        title=proposal.title,
        design_intent=proposal.design_intent,
        construction=ConstructionCreative(**proposal.construction.model_dump()),
        neckline=NecklineCreative(
            type=proposal.neckline.type, depth=proposal.neckline.depth, rationale=proposal.neckline.rationale
        ),
        sleeves=proposal.sleeves.model_copy(),
        bottom=proposal.bottom.model_copy() if proposal.bottom is not None else None,
        dupatta=dupatta_creative,
        decoration=decoration_creative,
        supporting_fabrics=supporting_fabrics,
        design_dna=proposal.design_dna.model_copy(),
        rationale=list(proposal.rationale),
        risks=list(root_risks),
    )


def _apply_change_to_content(content: GeneratedDesignContent, change: DesignChange) -> GeneratedDesignContent:
    """`replace` swaps the whole sub-model (parsed fully against its own
    schema); `set` merges only the given keys onto the current value.
    Raises `pydantic.ValidationError` on an invalid/incomplete value --
    callers must catch this and reject the change rather than let a
    malformed patch through (section 9: never a raw, unvalidated patch)."""
    model_cls = _COMPONENT_MODELS[change.component]
    current: Any = getattr(content, change.component)

    if change.operation == "replace" or current is None:
        new_value = model_cls.model_validate(change.value)
    else:
        new_value = current.model_copy(update=change.value)
        model_cls.model_validate(new_value.model_dump())  # re-validate the merged shape

    return content.model_copy(update={change.component: new_value})


def next_version_label(session: DesignSession, base: DesignVersionNode) -> str:
    existing = session.designs.get(base.design_family_id, [])
    return f"{base.design_family_id}-V{len(existing) + 1}"


def register_design_proposal(
    session: DesignSession, proposal: DesignProposal, turn_id: str | None = None
) -> DesignVersionNode:
    """Registers a freshly-generated `DesignProposal` (from
    `generate_design_directions`) as a new V1 root -- the entry point for
    every design family, never created via `apply_design_change`."""
    family_id = new_id("D")
    version_id = f"{family_id}-V1"
    node = DesignVersionNode(
        version_id=version_id,
        design_family_id=family_id,
        parent_version_id=None,
        proposal=proposal.model_copy(update={"id": version_id}),
        change=None,
        root_risks=list(proposal.risks),
        created_turn_id=turn_id,
    )
    session.designs[family_id] = [node]
    session.current_version_id[family_id] = version_id
    return node


def apply_design_change(
    session: DesignSession, change: DesignChange, turn_id: str | None = None
) -> DesignChangeResult:
    base = find_version_node(session, change.base_version_id)
    if base is None:
        issue = f"unknown design version '{change.base_version_id}'"
        return DesignChangeResult(ok=False, rejection_issues=[issue])

    content = _to_generated_content(base.proposal, base.root_risks)
    try:
        content = _apply_change_to_content(content, change)
    except ValidationError as exc:
        return DesignChangeResult(ok=False, rejection_issues=[f"invalid {change.component} value: {exc}"])

    fabric_ref = active_fabric_ref(session)
    if fabric_ref is None:
        return DesignChangeResult(ok=False, rejection_issues=["no fabric on file for this session"])
    resolution = get_fabric_repository().resolve(fabric_ref.fabric_name)
    fabric = resolution.profile
    if fabric_ref.declared_properties is not None:
        fabric = fabric.model_copy(update={"properties": fabric_ref.declared_properties})

    garment_id = base.proposal.garment.garment.id
    silhouette_id = base.proposal.garment.silhouette.id
    garment = get_garment_repository().get(garment_id)
    silhouette = get_silhouette_repository().get(silhouette_id)
    if garment is None or silhouette is None:
        return DesignChangeResult(ok=False, rejection_issues=["garment/silhouette no longer resolvable"])

    constraints = build_design_constraints(
        fabric, garment, silhouette, session.fashion_context, session.client_brief
    )
    new_candidate = assemble_candidate(content, fabric, garment, silhouette, constraints)

    request = DesignGenerationRequest(
        fabric=fabric,
        fashion_context=session.fashion_context,
        client_brief=session.client_brief,
        constraints=constraints,
        garment_id=garment.id,
        garment_name=garment.name,
        silhouette_id=silhouette.id,
        silhouette_name=silhouette.name,
        count=1,
    )
    issues = validate_candidate(new_candidate, request)
    if issues:
        return DesignChangeResult(ok=False, rejection_issues=issues)

    scores = score_candidate(new_candidate, constraints, session.fashion_context, session.client_brief, [])
    version_id = next_version_label(session, base)
    new_proposal = DesignProposal(
        **new_candidate.model_dump(),
        id=version_id,
        rank=1,
        palette=base.proposal.palette,
        scores=scores,
        confidence=base.proposal.confidence,
    )
    new_node = DesignVersionNode(
        version_id=version_id,
        design_family_id=base.design_family_id,
        parent_version_id=base.version_id,
        proposal=new_proposal,
        change=change,
        root_risks=list(base.root_risks),
        created_turn_id=turn_id,
    )
    session.designs.setdefault(base.design_family_id, []).append(new_node)
    session.current_version_id[base.design_family_id] = version_id
    session.redo_hint.pop(base.design_family_id, None)
    return DesignChangeResult(ok=True, new_version=new_node)
