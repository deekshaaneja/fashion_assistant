# Design Intelligence Engine (Phase 2)

Phase 1 answers "what can I make?" (silhouette/fabric compatibility). Phase 2
answers "what should I actually design?" -- turning a fabric + client brief +
fashion context into 2-3 complete, structurally distinct boutique design
directions. See the product brief's Phase 2 spec for the full requirements;
this doc covers what was actually built.

## Pipeline (`src/fashion_engine/design/generate.py`)

```
FabricProfile + FashionContext + ClientBrief + (selected or Phase-1-resolved)
Silhouette
      |
DESIGN CONSTRAINTS   (build_design_constraints -- reuses Phase 1's evaluate_candidate)
      |
CANDIDATE GENERATION (DesignGenerationProvider.generate -- template or live LLM)
      |
DOMAIN VALIDATION    (validate_candidate -- hard, deterministic, never trusts the provider)
      |
DIVERSITY CHECK      (filter_diverse -- structured DesignDNA + attribute similarity)
      |
RERANKING            (score_candidate -- named dimensions, not one vague score)
      |
DesignProposal[]
```

If no `selected_silhouette_id` is given, Phase 1's `recommend_silhouettes` is
called to resolve the top candidate (garment, silhouette) -- Phase 1 logic is
reused, never re-derived (section 33). If given, it's respected unless it
doesn't exist in the catalog.

## Design constraints (`constraints.py`)

`DesignConstraints` translates a Phase 1 `evaluate_candidate` result plus the
brief into the hard facts every candidate must respect: `effective_flare_level`
and `flare_construction` (from Phase 1's own flare-toning logic, section 9 of
the Phase 1.2 brief), `max_embellishment_intensity` (a ceiling derived from
the fabric's surface_density/embellishment_tolerance, never raised just
because the occasion is formal), `requires_lining`, and the real `consumption`
estimate (which may be `NO_CURATED_RULE` -- that must never block design
generation, only inform `fabric_usage`).

## Design DNA (`src/domain/models/design_dna.py`, `dna.py`)

An 8-axis, 0-1 aesthetic vector (`traditional_contemporary`, `minimal_maximal`,
`soft_architectural`, `romantic_sharp`, `understated_glamorous`,
`heritage_modern`, `fluid_structured`, `subtle_statement`) -- never a
designer name. `derive_target_dna` maps a `ClientBrief`'s free-form
`desired_aesthetic` tags and explicit leans onto this vector.

## Design archetypes (`data/seed/design_archetypes.yaml`, `archetypes.py`)

The deterministic "playing field" (section 30: "rules define the playing
field; the model designs within it"). Each archetype is a complete,
structurally distinct construction/neckline/sleeve/decoration/dupatta
philosophy with its own base DesignDNA and preferred
`flare_construction`/`structure_affinity`/`wear_category` -- e.g. Romantic
Fluid (gathered volume, restrained decoration) vs. Architectural Panelled
(controlled volume, minimal/no decoration) vs. Layered Hybrid (a genuinely
different garment architecture, not just a neckline change).

`score_archetype_fit` scores an archetype against the client's target DNA
*and* the actual silhouette's own structural character (an archetype wanting
gathered volume scores lower against a controlled-only silhouette).
`select_diverse` greedily picks `count` archetypes whose DesignDNA is at
least `min_dna_distance` apart -- the mechanism that guarantees the returned
directions differ structurally, not just cosmetically (section 8).

## Candidate generation providers (`src/providers/design_generation.py`)

Mirrors Phase 1's `LanguageModelProvider` pattern: one abstract contract,
gated by the same `llm_enabled` setting.

- **`TemplateDesignGenerationProvider`** (default when `LLM_ENABLED=false`):
  fully deterministic, no network call. Selects diverse archetypes and
  elaborates each into a full `DesignCandidate` via the same rule-based
  sub-tools (`neckline.py`, `sleeves.py`, `decoration.py`, `dupatta.py`) a
  live provider's output is validated against.
