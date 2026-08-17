# Rule Engine

## Where rules live

Per section 14 of the product brief: "build rules as data/configuration where
practical. Do not scatter hundreds of fabric-specific conditions across application
code." Two layers:

1. **General property-based rules** -- `data/rules/fabric_silhouette_rules.yaml`.
   Each rule matches on FABRIC properties (drape, stiffness, structure,
   transparency, sheen, embellishment_tolerance, surface_density) and/or
   SILHOUETTE properties (structure_affinity, default_flare_level,
   aesthetic_tags), and contributes a score delta + a human-readable reason when
   it fires. These are genuinely general -- e.g. "a crisp/stiff fabric at dramatic
   flare risks reading bulky" applies to *any* fabric with that property
   combination, not to one named fabric. This is the mechanism that lets the
   kernel reason about a fabric it has never seen a named rule for.
2. **Curated per-fabric anchors** -- `Fabric.strong_fit_silhouettes` /
   `avoid_silhouettes` in `data/seed/fabrics.yaml`. A small number of
   well-established pairings (e.g. "banarasi suits a flared/panelled lehenga")
   that domain expertise says should be pinned regardless of what the general
   rules alone would produce. These layer *on top of*, not instead of, the general
   rules -- see `score_fabric_silhouette` in `src/rules/compatibility.py`.

Both layers are versioned (`version: 1` at the top of the rules YAML) and
evaluated by one small, pure, fully-tested function
(`src/rules/compatibility.py:score_fabric_silhouette`) -- there is no rule logic
duplicated anywhere else. Bump the version and add new rules with their own `id`
rather than mutating an existing rule's meaning in place, so a golden-case run
against a known rule version stays reproducible.

## Inspectability

Every `SilhouetteCandidate`/`FabricCandidate` carries `source_rules: list[str]` --
the exact rule ids (plus `curated_strong_fit_anchor`/`curated_avoid_anchor` for the
per-fabric layer) that fired for that candidate. Nothing about a score is opaque;
a boutique owner (or a future agent) can always ask "why" and get back named rules,
not a black-box number.

## Three questions, not one (`src/fashion_engine/scoring/engine.py`)

Phase 1.2 replaced a single blended six-component score with three explicit,
never-blended questions (`evaluate_candidate`'s return shape,
`SilhouetteCandidate`/`FabricCandidate` in `src/domain/models/recommendation.py`):

1. **Design suitability** -- is this fabric+garment+silhouette combination
   intrinsically good, independent of who it's for or what's in stock?
2. **Context suitability** -- does it suit *this* consultation (occasion,
   wear-category preference, season)?
3. **Material feasibility** -- can it actually be cut from the fabric on
   hand right now?

Mixing these into one number was the root cause of a specific, real bug: an
A-line suit that's an excellent design but merely short a metre of fabric
used to score as if the *design itself* were mediocre. Keeping them separate
lets the kernel say "this is a great design, appropriate for the occasion,
but you don't have enough fabric" instead of collapsing all three judgments
into a single misleading number.

### Design suitability

Occasion/consultation-independent by construction -- these two components
never change when the caller changes occasion, season, or available metres:

| Component | Weight | What it measures |
|---|---|---|
| `fabric_compatibility` | 0.65 | The rule-engine score above: does this fabric's own material properties suit this silhouette's construction? |
| `construction_practicality` | 0.35 | Real tailoring friction: heavy fabric in a fitted cut, directional motif at the *effective* flare level, no-stretch fabric in a body-conscious cut. |

### Context suitability

Entirely consultation-dependent -- every component here is *omitted* (not
defaulted to a neutral score) when its underlying input wasn't given:

| Component | Weight | What it measures |
|---|---|---|
| `occasion_fit` | 0.35 | Does the garment fit the stated occasion? Omitted if no occasion given. |
| `wear_category_fit` | 0.20 | Does the garment's wear category (Indian/Western/fusion) match the caller's stated preference? Omitted if no preference given. |
| `season_fit` | 0.15 | Does the fabric suit the stated season? Omitted if no season given. |
| `formality_fit` | 0.30 | Does the fabric's own formality (sheen, surface density) plus the silhouette's aesthetic character already read appropriately for the stated occasion, or does it lean understated? Omitted if no occasion given (the old, single-score "styling_coherence" -- this is genuinely occasion-dependent, so it belongs here, not in design suitability). |

When a component is omitted, its weight is *not* redistributed as a penalty
-- `_weighted_score` renormalizes the remaining weights among whatever
components are actually present, so "no season given" never quietly drags
the score down the way a fabricated neutral default would.

