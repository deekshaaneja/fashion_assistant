# Domain Model

Every canonical concept has exactly one model, in exactly one place. Nothing in
`src/tools/`, `src/api/`, or `src/fashion_engine/` defines a competing shape for
any of these -- see `docs/architecture.md` for why that matters for a future agent.

## Fabric (`src/domain/models/fabric.py`)

`Fabric` is static, seeded catalog knowledge about a fabric *family* (e.g.
"organza"), not a specific physical swatch. Its `properties: FabricProperties`
are **all optional** -- section 4 of the product brief is explicit that "not every
field must always be known" and that uncertainty must be represented explicitly,
not defaulted away. A `None` property means "unknown," never "assumed average."

`FabricObservation` (`src/domain/models/fabric_analysis.py`) is the separate,
per-swatch layer: what a caller *declares* about a specific piece of fabric (e.g.
"this organza happens to be embroidered"). `analyze_fabric` merges declared
properties over the catalog defaults field-by-field, using Pydantic's
`model_fields_set` rather than comparing values -- several fields (`surface_density:
none`, `stretch: none`) have "none" as a real, meaningful declared value, not a
not-declared sentinel, so a naive value comparison would silently ignore a real
override. See `merge_fabric_properties` in `src/fashion_engine/fabric/analyze.py`.

## Garment and Silhouette (`src/domain/models/garment.py`)

These are two separate, composable axes, not one flat enum:

- **Garment** = the broad category of clothing (suit, kurta set, saree, lehenga,
  gown, ...).
- **Silhouette** = the shape applied to a garment (straight, A-line, Anarkali,
  fitted, ...).

A named outfit like "A-line suit" is the *pair* `(garment=suit, silhouette=a_line)`,
not a single catalog entry. This is why `recommend_silhouettes` returns
`(garment_id, silhouette_id)` pairs rather than one id, and why `recommend_fabrics`
needs a `garment_id` to disambiguate silhouettes (like "a_line") that apply to more
than one garment category.

Both are seeded from `data/seed/garments.yaml` / `data/seed/silhouettes.yaml`, not
hardcoded as Python enums -- section 4 explicitly asks that silhouettes be
"extensible through data/configuration," and the same reasoning applies to garments.
Adding a new silhouette or garment is a YAML edit, never a code change.

A `Silhouette` also declares `flare_construction` (Phase 1.2, section 9) --
`controlled` (panel/godet-built volume, held by the cut), `gathered`
(fullness gathered from a seam/yoke, needs some drape), or `dramatic`
(maximum-volume circular/godet flare). This is separate from
`default_flare_level` (how much flare) because the two interact very
differently with a fabric's own body -- see docs/rule-engine.md.

**Valid combinations are explicit, not a Cartesian product** (Phase 1.1, section
2). Each silhouette declares `applicable_garment_ids` -- the actual garments it
can pair with -- rather than every silhouette being assumed valid for every
garment. This is what stops nonsensical pairings like "Gown + Flared" or "Suit +
Fitted" from ever being generated: "flared" (big, dramatic volume) is restricted
to `lehenga`, since a suit's equivalent big-volume register is the Anarkali/
Kalidar/Panelled family and a gown's is A-Line/Empire/Structured; "fitted" is
restricted to the Western-register garments (gown, cocktail_dress, evening_dress,
corset_skirt), since Indian suits express a close cut via "straight"/"relaxed"
instead. The exact ontology in `silhouettes.yaml` can be revised as domain
expertise grows -- the mandatory principle is that it stays an explicit,
maintained set of valid pairs, never an assumed full cross-product.

## Styling (`src/domain/models/styling.py`)

`StylingSpec` is the structured output of `recommend_styling` -- neckline, sleeve,
length, flare, waist placement, bottom style, dupatta, lining, finishing, and
decoration intensity. Always a structured object; `recommend_styling` never
returns free prose as its primary result.

## Recommendation (`src/domain/models/recommendation.py`)

