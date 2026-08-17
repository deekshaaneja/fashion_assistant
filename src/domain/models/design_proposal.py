"""DesignProposal: a complete, structured outfit design -- never an
unstructured text blob (section 4). Every attribute is independently
addressable so a later agent can modify one field ("make it less
traditional") without regenerating the whole design (section 25).

`DesignCandidate` is the pre-validation shape -- exactly what a
`DesignGenerationProvider` proposes. `DesignProposal` extends it with
everything only deterministic post-processing can add (id, rank, palette,
scores, confidence) -- see docs/design-engine.md.
"""
from __future__ import annotations

from pydantic import Field

from src.domain.enums import (
    DecorationLevel,
    DupattaColorStrategy,
    EmbellishmentType,
    FlareConstruction,
    FlareLevel,
    NecklineType,
    SleeveLength,
    SleeveStyle,
)
from src.domain.models.colorway import ColorSpec
from src.domain.models.common import Confidence, DomainModel
from src.domain.models.consumption import ConsumptionEstimate
from src.domain.models.design_dna import DesignDNA
from src.domain.models.recommendation import GarmentRef, SilhouetteRef


class DesignGarment(DomainModel):
    garment: GarmentRef
    silhouette: SilhouetteRef


class ConstructionSpec(DomainModel):
    bodice_style: str  # descriptive: "fitted", "relaxed", "empire", "corseted"
    panelling: str | None = None  # e.g. "kalidar (gathered triangular panels)", "vertical princess panels"
    waist_placement: str = "natural"  # natural | empire | dropped
    flare_level: FlareLevel
    flare_construction: FlareConstruction
    garment_length: str  # descriptive: "floor_length" | "ankle_length" | "calf_length" | "knee_length"
    hem_treatment: str | None = None
    slit: str | None = None
    rationale: str


class NecklineSpec(DomainModel):
    type: NecklineType
    depth: str | None = None  # "moderate" | "deep" | "high"
    lining_required: bool = False
    rationale: str


class SleeveSpec(DomainModel):
    length: SleeveLength
    style: SleeveStyle = SleeveStyle.STRAIGHT
    sheer: bool = False
    cuff_treatment: str | None = None
    rationale: str


class BottomSpec(DomainModel):
    type: str  # e.g. "churidar", "straight_pants", "flared_skirt", "palazzo"
    fabric_role: str = "main"  # "main" | "supporting"
    rationale: str


class DupattaSpec(DomainModel):
    included: bool
    fabric_role: str | None = None  # "main" | "supporting"
    fabric_description: str | None = None
    weight: str | None = None
    transparency: str | None = None
    color_strategy: DupattaColorStrategy | None = None
    border: str | None = None
    embellishment: str | None = None
    ombre_direction: str | None = None
    rationale: str


class LiningSpec(DomainModel):
    required: bool
    fabric_description: str | None = None
    rationale: str


class DecorationTreatment(DomainModel):
    material: EmbellishmentType
    intensity: str  # "minimal" | "moderate" | "heavy"
    placement: list[str] = Field(default_factory=list)
    reason: str


class DecorationSpec(DomainModel):
    level: DecorationLevel
    treatments: list[DecorationTreatment] = Field(default_factory=list)
    rationale: str


class FinishingSpec(DomainModel):
    seams: str
    notes: list[str] = Field(default_factory=list)


class FabricRole(DomainModel):
    component: str  # "main_garment" | "bottom" | "dupatta" | "lining" | "blouse" | ...
    use_main_fabric: bool = True
    fabric_description: str | None = Field(
        default=None, description="populated when use_main_fabric is False -- a supporting fabric recommendation"
    )
    recommended_properties: dict[str, str] = Field(default_factory=dict)
    rationale: str


class FabricUsageSpec(DomainModel):
    main_fabric_id: str
    components: list[FabricRole] = Field(default_factory=list)
    consumption: ConsumptionEstimate


class ProportionSpec(DomainModel):
    """Output of `recommend_proportions` (section 12) -- descriptive/normalized
    proportion decisions, not exact tailoring measurements."""

    garment_length: str
    waist_placement: str
    flare_level: FlareLevel
    slit: str | None = None
    panel_category: str | None = None  # e.g. "4-panel", "many-panel gathered" -- descriptive, not a pattern spec
    bodice_length: str | None = None  # e.g. "cropped", "hip-length", "full-length"
    sleeve_proportion: str | None = None
    dupatta_scale: str | None = None  # e.g. "standard", "oversized", "narrow scarf-like"
    overlay_length: str | None = None  # jacket/cape length, when the garment has one
    rationale: str