`formality_fit` deliberately does not read `embellishment_tolerance` at all
(see "Decoration is not occasion-driven" below) -- occasion only ever
affects formality *fit*, never how much surface decoration a design should
carry.

Both `DESIGN_SUITABILITY_WEIGHTS` and `CONTEXT_SUITABILITY_WEIGHTS` are
module-level constants, not inlined into the scoring function.

### Effective flare level and flare construction (section 9)

A silhouette has both a `default_flare_level` (how much) and a
`flare_construction` (how the volume is built -- `controlled`, `gathered`,
or `dramatic`; see `src/domain/enums.py`). These behave very differently: a
crisp/stiff fabric is *excellent* for **controlled** volume (panel/godet-built,
held by the cut -- its own body gives clean architectural lines) but poor
for **gathered**/**dramatic** volume (needs some drape to move rather than
stand). `fabric_silhouette_rules.yaml` v2 encodes this directly
(`structured_fabric_suits_controlled_flare` is a positive rule; the
crisp/stiff-vs-flare penalty rules only fire for `gathered`/`dramatic`).
`_effective_flare_level` only tones the recommended flare down when the
fabric can't support GATHERED/DRAMATIC volume, states why (`assumptions`),
and feeds the *toned-down* level into both the consumption estimate and
`construction_practicality`.

### Classification thresholds and hard gates

Fixed, non-overlapping thresholds map a blended design+context score to a raw
tier (`classify_score`) -- never a hedge across tiers:

```
score >= 75  -> BEST_USE
score >= 55  -> GOOD_ALTERNATIVE
score >= 35  -> POSSIBLE_NOT_IDEAL
otherwise    -> AVOID
```

The blend (`RECOMMENDATION_WEIGHTS`, 0.6 design / 0.4 context) is used ONLY
for this raw threshold step -- material feasibility never enters
`classify_recommendation` (section 2/3). That raw tier is not sufficient by
itself: `classify_recommendation` additionally requires each component in
`BEST_USE_MIN_COMPONENTS` / `GOOD_ALTERNATIVE_MIN_COMPONENTS` (module-level,
configurable) to clear its own floor -- omitted components never gate
anything -- downgrading one tier per failed gate. On top of that, a
**critical floor**: a curated avoid-anchor firing, or `fabric_compatibility`
at or below `CRITICAL_FABRIC_COMPATIBILITY_FLOOR` (25.0), forces `AVOID`
outright regardless of how strong everything else scores (section 5: "do not
allow arithmetic averaging to hide serious incompatibility").

### Material feasibility and actionability (sections 1C, 2, 3)

`MaterialFeasibility` (`src/domain/models/feasibility.py`) is entirely
separate from `recommendation_classification` and never downgrades it.
Status is one of `FEASIBLE` / `MARGINAL` / `INSUFFICIENT` / `UNKNOWN` --
`UNKNOWN` covers both "no curated consumption rule exists" and "no available
quantity was given," since neither lets feasibility be honestly claimed
either way.

`actionability` (`Actionability` enum) is the separate, practical "what
should the client do next" signal, derived from classification *and*
feasibility together: `AVOID` always means `NOT_RECOMMENDED` regardless of
feasibility (a design that shouldn't be made isn't more attractive just
because you happen to have the fabric); otherwise `UNKNOWN` feasibility means
`REQUIRES_MISSING_INFORMATION`, `INSUFFICIENT` means
`REQUIRES_ADDITIONAL_FABRIC`, `MARGINAL` means `REQUIRES_DESIGN_MODIFICATION`,
and `FEASIBLE` means `READY_TO_MAKE`.

### Ranking policy (section 4)

`recommend_silhouettes`/`recommend_fabrics` sort candidates by, in order:

1. `recommendation_classification` (BEST_USE first)
2. `design_suitability.score`
3. `context_suitability.score`
4. `actionability` (closer to READY_TO_MAKE ranks higher -- `actionability_rank`)
5. `confidence.overall`

This is deliberately not a single blended-score sort. A structurally
excellent design that's merely short a metre of fabric still outranks a
design that's simply worse (classification/design/context dominate), while a
similarly strong and immediately feasible design can reasonably outrank a
fabric-short one once classification, design, and context are tied
(actionability breaks the tie). Ranking only happens after every candidate
has a complete evaluation -- classification, both suitability scores,
feasibility, and confidence are all finalized first, then the sort runs once.

### Decoration is not occasion-driven

Section 6: Occasion (garment formality, scored above) and surface decoration
amount are separate decisions. `_decoration_intensity`
(`src/fashion_engine/styling/recommend.py`) is driven by the fabric's own
`surface_density`/`embellishment_tolerance`: already-dense or low-tolerance
fabrics get `restrained` decoration; `heavy` decoration requires *both* high
tolerance *and* some existing surface interest (`surface_density != "none"`).
Occasion only narrows the low end (keeping `daytime` restrained absent high
tolerance) -- it never on its own escalates a plain, low-surface-interest
fabric to `heavy` just because the occasion is formal. A plain wedding-guest
georgette suit is expected to land on `moderate`, not `heavy`.

## Consumption arithmetic (`src/fashion_engine/consumption/calculate.py`)

Deterministic, seeded-rule-driven: `base_metres` graded by size step, adjusted for
requested flare vs. the silhouette's natural flare, scaled for narrower-than-reference
fabric width, plus lining/sleeve/border add-ons and a wastage allowance (bumped
further for a declared directional motif).

**No fabricated fallback range** (Phase 1.2, section 6): when no seeded rule
exists for a `(garment, silhouette)` pair, `calculate_consumption` returns
`status: NO_CURATED_RULE` with `min_metres`/`max_metres` both `None` --
explicitly unknown, not a wide guessed band. Downstream, this makes
`material_feasibility.status` `UNKNOWN` rather than silently comparing
available fabric against a number that was never trustworthy in the first
place. See `test_no_seeded_rule_returns_explicit_unknown_not_a_fabricated_range`.

When a rule *is* used, the estimate exposes exactly what it was generated
FROM (section 7) via `construction_assumptions`
(`ConstructionAssumptions` -- `fabric_width_cm`, `size`, `flare_level`,
`sleeve_allowance_included`, `lining_included`, `border_included`,
`directional_motif`, `wastage_percent`) plus a `modifiers` dict of every
numeric adjustment that actually fired (`size_grading_pct`,
`flare_adjustment_pct`, `sleeve_m`, `lining_m`, `border_m`, `wastage_pct`).
The min/max band narrows as the underlying rule's own `confidence` rises
(`_MIN_BAND_PCT`/`_BAND_SPREAD_PCT`), and displayed metres are always rounded
to one decimal place (section 8: "remove false precision" -- a range like
"10.28-10.76m" claims more precision than a boutique estimate has).

Each `ConsumptionRule` (`data/seed/consumption_rules.yaml`) carries a `source`
tag: `seed` (a rough starting assumption, not independently verified),
`curated` (cross-checked against a named real-world reference point -- here,
the product brief's own worked examples for blouse/A-line-suit/Anarkali), or
`boutique_override` (supplied by a specific boutique). This provenance
(`rule_source` on the estimate) is never presented as more certain than it
is -- it feeds directly into `ConfidenceBreakdown.consumption` below.

## Confidence (`ConfidenceBreakdown`, `_aggregate_confidence`)

Phase 1.2, section 12: confidence is not one number -- design/context fit can
be well-evidenced even when the yardage estimate is a shaky fallback, and
vice versa. `ConfidenceBreakdown` carries four values: `design_suitability`
(fabric resolution confidence + whether a compatibility rule fired),
`context_suitability` (whether occasion/season/wear-category preference were
given), `consumption` (the consumption rule's own confidence, genuinely low
for `NO_CURATED_RULE`), and `overall` (their average). A rule matching is one
input among several, never a stand-in for ~95% confidence.

## Feasibility (`src/fashion_engine/feasibility/check.py`)

`available_metres >= required_range.min` -> `FEASIBLE`. Within 0.3m of the minimum
-> `MARGINAL` with a small design-adjustment suggestion. Otherwise
`INSUFFICIENT`, with a `shortage_range` and a rule-based, non-LLM list of redesign
options (reduce flare, use a complementary fabric for lining/lower panels, move to
a lower-volume silhouette, use a contrast dupatta/sleeve fabric) -- prioritizing
the flare-reduction option first when the candidate's high flare is itself the main
driver of the shortage. This standalone tool always receives an explicit required
range from its caller, so it never itself returns `UNKNOWN` -- that status only
arises one level up, in `MaterialFeasibility`, before a required range can even be
computed (see "Material feasibility and actionability" above).

## Colorway harmony selection (`src/fashion_engine/colors/generate.py`)

Deterministic occasion -> harmony-type mapping (bold occasions lean complementary/
metallic+base, softer occasions lean analogous, an already-densely-decorated fabric
always gets a calm tonal palette regardless of occasion). The actual color values
are computed via real HSL rotation/lightness-shift math
(`src/fashion_engine/colors/color_math.py`) -- an LLM is never asked to invent a
hue relationship.
