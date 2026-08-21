"""Phase 4, visualization domain models: `DesignProposal` + the original
fabric image(s) + `FabricProfileWithProvenance` -> a `VisualizationSpecification`
(a rendering PROJECTION of `DesignProposal`, never a second independent
garment representation -- section 47) -> a provider call -> a persisted
`VisualizationResult`.

The structured system remains authoritative (section 2): nothing here ever
writes back into `DesignProposal`. If a generated image disagrees with the
specification, the image is what's wrong.
"""
from __future__ import annotations

from enum import Enum

from pydantic import Field

from src.domain.enums import (
    DecorationLevel,
    DupattaColorStrategy,
    FlareConstruction,
    FlareLevel,
    NecklineType,
    SleeveLength,
    SleeveStyle,
    SurfaceDensity,
    Transparency,
)
from src.domain.models.common import DomainModel
from src.domain.models.fabric_vision import EvidenceType, ImageRole

# --- Request-level vocabulary ---------------------------------------------


class PresentationMode(str, Enum):
    """Section 6-7: MANNEQUIN is the default for design evaluation --
    a glamorous model shot distracts from judging fabric/construction
    accuracy, which is what a boutique owner actually needs first."""

    MANNEQUIN = "mannequin"
    MODEL = "model"
    FLAT = "flat"


class ViewAngle(str, Enum):
    """Section 41: front view only for Phase 4 -- back/side/turntable are
    explicitly out of scope, not silently unsupported."""

    FRONT = "front"


class VisualizationQuality(str, Enum):
    CONCEPT = "concept"


class VisualizationOptions(DomainModel):
    """The user-level ask (section 5) -- everything else needed to render is
    derived from the `DesignProposal`/`FabricProfileWithProvenance` supplied
    alongside it, never re-declared here."""

    view: ViewAngle = ViewAngle.FRONT
    presentation: PresentationMode = PresentationMode.MANNEQUIN
    quality: VisualizationQuality = VisualizationQuality.CONCEPT
    count: int = Field(default=1, ge=1, le=3)


# --- VisualizationSpecification (sections 4, 47) --------------------------


class SubjectSpec(DomainModel):
    presentation: PresentationMode
    pose: str = "standing, arms relaxed at sides"
    view: ViewAngle = ViewAngle.FRONT


class GarmentSpec(DomainModel):
    category: str  # garment id, e.g. "suit"
    category_name: str
    silhouette: str  # silhouette id, e.g. "anarkali"
    silhouette_name: str


class ConstructionVisualSpec(DomainModel):
    """A rendering-facing projection of `ConstructionSpec` -- same facts,
    described so a visualization provider (or a human reading the spec) can
    act on them without needing the full Phase 2 domain model."""

    bodice: str
    panelling: str | None = None
    waist: str
    flare_level: FlareLevel
    flare_construction: FlareConstruction
    length: str
    hem: str | None = None
    slit: str | None = None


class NecklineVisualSpec(DomainModel):
    type: NecklineType
    depth: str | None = None


class SleevesVisualSpec(DomainModel):
    length: SleeveLength
    style: SleeveStyle
    sheer: bool = False
    cuff_treatment: str | None = None


class BottomVisualSpec(DomainModel):
    type: str
    fabric_role: str = "main"


class DupattaVisualSpec(DomainModel):
    included: bool
    fabric_role: str | None = None
    transparency: str | None = None
    color_strategy: DupattaColorStrategy | None = None
    border: str | None = None
    embellishment: str | None = None
    ombre_direction: str | None = None


class DecorationTreatmentVisualSpec(DomainModel):
    material: str
    intensity: str
    placement: list[str] = Field(default_factory=list)


class DecorationVisualSpec(DomainModel):
    level: DecorationLevel
    treatments: list[DecorationTreatmentVisualSpec] = Field(default_factory=list)


class MaterialFabricSummary(DomainModel):
    """A compact, design-relevant slice of a fabric's declared properties --
    never the full `FabricProperties` object, and never GSM/width/stretch
    (Phase 3 leaves those unknown from a photograph; nothing here should
    look more precise than what's actually known)."""

    dominant_color: str | None = None
    transparency: Transparency | None = None
    sheen: str | None = None
    surface_density: SurfaceDensity | None = None
    motif_family: str | None = None
    motif_directional: bool | None = None
    border_present: bool | None = None


