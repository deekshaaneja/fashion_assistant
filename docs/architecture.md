# Architecture

## Principle

> Deterministic domain logic first. An LLM is optional, disabled by default, and
> only ever turns already-computed facts into prose -- it never decides a score,
> tier, consumption number, or compatibility verdict.

```
INPUT (fabric name / silhouette id / structured context)
  |
  v
STRUCTURED DOMAIN CONTEXT (Fabric, Garment, Silhouette, RecommendationContext)
  |
  v
DETERMINISTIC / RULE-BASED FASHION LOGIC (src/rules/, src/fashion_engine/)
  |
  v
CANDIDATE GENERATION (every applicable (garment, silhouette) or fabric pairing)
  |
  v
SCORING / RANKING (src/fashion_engine/scoring/engine.py, 6 weighted components)
  |
  v
OPTIONAL LLM EXPLANATION (src/providers/llm.py -- disabled by default)
  |
  v
STRUCTURED OUTPUT (typed Pydantic models, never free prose as the primary result)
```

The kernel is fully functional -- and fully tested -- with the LLM disabled. Turning
it on changes only prose explanation text; it can never change a score, tier,
consumption number, or compatibility verdict (see `src/providers/llm.py`'s
docstring and `docs/rule-engine.md`).

## Stack

- **Python 3.10+, FastAPI, Pydantic v2, pytest.** Same stack shape as most
  production Python services; nothing exotic.
- **No SQLAlchemy/PostgreSQL in Phase 1.** The two core questions and seven tools
  are stateless functions over structured input + seed data -- nothing needs to be
  persisted yet (no client book, no order management, no saved consultations in
  this phase; see the product brief's explicit Phase 1 exclusions). Adding a
  database now would be infrastructure that doesn't serve Phase 1. If/when a later
  phase needs to persist a conversation or a boutique's saved designs, the existing
  `Pydantic` domain models already have a very small surface to add a persistence
  layer behind (see the previous iteration of this project's
  `JsonRepository`-then-swap-for-SQL pattern as prior art).
- **No microservices, no message queue, no vector database.** A modular monolith,
  per the product brief's explicit instruction. `src/rules/` and
  `src/fashion_engine/` are plain Python packages, not services.
- **YAML seed data, not a database.** `data/seed/*.yaml` and `data/rules/*.yaml`
  are loaded once (`@lru_cache`) and queried in-memory. This keeps every fact the
  kernel relies on inspectable in a text diff, versionable, and boutique-overridable
  in principle without a migration.

## Repository layout

```
src/
  domain/
    enums/          Controlled vocabularies (WearCategory, Drape, Classification, ...)
    models/         Pydantic domain models (Fabric, Garment, Silhouette, ...)
  fashion_engine/
    fabric/         analyze_fabric, recommend_fabrics implementations
    silhouettes/    recommend_silhouettes implementation
    styling/        recommend_styling implementation
    colors/         generate_colorways implementation + deterministic HSL math
    scoring/        the 6-component weighted scoring engine + classification
    consumption/    calculate_consumption implementation
    feasibility/    check_fabric_feasibility implementation
    design/         Phase 2 Design Intelligence Engine (see docs/design-engine.md) --
                     constraints, archetypes, validation, diversity, scoring, and the
                     neckline/sleeve/decoration/dupatta/ensemble/colorway sub-tools
  rules/            Seed-data repositories + the fabric<->silhouette compatibility
                     rule evaluator (the "rule engine" -- see docs/rule-engine.md)
  tools/            Thin, typed, documented wrappers -- the actual tool boundary a
                     future agent (or the API) calls (see docs/tool-contracts.md)
  providers/        LanguageModelProvider (Phase 1, prose-only) and
                     DesignGenerationProvider (Phase 2, creative candidate generation)
                     abstractions -- both optional, both disabled unless LLM_ENABLED
  api/              FastAPI app exposing every tool as a POST endpoint
  tests/            pytest unit/integration tests
data/
  seed/             Fabric/garment/silhouette/embellishment/consumption-rule/
                     design-archetype catalogs
  rules/            The general fabric<->silhouette compatibility rule table
  golden/           50+ golden scenarios (docs/evaluation.md)
docs/               This documentation set
scripts/            The golden-scenario eval runner + the Phase 2 design golden review
```

## Phase 2: a second, wider LLM boundary

Phase 1's principle -- deterministic logic decides, an LLM only narrates --
holds for every Phase 1 tool. Phase 2 (the Design Intelligence Engine, see
docs/design-engine.md) adds a second boundary that's deliberately wider: a
`DesignGenerationProvider` may creatively propose a full design candidate's
construction/neckline/sleeve/decoration choices, not just prose. What stays
constant is the *shape* of the guarantee: the provider proposes, and
deterministic validation (`src/fashion_engine/design/validation.py`) disposes
-- a candidate that violates a fabric/construction constraint or an explicit
client preference is rejected regardless of which provider produced it, and a
failing live provider always falls back to a fully deterministic template
provider rather than blocking generation.

## Why this shape supports a future conversational agent

Every one of the seven tools in `src/tools/` is:

- **Independently callable** -- no tool depends on another tool having been called
  first, and none require the FastAPI layer or any UI.
- **Typed in, typed out** -- Pydantic models throughout, so a future agent's
  tool-calling schema can be generated directly from `Model.model_json_schema()`
  rather than hand-maintained.
- **Deterministic where it matters** -- fabric/silhouette compatibility, scoring,
  consumption, and feasibility never change answer based on an LLM's mood; the
  same input always produces the same output (see `test_generate_colorways.py`'s
  determinism test as one example enforced by the suite).

Adding a conversational agent later means: add an orchestration loop that calls
these same `src/tools/*` functions and turns their structured results into prose
(exactly the pattern `src/providers/llm.py`'s `explain()` contract already
establishes) -- not rewriting the domain logic underneath it.
