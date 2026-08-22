# Phase 5: Conversational Co-Designer Orchestration

Phase 5 adds a conversational orchestration layer over the existing Phase
1-4 kernel. It does not reimplement any fashion/vision/design/visualization
logic -- its only job is to interpret intent, maintain structured session
state, choose the right existing tool, and sequence tool calls into a
coherent design workflow.

```
USER
 |
POST /v1/chat  (src/api/main.py)
 |
run_turn()     (src/agent/loop.py)  <-- bounded loop, max 5 tool calls/turn
 |
ConversationProvider.decide()  (src/providers/agent.py)
 |    one structured TurnDecision per iteration
 v
TOOL_REGISTRY  (src/agent/tool_registry.py)  -- the ONLY dispatchable set
 |
src/tools/*  (Phase 1-4, unchanged)
 |
DesignSession  (src/domain/models/session.py)  -- persisted via SessionStore
```

## Tool-calling mechanism

No real OpenAI `tools=[...]` function-calling. The model (or the
deterministic mock) emits one `TurnDecision` JSON object per loop
iteration via the same `response_format: json_schema` structured-output
call `OpenAICompatibleDesignGenerationProvider` already uses successfully
against this account's endpoint (see `docs/design-engine.md`). Every other
provider in this kernel already needed its own account-specific deviation
from generic vendor documentation, so real function-calling was treated as
unverified and not built as the primary mechanism. The orchestrator, not
the model, decides whether another loop iteration is needed -- "show me all
three" is three separate `TurnDecision`s (three separate `visualize_design`
calls), never one decision fanning out.

## Session state, not transcript

`DesignSession` (`src/domain/models/session.py`) is the state of record.
Fabric/design/visualization facts are stored by reference to the existing
Phase 1-4 domain models (`FabricProfile`, `DesignProposal`,
`VisualizationResult`), never duplicated. A design is a tree of immutable
`DesignVersionNode`s -- a flat list per `design_family_id`, each node
carrying its own `parent_version_id`, so branching needs no separate
recursive structure. A version is never mutated in place; a `DesignChange`
always produces a new node via `src/agent/design_changes.py`, which reuses
the exact same `assemble_candidate -> validate_candidate` pipeline
`generate_design_directions` already uses. A change that fails validation
is rejected with reasons -- nothing is committed.

Session persistence is sqlite (stdlib, `src/agent/session_store.py`),
`AGENT_SESSION_DB_PATH` (default `data/sessions.db`, gitignored).

## Cost policy

Every registered tool (`src/agent/tool_registry.py`) carries a `cost_class`
(LOW/MEDIUM/HIGH). `src/agent/cost_policy.py` is the single choke point:
LOW/MEDIUM tools may run whenever useful; the one HIGH-cost tool
(`visualize_design`) only runs on an explicit user request -- it never
auto-triggers after design generation or modification. `visualize_design`
itself always renders from the session's ORIGINAL uploaded fabric images
(reloaded from the asset store by reference) plus the current
`DesignProposal` version -- never from a previously generated image,
mirroring the Phase 4 regression test of the same invariant.

## Security

The orchestration loop only ever dispatches a tool whose name is a key in
`TOOL_REGISTRY`; anything else is rejected and logged, never executed. No
shell/URL/DB/filesystem access is reachable from model output.

## Deliberately out of scope for Phase 5

MCP, trend/designer-inspiration retrieval, a production frontend,
ecommerce/CRM/supplier-catalog integration, and virtual try-on. A minimal
in-process CLI harness (`scripts/chat_cli.py`) exists for manual testing
only.