class MaterialReference(DomainModel):
    """Section 23: explicit material ROLES so a renderer never covers every
    component in the hero fabric merely because only one reference image
    exists. `source_image_ids` is empty for a supporting fabric that only
    has a text description (e.g. "soft crepe lining") -- there is no
    photograph of it to reference."""

    role: str  # "hero_fabric" | "lining" | "bottom" | "dupatta" | ...
    use_hero_fabric: bool
    source_image_ids: list[str] = Field(default_factory=list)
    fabric_description: str | None = None
    fabric_summary: MaterialFabricSummary | None = None


class PreservationRequirements(DomainModel):
    """Section 12, 20-22: explicit, structured fabric-fidelity asks --
    never buried in prose the provider might drop."""

    preserve_color: bool = True
    preserve_motif: bool = True
    preserve_surface_work: bool = True
    preserve_border: bool = True
    preserve_transparency: bool = True
    motif_directional: bool = False
    border_placement: list[str] = Field(default_factory=list)  # e.g. ["hem", "dupatta_edge"]
    lined_components: list[str] = Field(default_factory=list)  # e.g. ["main_garment"]
    unlined_sheer_components: list[str] = Field(default_factory=list)  # e.g. ["sleeves"]


class PaletteVisualSpec(DomainModel):
    harmony_strategy: str | None = None
    colors: dict[str, str] = Field(default_factory=dict)  # component -> color name/hex


class VisualizationSpecification(DomainModel):
    """The canonical, provider-independent rendering projection of a
    `DesignProposal` (section 47) -- the ONLY thing a
    `DesignVisualizationProvider` is asked to render. Never a second
    fashion-design domain: every field here traces back 1:1 to
    `DesignProposal`/`FabricProfileWithProvenance` fields."""

    design_id: str
    subject: SubjectSpec
    garment: GarmentSpec
    construction: ConstructionVisualSpec
    neckline: NecklineVisualSpec
    sleeves: SleevesVisualSpec
    bottom: BottomVisualSpec | None = None
    dupatta: DupattaVisualSpec | None = None
    decoration: DecorationVisualSpec
    materials: list[MaterialReference] = Field(default_factory=list)
    palette: PaletteVisualSpec | None = None
    preservation_requirements: PreservationRequirements = Field(default_factory=PreservationRequirements)


# --- Fabric reference selection (section 11) ------------------------------


class SelectedFabricReference(DomainModel):
    image_id: str
    role: ImageRole
    reason: str


class FabricReferenceSelection(DomainModel):
    selected: list[SelectedFabricReference] = Field(default_factory=list)
    excluded_image_ids: list[str] = Field(default_factory=list)
    max_references: int


# --- Phase 4.1: staged fabric-to-look visualization -----------------------


class VisualizationStage(str, Enum):
    """Section 2: three narrow stages instead of one call solving fabric
    identity + garment invention + full design transformation at once."""

    MATERIAL_REFERENCE = "material_reference"
    BASE_GARMENT = "base_garment"
    DESIGN_TRANSFORMATION = "design_transformation"


class ProviderCapability(str, Enum):
    """Section 15: a provider advertises what it can do -- no single
    provider is assumed to implement every stage."""

    FABRIC_REFERENCE_PREPARATION = "fabric_reference_preparation"
    GARMENT_COMPOSITION = "garment_composition"
    IMAGE_EDIT = "image_edit"
    REFERENCE_CONDITIONED_GENERATION = "reference_conditioned_generation"


class MaterialReferenceType(str, Enum):
    """Section 6: never assume a fabric is tileable -- directional
    embroidery, placement motifs, large repeats, and borders can all be
    destroyed by forcing a seamless tile."""

    SURFACE_REFERENCE = "surface_reference"
    TILEABLE_REFERENCE = "tileable_reference"


