# Fashion Intelligence Kernel

**Phase 1** of an AI Co-Designer for Indian Fashion Boutiques -- see
`docs/architecture.md` for the full design rationale.

This is deliberately *not* a full application. It's the deterministic fashion
intelligence kernel that later becomes the tool layer behind a conversational
agent. It answers two questions:

- **Question A:** "I have this fabric, what should I make?"
- **Question B:** "I want this silhouette, what fabric should I use?"

No frontend, no client book, no ecommerce integration, no order management, no
image generation, no MCP servers in this phase -- see `docs/architecture.md` and
the product brief for the explicit Phase 1 scope boundary.

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
.venv/bin/pytest src/tests -q                    # 74 unit/integration tests
.venv/bin/python scripts/run_golden_evals.py     # 55 golden scenarios, 66 checks
.venv/bin/ruff check src/ scripts/                # lint
```

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

Full endpoint list in `src/api/main.py`; interactive docs at
`http://127.0.0.1:8000/docs` while the server is running.

## Configuration

Every AI provider defaults to disabled -- the kernel runs, and is fully tested,
with zero external calls:

```
LLM_ENABLED=false   # OpenAI-compatible endpoint (Ollama, Aliyun DashScope, etc.)
```

Turning it on only changes the (currently unused in Phase 1) explanation-prose
path in `src/providers/llm.py` -- it can never change a score, tier, consumption
number, or compatibility verdict. See `docs/tool-contracts.md`.

## Documentation

- `docs/architecture.md` -- the hybrid deterministic pipeline, stack choices, repo layout
- `docs/domain-model.md` -- the canonical domain models and why each exists
- `docs/rule-engine.md` -- how compatibility rules and scoring work, in detail
- `docs/tool-contracts.md` -- each of the seven tools' contract and purpose
- `docs/evaluation.md` -- the golden-scenario test methodology

## Project structure

```
src/domain/          Pydantic domain models + controlled-vocabulary enums
src/fashion_engine/   Deterministic implementations behind each tool
src/rules/            Seed-data repositories + the compatibility rule engine
src/tools/            Typed, documented tool boundary (the future agent's toolkit)
src/providers/        Optional LLM provider abstraction (disabled by default)
src/api/              FastAPI app exposing every tool as a POST endpoint
src/tests/            pytest suite
data/seed/            Fabric/garment/silhouette/embellishment/consumption catalogs
data/rules/           General fabric<->silhouette compatibility rule table
data/golden/          55 golden scenarios
docs/                 Architecture + domain + rule-engine + tool-contract + eval docs
scripts/              Golden-scenario eval runner
```