Phase 1.2: a candidate is three separate, never-blended judgments, not one
opaque score -- see docs/rule-engine.md's "Three questions, not one."
`SuitabilityAssessment` (used for both `design_suitability` and
`context_suitability`) carries a `score`, a five-tier `classification`
(`SuitabilityTier`: EXCELLENT/STRONG/MODERATE/WEAK/POOR), `components` (only
the ones genuinely computable given the inputs), `omitted_components`
(component name -> why it couldn't be computed, e.g. "no occasion given" --
never silently filled with a placeholder score), and `component_trace`
(component name -> the rule ids/evidence that produced it, for development
inspection). `material_feasibility` is a `MaterialFeasibility`
(see below) and never affects `recommendation_classification`.

`SilhouetteCandidate`/`FabricCandidate` are the two mirror-image
ranked-and-classified output shapes for Question A and Question B
respectively: `recommendation_classification` (design+context quality only),
`design_suitability`, `context_suitability`, `material_feasibility`,
`actionability` (what to do next -- folds classification and feasibility
together), `consumption`, `reasons`, `risks`, `assumptions`, a
`ConfidenceBreakdown` (`design_suitability`/`context_suitability`/
`consumption`/`overall`, all 0-1), and `source_rules`. `garment`/`silhouette`/
`fabric` are lightweight `*Ref` objects (`id`, `name`), not the full catalog
entry, to avoid duplicating catalog data across every ranked candidate.

## ConsumptionRule / ConsumptionEstimate (`src/domain/models/consumption.py`)

`ConsumptionRule` is a *seeded starting assumption* for a `(garment_id,
silhouette_id)` pair at a reference size/width -- explicitly not "universal
manufacturing truth" (section 4). Only pairs the garment/silhouette ontology
above actually allows have a rule; there is no consumption rule for a
combination that shouldn't exist. Each rule carries a `source`
(`seed`/`curated`/`boutique_override`) -- see `docs/rule-engine.md`.

`ConsumptionEstimate` has a `status` (`ESTIMATED` or `NO_CURATED_RULE`,
Phase 1.2 section 6) -- `min_metres`/`max_metres` are both `None` when no
curated rule exists, rather than a fabricated generic range. When
`ESTIMATED`, it carries the arithmetic itself as data, not just prose:
`base_metres`, a `modifiers` dict of every adjustment that actually fired
(size grading, flare, sleeve/lining/border add-ons, wastage),
`construction_assumptions` (a `ConstructionAssumptions` -- exactly the inputs
the estimate was generated FROM, section 7), `rule_source`, and a `Confidence`
(score + high/medium/low label, never a single fake-precise number).

## MaterialFeasibility / FeasibilityResult (`src/domain/models/feasibility.py`)

`MaterialFeasibilityStatus` is one of `FEASIBLE` / `MARGINAL` / `INSUFFICIENT`
/ `UNKNOWN` (Phase 1.2, section 1C). `FeasibilityResult` is the standalone
`check_fabric_feasibility` tool's output (always a real status, never
`UNKNOWN`, since it always receives an explicit required range).
`MaterialFeasibility` is the candidate-level, flat-schema facet (`status`,
`available_metres`, `required_min_metres`/`required_max_metres`,
`shortage_min_metres`/`shortage_max_metres`, `redesign_options`,
`reasoning`) -- `UNKNOWN` when either no curated consumption rule exists or
no available quantity was given. See docs/rule-engine.md for the thresholds.

## Colorway (`src/domain/models/colorway.py`)

Structured only -- `main_colors` / `supporting_colors` / `metallic_accents` /
`embroidery_colors`, a `harmony_type`, and a `dupatta_direction` string. No image
generation in Phase 1 (section 12); every color relationship is computed via real
HSL math (`src/fashion_engine/colors/color_math.py`), never invented by an LLM.

## RecommendationContext (`src/domain/models/context.py`)

The one shared, optional input to `recommend_silhouettes` / `recommend_fabrics` /
`recommend_styling` / `generate_colorways`: occasion, season, wear-category
preference, size, available fabric, fabric width, and how many results to return.
Every field is optional -- when something isn't given, the kernel states its
assumption rather than blocking (section 18) or silently guessing.
