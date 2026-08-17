# Tool Contracts

Every tool lives in `src/tools/`, is independently callable (no UI, no other tool
required first), typed in and out via Pydantic models, and covered by
`src/tests/`. Each is exposed as a `POST /v1/tools/*` endpoint in `src/api/main.py`
for now; a future agent orchestrator calls the same functions directly rather than
going through HTTP.

## 1. `analyze_fabric(observation: FabricObservation) -> FabricAnalysis`

**Why it exists:** the entry point for "what do I know about this fabric?" --
resolves a free-text fabric name against the seed catalog, merges in any declared
per-swatch properties, and surfaces strengths/limitations/suitable garment families
in one structured object.

**Deterministic.** Pure catalog lookup + property merge; no LLM involved.

## 2. `recommend_silhouettes(fabric_name, declared_properties?, context?) -> SilhouetteRecommendationResult`

**Why it exists:** Question A, "I have this fabric, what should I make?" Ranks
every `(garment, silhouette)` pairing the fabric could plausibly become.

**Output:** `candidates` (top N, ranked, classified, with reasons/risks/
consumption estimate/confidence/source rules) plus `avoid_examples` (up to 2
explicit AVOID-tier pairings, even if they'd otherwise fall outside the top N) --
so "what should be avoided, and why" is always answerable, not just implied by
absence from the top list.

**Deterministic core, LLM-free.** Fabric resolution degrades gracefully
(exact -> partial -> unresolved) rather than erroring on an unknown name.

## 3. `recommend_fabrics(silhouette_id, garment_id?, context?) -> FabricRecommendationResult`

**Why it exists:** Question B, the mirror image -- "I want this silhouette, what
fabric should I use?" Uses the exact same scoring engine as `recommend_silhouettes`,
just with fabric as the varying axis.

**`garment_id` disambiguation:** a silhouette like "flared" applies to more than
one garment (suit, lehenga, gown, skirt-top). If `garment_id` is omitted, the
kernel assumes the first applicable garment and states that assumption explicitly
in the result rather than guessing silently (section 18: "when assuming, state
it"). If the silhouette applies to exactly one garment (e.g. "anarkali" -> suit
only), no assumption is needed.

## 4. `recommend_styling(garment_id, silhouette_id, fabric_name, context?) -> StylingSpec`

**Why it exists:** once a garment/silhouette/fabric is chosen, this fills in the
construction detail -- neckline, sleeve, length, flare, bottom style, dupatta,
lining, finishing, decoration intensity -- as one structured object, never prose.

**Deterministic rule lookups** over the fabric's own properties (e.g. a sheer
fabric gets a lining note and three-quarter sleeves; an already-densely-decorated
fabric gets restrained decoration intensity regardless of occasion).

## 5. `calculate_consumption(garment_id, silhouette_id, size?, fabric_width_cm?, ...) -> ConsumptionEstimate`

**Why it exists:** deterministic yardage estimation. See `docs/rule-engine.md` for
the arithmetic. Always a `min_metres`/`max_metres` range with `assumptions` and a
`confidence` score -- never a single fake-precise number.

## 6. `check_fabric_feasibility(available_metres, required_range, ...) -> FeasibilityResult`

**Why it exists:** turns a consumption estimate plus "how much fabric do I
actually have" into a decisive feasibility verdict and, when short, concrete
rule-based redesign options (not an LLM improvising suggestions).

## 7. `generate_colorways(fabric_name, garment_id?, context?) -> Colorway`

**Why it exists:** a structured colorway engine -- main/supporting/metallic/
embroidery colors, a harmony type, and a dupatta color direction. No image
generation in Phase 1. Every color relationship is exact HSL math
(`src/fashion_engine/colors/color_math.py`), never an LLM-invented hex value.

---

## Phase 2: Design Intelligence Engine (see docs/design-engine.md)

## 8. `generate_design_directions(fabric_name, declared_properties?, fashion_context?, client_brief?, selected_garment_id?, selected_silhouette_id?, count=3) -> DesignDirectionsResult`

**Why it exists:** the core Phase 2 capability -- "what should I actually
design?" Turns a fabric + client brief + fashion context into `count`
complete, validated, structurally distinct `DesignProposal`s (construction,
neckline, sleeves, bottom, dupatta, lining, palette, decoration, fabric
usage), plus a validation report (what was rejected and why) and generation
metadata (which provider ran, whether it fell back to the deterministic one).

**Hybrid, not "one LLM call."** Constraints and candidate validation/
diversity/reranking are fully deterministic; only candidate elaboration is
ever delegated to a `DesignGenerationProvider`, and its output is always
re-checked against the same deterministic constraints. See
`docs/design-engine.md` for the full pipeline.

## 9. `design_ensemble(primary_design: DesignProposal) -> DesignEnsemble`

**Why it exists:** thinks about the complete look, not just the main
garment -- derived directly from the garment's own `typical_components`
(Phase 1 catalog data), so a suit, a lehenga, and a jacket set naturally get
different ensembles without any garment-specific branching.

## 10. `recommend_neckline` / `recommend_sleeves` / `recommend_proportions` / `recommend_decoration` / `recommend_dupatta` / `generate_design_colorways`

Standalone versions of the same deterministic sub-tools the generation
pipeline calls internally -- each independently callable, each documented in
`docs/design-engine.md`. `recommend_decoration` is genuinely capable of
returning `NO_ADDITIONAL_DECORATION`; occasion never implies heavy decoration
on its own.

---

## Deterministic vs. AI responsibilities (section 2)

| Deterministic (always, no LLM) | Optional LLM (disabled by default) |
|---|---|
| Fabric/silhouette compatibility scoring | Turning a `DesignProposal`-style set of facts into warm prose |
| Consumption arithmetic | Creative elaboration of a design candidate WITHIN a fixed archetype/constraint menu (Phase 2, `DesignGenerationProvider`) |
| Feasibility verdicts | Semantic interpretation of unstructured free text (future phase) |
| Classification tiers | Image understanding (future phase) |
| Color harmony relationships | |
| Every score component and weight | |
| Design constraints, validation, diversity checking, and reranking (Phase 2) | |

`src/providers/llm.py`'s `LanguageModelProvider.explain()` is the *only* place an
LLM can touch Phase 1 kernel output, and its own docstring states the constraint: it must
never override a deterministic tool's score, tier, consumption number, or
compatibility verdict. The default provider (`NullLanguageModelProvider`) always
returns the deterministic fallback untouched -- proof that every Phase 1 tool is fully
functional with zero LLM calls, which is exactly what `src/tests/` exercises.

Phase 2's `DesignGenerationProvider` (`src/providers/design_generation.py`)
is a second, wider LLM boundary -- creative candidate generation, not just
prose -- but it is still bounded the same way: the live provider proposes a
`DesignCandidate`, and `validate_candidate` disposes, rejecting anything that
violates a stated fabric/construction constraint or an explicit client
preference regardless of which provider produced it. The default
(`TemplateDesignGenerationProvider`, used when `LLM_ENABLED=false`) needs no
network call at all.

## Discoverability for a future agent

Every tool's request/response shape is a Pydantic model, so
`Model.model_json_schema()` produces a ready-made JSON schema for an LLM
function-calling tool definition without hand-maintaining a second copy of the
contract. Adding a new tool later means: implement it in `src/fashion_engine/`,
wrap it thinly in `src/tools/`, and it's immediately both API-callable and
agent-callable.
