# Evaluation

## Two layers, two different jobs

1. **`src/tests/` (pytest, 74 tests)** -- unit/integration correctness: does each
   function do what its contract says, does it handle edge cases (unknown fabric,
   unknown garment, no seeded consumption rule, declared-property overrides), does
   the API layer wire requests through correctly. Run with:

   ```bash
   .venv/bin/pytest src/tests -q
   ```

2. **`data/golden/golden_cases.yaml` + `scripts/run_golden_evals.py` (55 cases, 66
   checks)** -- does the fashion intelligence make *sense*? Per section 18: "do
   not just test that functions execute. Test whether recommendations make
   sense." Run with:

   ```bash
   .venv/bin/python scripts/run_golden_evals.py
   ```

   Exits non-zero if any check fails, so it can be wired into CI without being
   pytest itself.

## What the golden cases cover

- **The seven worked scenarios from section 19 of the product brief**, verified
  directly against this kernel's real output (not hand-waved): embroidered organza
  for an engagement suit (structured/A-line rank highest, heavy flare and excess
  embellishment both penalized with named reasons), georgette-Anarkali strong
  compatibility, velvet in summer daytime wear flagged for low season suitability,
  banarasi for a festive lehenga, an insufficient-2.8m-for-a-full-Anarkali
  infeasibility case with redesign options, heavily embroidered organza correctly
  favoring a cocktail dress over a conventional straight kurta, and multiple
  BEST_USE fabric options for an A-line silhouette.
- **A 34-combination sweep** across the fabrics (organza, georgette, chiffon,
  banarasi, velvet, silk, chanderi, tissue, jacquard, cotton, crepe, satin, plus
  kanjivaram, raw silk, net, tulle, linen, lace, brocade, Korean organza),
  silhouettes (straight, A-line, Anarkali, flared, panelled, fitted, structured,
  empire, relaxed, corset, draped), and occasions (wedding_guest, engagement,
  reception, festive, cocktail, daytime, evening) named in section 18.
- **Consumption baselines** matching section 10's worked examples (~1m blouse,
  ~3m A-line, ~5m Anarkali at Medium/44in).
- **Feasibility** at both the ample-fabric and just-short boundary conditions.
- **Colorway harmony selection** (metallic accent on a bold occasion, tonal
  harmony for an already-densely-decorated fabric, analogous harmony for a softer
  occasion).
- **Styling**, including the exact section 9 worked example (embroidered organza
  A-line suit -> three-quarter sleeves, V-neck, moderate flare, a lightweight
  dupatta) reproduced by the real `recommend_styling` output, not asserted by
  hand.

## Why classification tiers, not exact scores

Section 18 is explicit: "do not overfit to exact numeric scores. Test ranges and
relative ranking." Every golden check asserts a `Classification` tier (or a small
set of acceptable tiers) and, where relevant, that a specific reason/risk string
appears -- never a literal score value. This means the rule weights in
`src/fashion_engine/scoring/engine.py:DEFAULT_WEIGHTS` can be tuned later without
every golden case breaking, as long as the *relative* story each case tells (this
pairing is strong, that one is penalized for a stated reason) still holds.

## Regression guard

The sweep cases' expected classifications were captured from this kernel's own
verified output at rule-set version 1
(`data/rules/fabric_silhouette_rules.yaml`'s `version: 1`). If a future rule
change shifts one of these classifications, that's a signal to look at *why* --
either the rule change was correct and the golden case's expectation should be
updated deliberately (bump the rule version, update the case, note the reasoning
in the commit), or the rule change had an unintended side effect on an unrelated
fabric/silhouette pairing.