class FabricSurfaceReference(DomainModel):
    """One entry in a `FabricMaterialReference` -- section 5. `generated`
    is False for the large majority of cases (section 4: prefer the actual
    photograph, deterministically prepared, over generative cleanup)."""

    role: ImageRole
    reference_type: MaterialReferenceType = MaterialReferenceType.SURFACE_REFERENCE
    asset_id: str
    source_image_id: str
    generated: bool = False


class FabricMaterialReference(DomainModel):
    """Stage 1 output (section 3, 5): a clean, reusable visual
    representation of the actual supplied textile -- never a replacement
    for the original photographs, which remain available via
    `source_image_id` on each reference."""

    id: str
    references: list[FabricSurfaceReference] = Field(default_factory=list)
    fabric_summary: MaterialFabricSummary | None = None
    warnings: list[str] = Field(default_factory=list)


# --- Visual validation (sections 15-19) -----------------------------------


class ValidationVerdict(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class VisualValidationCheck(DomainModel):
    category: str  # "design" | "fabric"
    name: str
    verdict: ValidationVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    detail: str


class GeneratedImageObservation(DomainModel):
    """Section 16: the ONLY shape asked of the vision model when analyzing a
    GENERATED image -- "what is visibly present," never "is this a good
    design." Deliberately as compact as Phase 3's `VisionModelOutput` for
    the same reason (section 24 of the Phase 3 brief -- never a giant
    schema asking a model to also judge/compute)."""

    garment_subject: str | None = None  # free text, e.g. "anarkali suit"
    neckline: str | None = None
    sleeve_length: str | None = None
    sleeve_style: str | None = None
    dupatta_present: bool | None = None
    dominant_color: str | None = None
    surface_density: str | None = None
    border_present: bool | None = None
    transparency: str | None = None
    reason: str = ""


class VisualValidationResult(DomainModel):
    overall: ValidationVerdict
    checks: list[VisualValidationCheck] = Field(default_factory=list)
    observation: GeneratedImageObservation | None = None
    corrective_regeneration_attempted: bool = False
    warnings: list[str] = Field(default_factory=list)


# --- Result (sections 26, 48) ---------------------------------------------


class VisualizationImage(DomainModel):
    id: str
    uri: str  # stable application reference (asset-store path), never a raw provider URL
    view: ViewAngle
    presentation: PresentationMode
    width: int | None = None
    height: int | None = None
    # Phase 4.1, sections 13, 31: explicit lineage -- which stage produced
    # this image and what it was built from, so a future conversational
    # edit ("change just the neckline") can target the right prior asset
    # instead of regenerating everything.
    stage: VisualizationStage | None = None
    parent_asset_id: str | None = None
    edit_depth: int = 0


class VisualizationGenerationMetadata(DomainModel):
    provider: str
    model: str | None = None
    strategy: str  # "reference_conditioned" | "text_only" | "mock"
    attempts: int = 1
    corrective_regenerations: int = 0
    reference_image_ids: list[str] = Field(default_factory=list)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    provider_error: str | None = None
    provider_error_code: str | None = None
    capability_used: ProviderCapability | None = None
    # Cost telemetry (Phase 4 finalization) -- `estimated_cost_usd` is
    # always an ESTIMATE (see the provider's per-call pricing constant),
    # never a real billed amount from the provider's own usage API, which
    # none of the evaluated providers expose per-image.
    quality: VisualizationQuality | None = None
    resolution: str | None = None
    estimated_cost_usd: float | None = None


class VisualizationResult(DomainModel):
    id: str
    design_id: str
    fabric_name: str
    fabric_identity_evidence_type: EvidenceType | None = None
    images: list[VisualizationImage] = Field(default_factory=list)
    specification: VisualizationSpecification
    fabric_references: FabricReferenceSelection
    validation: VisualValidationResult
    generation_metadata: VisualizationGenerationMetadata
    # Phase 4.1, section 13, 48: traceability back to the Stage 1 material
    # reference this result was ultimately built from.
    source_fabric_reference_id: str | None = None
    disclaimer: str = (
        "This is a DESIGN CONCEPT VISUALIZATION, not an exact production preview. Motif placement, scale, "
        "color, and construction detail may differ from the finished garment."
    )