- **`OpenAICompatibleDesignGenerationProvider`** (used when `LLM_ENABLED=true`):
  sends the fabric, constraints, brief, and the full archetype menu (as
  context, not as a directive to copy verbatim) to an OpenAI-compatible
  `/chat/completions` endpoint in JSON mode, asking for `count + 1`
  candidates. Malformed/schema-invalid items trigger a targeted repair
  round-trip (the specific pydantic validation errors are sent back,
  asking for corrected versions of only those items), up to
  `_MAX_REPAIR_ATTEMPTS` times. Valid candidates are deduplicated by title
  across repair rounds (a repair response can legitimately resend an
  already-accepted item alongside the fixed one). On total failure --
  network error, no valid candidates after all attempts -- returns an empty
  list; `generate_design_directions` then falls back to the template
  provider and records `fallback_to_template=True` in
  `generation_metadata`. The live model's chain-of-thought is never read
  (only `message.content`, never `reasoning_content`).

**The LLM never decides validity.** Whichever provider produced a candidate,
`validate_candidate` (below) checks it against the same `DesignConstraints`
and the client's explicit preferences -- a live provider proposing a flare
level, decoration intensity, or neckline that violates a stated constraint or
preference gets that candidate rejected, not silently accepted.

## Validation (`validation.py`)

Hard, deterministic checks -- a candidate failing any of these is rejected
outright:

- garment/silhouette matches what was actually requested (catches a
  hallucinated component)
- `flare_construction`/`flare_level` match the fabric-appropriate values from
  `DesignConstraints` (never the silhouette's raw, possibly-too-ambitious
  default)
- lining present when the fabric's transparency requires it
- decoration level does not exceed `max_embellishment_intensity`
- sleeves aren't marked sheer while also sleeveless (an inconsistency the
  live model actually produced once during development -- see "known
  weaknesses" in the Phase 2 report)
- neckline/sleeve/decoration don't contradict an explicit client preference

## Diversity (`diversity.py`)

`similarity(a, b)` blends DesignDNA distance (60%) with shared discrete
attributes -- bodice style, flare_construction, neckline, sleeve
length+style, dupatta inclusion, decoration level, bottom type (40%).
Structured attributes first, never only embedding similarity (section 29 --
there is no embedding step anywhere in this kernel). `filter_diverse` greedily
keeps candidates below a similarity threshold and does **not** backfill with
near-duplicates if too few survive -- returning fewer honest directions beats
padding with cosmetic variations.

## Scoring (`scoring.py`)

Eight named dimensions (`fabric_design_fit`, `aesthetic_coherence`,
`occasion_fit`, `client_brief_fit`, `construction_coherence`,
`surface_design_coherence`, `color_coherence`, `originality`), each with a
`trace` explaining what was checked -- never one vague "fashion score"
(section 19). Used only to rerank already-validated candidates.

## Colorways, dupatta, ensemble, proportions, neckline, sleeves, decoration

Each is both a standalone tool (`src/tools/*.py`) and a building block the
providers/orchestrator call: `generate_design_colorways` (multi-component
color stories, reusing Phase 1's `color_math.py`), `recommend_dupatta`
(decides whether a dupatta belongs at all before its fabric/color/border),
`design_ensemble` (derives the complete look directly from the garment's own
`typical_components`, so a suit/lehenga/jacket_set naturally get different
ensembles), `recommend_proportions`, `recommend_neckline`, `recommend_sleeves`,
`recommend_decoration` (genuinely capable of `NO_ADDITIONAL_DECORATION`).

## API

`POST /v1/tools/generate-design-directions` is the main Phase 2 endpoint;
every sub-tool above also has its own endpoint, following the same
convention as Phase 1 (`docs/tool-contracts.md`).

## Known limitations

- No regeneration round-trip when diversity filtering leaves fewer than
  `count` valid, distinct candidates -- the pipeline returns fewer directions
  honestly rather than calling the provider again for a replacement.
- `client_brief_fit` and `occasion_fit` scoring use a handful of explicit
  signals (stated preferences, an approximate formality read from DesignDNA)
  rather than the full richness Phase 1's context-suitability scoring has;
  they are reasoned, not exhaustive.
- The live provider's response time (a full multi-candidate structured
  generation against a reasoning model) is substantial -- often 2-8 minutes
  per call including any repair round-trips.