class DesignColorway(DomainModel):
    id: str
    harmony_strategy: str  # a ColorHarmonyType value
    colors: dict[str, ColorSpec] = Field(
        default_factory=dict,
        description="component name -> color, e.g. 'main_garment'/'bottom'/'dupatta'/'lining'",
    )
    ombre_direction: str | None = None
    rationale: str


class DesignScoreBreakdown(DomainModel):
    fabric_design_fit: float = Field(ge=0.0, le=100.0)
    aesthetic_coherence: float = Field(ge=0.0, le=100.0)
    occasion_fit: float = Field(ge=0.0, le=100.0)
    client_brief_fit: float = Field(ge=0.0, le=100.0)
    construction_coherence: float = Field(ge=0.0, le=100.0)
    surface_design_coherence: float = Field(ge=0.0, le=100.0)
    color_coherence: float = Field(ge=0.0, le=100.0)
    originality: float = Field(ge=0.0, le=100.0)
    overall: float = Field(ge=0.0, le=100.0)
    trace: dict[str, list[str]] = Field(default_factory=dict)


class ConstructionCreative(DomainModel):
    """Model-facing subset of `ConstructionSpec` -- everything except
    `flare_level`/`flare_construction`, which are forced from
    `DesignConstraints` (never left to the model) by `assemble_candidate`."""

    bodice_style: str
    panelling: str | None = None
    waist_placement: str = "natural"
    garment_length: str
    hem_treatment: str | None = None
    slit: str | None = None
    rationale: str


class NecklineCreative(DomainModel):
    """Model-facing subset of `NecklineSpec` -- `lining_required` is forced
    from `DesignConstraints`, never asked of the model."""

    type: NecklineType
    depth: str | None = None
    rationale: str


class DupattaCreative(DomainModel):
    """Model-facing subset of `DupattaSpec` -- weight/transparency/border/
    embellishment/ombre_direction are left to deterministic assembly."""

    included: bool
    fabric_role: str | None = None
    fabric_description: str | None = None
    color_strategy: DupattaColorStrategy | None = None
    rationale: str


class DecorationCreative(DomainModel):
    """Model-facing subset of `DecorationSpec` -- `treatments` are always
    derived deterministically from the (clamped) level, never generated."""

    level: DecorationLevel
    rationale: str


class SupportingFabricSuggestion(DomainModel):
    component: str  # "lining" | "dupatta" | "blouse" | ...
    fabric_description: str
    rationale: str


class GeneratedDesignContent(DomainModel):
    """The ONLY shape a `DesignGenerationProvider` asks the model for
    (section 3, Phase 2 performance fix). Excludes every field that is
    deterministic or application-derived -- garment/silhouette (already known
    from the request), flare_level/flare_construction/lining_required
    (forced from constraints), decoration.treatments, lining, finishing,
    fabric_usage.consumption, scores, confidence, validation metadata. See
    `assemble_candidate` for how this is combined with deterministic data
    into a full `DesignCandidate`."""

    title: str
    design_intent: str
    construction: ConstructionCreative
    neckline: NecklineCreative
    sleeves: SleeveSpec
    bottom: BottomSpec | None = None
    dupatta: DupattaCreative | None = None
    decoration: DecorationCreative
    supporting_fabrics: list[SupportingFabricSuggestion] = Field(default_factory=list)
    design_dna: DesignDNA
    rationale: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DesignCandidate(DomainModel):
    """Pre-validation shape -- exactly what a `DesignGenerationProvider`
    proposes, before deterministic validation/scoring/coloring runs."""

    title: str
    design_intent: str
    garment: DesignGarment
    design_dna: DesignDNA
    construction: ConstructionSpec
    neckline: NecklineSpec
    sleeves: SleeveSpec
    bottom: BottomSpec | None = None
    dupatta: DupattaSpec | None = None
    lining: LiningSpec | None = None
    decoration: DecorationSpec
    finishing: FinishingSpec
    fabric_usage: FabricUsageSpec
    rationale: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DesignProposal(DesignCandidate):
    """The final, validated, scored, ranked design direction -- the only
    object `generate_design_directions` returns to a caller."""

    id: str
    rank: int
    palette: DesignColorway | None = None
    scores: DesignScoreBreakdown
    confidence: Confidence
    validation_notes: list[str] = Field(default_factory=list)


class EnsembleComponent(DomainModel):
    component: str  # "main_garment" | "bottom" | "dupatta" | "blouse" | "jacket" | "cape" | "overlay" | "lining"
    included: bool
    fabric_role: str  # "main" | "supporting" | "not_applicable"
    description: str
    rationale: str


class DesignEnsemble(DomainModel):
    components: list[EnsembleComponent] = Field(default_factory=list)
    rationale: str
