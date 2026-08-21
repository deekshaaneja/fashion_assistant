# Design Visualization Engine (Phase 4)

Phase 1-3 answer "what should I make, and from what fabric?" Phase 4 answers
"what could this specific design look like when made from this specific
fabric?" -- a design CONCEPT visualization, never an exact production
preview, and never the source of truth (the structured `DesignProposal` +
`FabricProfile` remain authoritative; a generated image that disagrees with
them is the thing that's wrong, not the other way around).

## MVP rendering architecture (decided after the Phase 4.1 provider spike)

```
FabricMaterialReference (built once from the ORIGINAL Phase 3 fabric photos)
        +
current DesignProposal
        v
fresh Gemini render
        v
VisualizationResult
```

**Every visualization is an independent fresh render from the original
fabric reference + the current `DesignProposal`.** Changing a design
attribute (V1 -> V2 -> V3) means calling `visualize_design()` again with the
updated `DesignProposal` -- it never edits or chains from a previously
generated image. This is deliberate, not an oversight: see "Why rebuild
instead of edit" below.

`src/fashion_engine/visualization/pipeline.py::visualize_design()` is this
canonical path:

```
DesignProposal + fabric image(s) + FabricProfile + VisualizationOptions
      |
fabric reference selection   (reference_selector.py -- role priority, usable/non-duplicate only)
      |
VisualizationSpecification   (spec_builder.py -- pure projection of DesignProposal, section 47)
      |
DesignVisualizationProvider.generate()   (ALWAYS conditioned on the ORIGINAL fabric photos)
      |
asset storage                (asset_store.py -- stable app reference, never a raw provider URL)
      |
visual validation            (visual_validate.py -- compact vision-model observation vs. spec)
      |
at most one bounded corrective regeneration, only on a hard validation FAIL
      |
VisualizationResult
```

## Provider evaluation summary

Four providers were investigated empirically (never assumed from
documentation alone) before choosing one:

| Provider | Model | Outcome |
|---|---|---|
| Aliyun DashScope | `qwen-image-edit` | Accepts well-formed requests (validated 1-3 reference images, single-message-only constraint), but every image-capable model tried returned HTTP 200 with **no image payload** on this account. Not proven functional. |
| OpenAI | `gpt-image-1` | Valid key, but the account has **no billing credits** (`insufficient_quota`). Untested beyond that. |
| Google Gemini | `gemini-2.5-flash-image` | Free tier returns `RESOURCE_EXHAUSTED` (`limit: 0`) for every image model -- a billing/quota gate, not a capability finding. **Once paid billing was enabled on a correctly-scoped API key, this became the accepted MVP provider** (see acceptance results below). |
| fal.ai | `fal-ai/flux-pro/kontext` | Technically capable (4 successful real generations, strong fabric-identity preservation) but requires a $25 minimum top-up. **Not required for MVP** given Gemini's acceptance results -- kept configured behind `ImageEditCapableProvider` for a future provider need, never the MVP default. |

## Real-image acceptance results (organza anchor)

Ran against the real embroidered-organza Phase 3 evaluation photos, blind
(fabric identity resolved by Phase 3's own vision inference, never leaked
from the eval folder name).

- **Fabric transfer** (fabric photo -> simple garment): PASS -- color, rose/
  leaf motif, motif scale, striped embroidery character, sequin/sparkle
  detail, surface density, and semi-sheer transparency were all
  recognizably preserved.
- **Precise design-geometry edit via iterative image editing** (asking the
  model to edit an already-generated image's neckline from round to
  square): **FAILED twice**, including one corrective attempt with
  explicit geometric criteria. Fabric/design/scene preservation around the
  edit was excellent -- the model simply never executed the structural
  change in-place.
- **Full rebuild from the original fabric reference + an updated
  `DesignProposal` (square neckline)**: **PASSED** -- exact target geometry
  achieved (unmistakably square neckline: straight lower edge, vertical
  sides, squared corners), fabric identity fully recognizable. The first
  rebuild attempt showed measurable color-darkening and reduced
  transparency (traced to the prompt splitting the transparency
  instruction into a separate "opaque layer" sentence instead of one
  unified fabric-preservation clause); restoring the unified phrasing
  resolved both in a second attempt.

This directly validated the MVP decision: **rebuild-per-design-version,
never in-place image editing.**

## Why rebuild instead of edit

Localized in-place image editing (take a previously generated image, ask
the model to change one attribute) was tested and failed on precise
garment-structure edits (round -> square neckline), twice, even when the
edit was stated as the sole objective with explicit geometric criteria.
Fresh rebuild from the original fabric photo + the current `DesignProposal`
sidesteps this entirely, because it never asks the model to locate and
modify a region of an existing image -- it asks the model to do the thing
it already does well (fabric photo -> garment matching a description),
just with a different description each time. At the observed
~$0.04/image, this is also cheap enough that cost is not a reason to
prefer editing (an initial visualization + 2 revisions is roughly $0.12).

**Localized image editing is deferred, not deleted.** The staged
abstractions (`material_reference.py`, `base_composition.py`,
`design_transformation.py`, `staged_pipeline.py`, `ImageEditCapableProvider`,
`FalKontextVisualizationProvider`) remain in the codebase and are fully
tested, but are **not** the MVP default path -- they exist for a future
provider/use case that specifically needs in-place editing (e.g. a
conversational "just change the neckline" flow with a provider proven
capable of that), and should not be revived without new evidence that a
specific provider can do it reliably.

## Provider configuration

```
VISUALIZATION_PROVIDER=auto      # auto prefers gemini > fal > aliyun (if enabled) > mock
GEMINI_API_KEY=...
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
FAL_KEY=...                      # optional, not required for MVP
VISUALIZATION_MODEL=qwen-image-edit   # Aliyun, kept but not proven functional
```

Mirrors every other provider in the kernel: `mock` for deterministic
testing, an explicit provider name to force a specific live path, `auto` to
let configured credentials decide.

## Fabric-preservation instruction

There is exactly ONE canonical fabric-preservation instruction --
`fabric_preservation_instruction()` in `spec_builder.py` -- used by the MVP
path's prompt builder. It encodes two lessons from the acceptance
experiment: keep color/motif/embroidery/density/sheen/transparency as one
unified clause (splitting transparency into a separate "opaque layer"
sentence measurably darkened the perceived fabric color as a side effect),
and state an explicit anti-darkening/neutral-lighting constraint. Do not
add a second, competing fabric-preservation prompt elsewhere -- if the
wording needs to change, change it here.

## Cost telemetry

`VisualizationGenerationMetadata` records `provider`, `model`, `quality`,
`estimated_cost_usd` (an ESTIMATE from `GEMINI_ESTIMATED_COST_PER_IMAGE_USD`/
`FAL_ESTIMATED_COST_PER_IMAGE_USD`, never a real billed figure -- neither
provider exposes a per-image usage API), `attempts`, `corrective_regenerations`,
and per-stage `timing_ms`. `VisualizationResult.design_id` identifies which
`DesignProposal` (version) a given render belongs to.

## Explicitly deferred / out of scope

- Localized in-place image editing as a default path (see above).
- fal.ai / any specialized virtual-try-on provider -- not required given
  current acceptance evidence; would need a new capability gap to justify.
- Georgette real-image acceptance for the rebuild-per-version path
  (organza-only was sufficient to validate the architecture decision).
- Multi-view consistency (front/back/side), video, 3D garments.
- Virtual try-on, customer photographs, body reconstruction.
- Conversational/agent-driven editing (the rebuild-per-version pattern is
  designed to support it later, but no chat/agent layer exists yet).
