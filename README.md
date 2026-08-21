# Fashion Intelligence Kernel

An AI Co-Designer for Indian fashion boutiques -- see `docs/architecture.md`
for the full design rationale. This is deliberately *not* a full
application yet: it's the deterministic fashion-intelligence kernel + a
provider-backed visualization layer that will later sit behind a
conversational agent.

**Development status: Phases 1-4 complete. Phase 5 (a conversational
co-designer agent) is not yet implemented** -- everything below is a
programmatic tool/API layer, not a chat product.

## What it does today

```
REAL FABRIC PHOTOGRAPH(S)
        |
PHASE 3 -- Visual Fabric Intelligence
        |   real fabric image(s) -> image quality/evidence -> FabricProfile
        v
PHASE 1 -- Fashion Intelligence
        |   fabric <-> silhouette recommendation ("what should I make with
        |   this fabric?" / "what fabric fits this silhouette?")
        v
PHASE 2 -- Design Intelligence
        |   FabricProfile + client brief + context -> structured
        |   DesignProposal (silhouette, construction, neckline, sleeves,
        |   dupatta, decoration, colorway -- never a text blob)
        v
PHASE 4 -- Fabric-Preserving Design Visualization
        |   original FabricMaterialReference + current DesignProposal
        |   -> fresh Gemini render -> VisualizationResult
        v
"Here is what YOUR fabric could look like as THIS design."
```

Phase 3 can also be skipped by declaring a fabric by name/properties
directly (Phase 1/2 don't require a photograph).

## Quick start

```bash
python3 -m venv .venv          # if you don't already have one
.venv/bin/pip install -e ".[dev]"
cp .env.example .env           # optional -- everything runs fully offline by default

.venv/bin/uvicorn src.api.main:app --reload --port 8000
```

```bash
curl -s http://127.0.0.1:8000/health
```

## Tests

```bash
.venv/bin/pytest src/tests -q                    # full unit/integration suite
.venv/bin/python scripts/run_golden_evals.py     # Phase 1 golden scenarios
.venv/bin/ruff check .                           # lint
```

Every provider defaults to a deterministic mock/template mode, so the full
suite runs offline with zero external calls and zero cost. See
`scripts/run_vision_eval.py` / `scripts/run_visualization_eval.py` /
`scripts/run_staged_visualization_eval.py` for the real-photo/real-provider
acceptance harnesses used during development (these DO make live,
potentially billed provider calls and are not part of the automated suite).

## Example calls

Question A -- what should I make with this fabric?

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tools/recommend-silhouettes \
  -H 'Content-Type: application/json' \
  -d '{
    "fabric_name": "embroidered korean organza",
    "declared_properties": {"surface_density": "dense"},
    "context": {"occasion": "engagement", "size": "L", "top_n": 5}
  }'
```

Question B -- what fabric should I use for this silhouette?

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tools/recommend-fabrics \
  -H 'Content-Type: application/json' \
  -d '{"silhouette_id": "anarkali", "context": {"top_n": 5}}'
```

Consumption + feasibility:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tools/calculate-consumption \
  -H 'Content-Type: application/json' \
  -d '{"garment_id": "suit", "silhouette_id": "anarkali", "size": "L", "fabric_width_cm": 112}'

curl -s -X POST http://127.0.0.1:8000/v1/tools/check-fabric-feasibility \
  -H 'Content-Type: application/json' \
  -d '{"available_metres": 2.8, "required_range": {"min": 8.64, "max": 9.33}, "high_flare": true}'
```

Fabric photo -> evidence -> Phase 1 recommendation (multipart upload):

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tools/fabric-image/recommend-silhouettes \
  -F "images=@swatch.jpg" \
  -F 'context={"occasion": "festive"}'
```

Full endpoint list in `src/api/main.py`; interactive docs at
`http://127.0.0.1:8000/docs` while the server is running.

## Configuration & providers

Every AI provider defaults to disabled/mock -- the kernel runs, and is
fully tested, with zero external calls:

```
LLM_ENABLED=false          # text/design generation
VISION_ENABLED=false       # fabric image understanding
VISUALIZATION_ENABLED=false / VISUALIZATION_PROVIDER=auto   # design visualization
```

Providers are all behind narrow abstractions (`DesignGenerationProvider`,
`FabricVisionProvider`, `DesignVisualizationProvider`) and configurable
independently -- currently:

| Capability | Provider |
|---|---|
| Text / design generation | Alibaba Cloud Model Studio (Qwen, OpenAI-compatible endpoint) |
| Fabric image understanding | Alibaba Cloud Model Studio (Qwen-VL) |
| Design visualization | Google Gemini (`gemini-2.5-flash-image`) |

No API keys, billing identifiers, or provider URLs are documented here --
see `.env.example` for the full list of configuration variables and
`docs/*.md` for how each provider was selected/evaluated.

## Design visualization: the MVP rendering rule

> **Generated visualization images are renderings of canonical design
> state, not design state themselves.**
>
> Every design version is rendered fresh from the original
> `FabricMaterialReference` + the current `DesignProposal` -- never by
> editing a previously generated image.

`DesignProposal` (Phase 2) and the original fabric photographs (Phase 3)
remain the single source of truth. If a generated image disagrees with
them, the image is what's wrong, and nothing in the system infers or
updates a `DesignProposal` from a generated visualization. Changing one
design attribute (e.g. a different neckline) means generating a new
`DesignProposal` version and rendering *that* from scratch against the
original fabric reference -- see `docs/visualization-engine.md` for why
in-place image editing was tried and rejected for this.

## Current limitations (Phase 4 visualization)

- Concept-level visualization, not a manufacturing simulation --
  exact motif placement, scale, and color may vary from the source photo.
- Generative rendering can shift color/transparency somewhat even with a
  validated fabric-preservation prompt; treat output as illustrative.
- No virtual try-on, no customer photographs, no body/fit simulation.
- One visualization per request (no batch/multi-version generation yet --
  each version is an intentional, separately-costed call).
- No conversational agent/chatbot yet -- every capability above is a
  direct, stateless tool/API call.
- No trend intelligence, CRM, or ecommerce integration.

## Documentation

- `docs/architecture.md` -- the hybrid deterministic pipeline, stack choices, repo layout
- `docs/domain-model.md` -- the canonical domain models and why each exists
- `docs/rule-engine.md` -- how compatibility rules and scoring work, in detail
- `docs/tool-contracts.md` -- each tool's contract and purpose
- `docs/design-engine.md` -- Phase 2 design generation pipeline
- `docs/visualization-engine.md` -- Phase 4 visualization architecture, provider
  evaluation, and the rebuild-vs-edit acceptance experiment
- `docs/evaluation.md` -- the golden-scenario test methodology

## Project structure

```
src/domain/              Pydantic domain models + controlled-vocabulary enums
src/fashion_engine/       Deterministic implementations behind each tool
  fabric/                 Phase 3 vision pipeline (preprocessing, evidence, provenance)
  design/                 Phase 2 design generation, validation, scoring
  visualization/          Phase 4 visualization pipeline (MVP path + experimental staged path)
src/rules/                Seed-data repositories + the compatibility rule engine
src/tools/                Typed, documented tool boundary (the future agent's toolkit)
src/providers/            LLM/vision/visualization provider abstractions (disabled by default)
src/api/                  FastAPI app exposing every tool as a POST endpoint
src/tests/                pytest suite
data/seed/                Fabric/garment/silhouette/embellishment/consumption catalogs
data/rules/               General fabric<->silhouette compatibility rule table
data/golden/              Golden scenarios for Phase 1
eval_data/                Real fabric photographs for Phase 3/4 acceptance (gitignored)
artifacts/                Generated visualization assets (gitignored, local dev storage)
docs/                     Architecture + domain + rule-engine + tool-contract + eval docs
scripts/                  Golden-scenario and real-provider evaluation runners
```
