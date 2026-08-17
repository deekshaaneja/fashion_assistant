"""Phase 3, visual fabric intelligence: fabric photograph(s) in, structured
evidence + a canonical `FabricProfile` out (SEE -> UNDERSTAND, section 51's
final principle). The vision layer supplies evidence to Phase 1/2 -- it
never bypasses them.

Two distinct schema layers live here, deliberately kept separate (section
24 -- do not repeat the Phase 2 mistake of asking a model to generate one
huge object):

- `VisionModelOutput` (+ its `Vision*Out` helpers) is the ONLY shape asked
  of the vision model itself: compact, flat, no nested Evidence/Confidence
  scaffolding, a plain `certainty` self-rating instead of a fabricated
  precise float.
- `FabricVisionObservation` (+ `Evidence`, `ObservedColor`, etc.) is the
  fused, normalized result APPLICATION CODE builds from one or more
  `VisionModelOutput`s -- this is what carries observed/inferred/
  user_confirmed/unknown provenance and confidence (section 3-4).

Every property is tagged with an `EvidenceType` -- nothing here is
hallucinated certainty; an unknown property stays `None` with an UNKNOWN
evidence entry rather than a guessed value that would look authoritative
downstream (mirrors `FabricProperties`'s own existing philosophy)."""
from __future__ import annotations

from enum import Enum

from pydantic import Field

from src.domain.models.common import DomainModel
from src.domain.models.fabric import FabricProperties

# --- Shared vocabulary -------------------------------------------------


class ImageRole(str, Enum):
    FULL_VIEW = "full_view"
    CLOSE_UP = "close_up"
    BORDER = "border"
    REVERSE = "reverse"
    DRAPE = "drape"
    TRANSPARENCY = "transparency"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    USER_CONFIRMED = "user_confirmed"
    UNKNOWN = "unknown"


class FabricSubject(str, Enum):
    """Section 35-36: a photo of a person/shoe/room is not a fabric, and an
    existing garment is not a flat swatch, even though a garment photo may
    still yield partial (obscured) fabric evidence."""

    FABRIC_SWATCH = "fabric_swatch"
    GARMENT = "garment"
    NON_FABRIC = "non_fabric"
    UNCERTAIN = "uncertain"


class MotifType(str, Enum):
    FLORAL = "floral"
    GEOMETRIC = "geometric"
    PAISLEY = "paisley"
    ABSTRACT = "abstract"
    BOTANICAL = "botanical"
    TRADITIONAL = "traditional"
    STRIPE = "stripe"
    CHECK = "check"
    NONE = "none"
    OTHER = "other"


class MotifPlacement(str, Enum):
    ALL_OVER = "all_over"
    PLACEMENT = "placement"
    BORDER_ONLY = "border_only"
    NONE = "none"


# --- Model-facing schema (section 24) -- compact, no false precision ------


class VisionColorOut(DomainModel):
    name: str
    hex_estimate: str | None = None
    proportion: float | None = Field(default=None, ge=0.0, le=1.0)
    role: str = "dominant"  # "dominant" | "secondary" | "accent" | "metallic"


class VisionMotifOut(DomainModel):
    motif_type: str  # free text -- normalized against MotifType afterward
    placement: str | None = None
    scale: str | None = None
    density: str | None = None
    directional: bool | None = None


class VisionBorderOut(DomainModel):
    present: bool
    relative_width: str | None = None  # "narrow" | "moderate" | "wide" -- never exact cm, no reference scale
    decorative_density: str | None = None
    style: str | None = None
    directional: bool | None = None
    preserve_as_design_element: bool | None = None


class VisionPropertyOut(DomainModel):
    """One property judgment straight from the model. `certainty` is a
    coarse self-rating (never a fabricated precise float -- section 5);
    application code converts it to a calibrated confidence band."""

    value: str | None = None
    certainty: str = "unknown"  # "high" | "medium" | "low" | "unknown"
    source_images: list[str] = Field(default_factory=list)
    reason: str = ""
    alternative: str | None = None


class VisionModelOutput(DomainModel):
    """The ONLY shape asked of the vision model for one analysis call
    (covering all supplied images at once). Never repeats information the
    application already knows, never asked to compute anything
    deterministic -- purely "what does this look like."""

    image_subject: str = "uncertain"  # fabric_swatch | garment | non_fabric | uncertain
    subject_reason: str = ""

    dominant_colors: list[VisionColorOut] = Field(default_factory=list)

    transparency: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    sheen: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    drape: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    stiffness: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    structure: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    surface_density: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    weight_class: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    embellishment_tolerance: VisionPropertyOut = Field(default_factory=VisionPropertyOut)
    fabric_family: VisionPropertyOut = Field(default_factory=VisionPropertyOut)

    motifs: list[VisionMotifOut] = Field(default_factory=list)
    border: VisionBorderOut | None = None
    embellishment_types: list[str] = Field(default_factory=list)

    wear_potential_indian: float = Field(ge=0.0, le=1.0, default=0.5)
    wear_potential_western: float = Field(ge=0.0, le=1.0, default=0.5)
    wear_potential_fusion: float = Field(ge=0.0, le=1.0, default=0.5)
    wear_potential_reason: str = ""

    design_potential_signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_additional_photos: list[str] = Field(default_factory=list)


# --- Fused/normalized output (sections 3-4) -------------------------------


class EvidenceAlternative(DomainModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)


class Evidence(DomainModel):
    """One property's provenance trail -- section 4's evidence model.
    `property` names either a canonical `FabricProperties` field (e.g.
    "transparency") or a vision-only property not in the canonical model
    (e.g. "fabric_family")."""

    property: str
    value: str | float | bool | None = None
    evidence_type: EvidenceType
    confidence: float = Field(ge=0.0, le=1.0)
    source_images: list[str] = Field(default_factory=list)
    reason: str
    alternatives: list[EvidenceAlternative] = Field(default_factory=list)


class ObservedColor(DomainModel):
    name: str
    hex_estimate: str | None = None
    proportion: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    role: str = "dominant"


class MotifObservation(DomainModel):
    motif_type: MotifType
    placement: MotifPlacement = MotifPlacement.NONE
    scale: str | None = None
    density: str | None = None
    directional: bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class BorderObservation(DomainModel):
    present: bool
    relative_width: str | None = None
    decorative_density: str | None = None
    style: str | None = None
    directional: bool | None = None
    preserve_as_design_element: bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class WearPotential(DomainModel):
    """Section 17: never a single Indian/Western label -- suitability
    signals with a reason, informational only (Phase 1 is driven by the
    concrete `FabricProperties` fields, not by this)."""

    indian: float = Field(ge=0.0, le=1.0)
    western: float = Field(ge=0.0, le=1.0)
    fusion: float = Field(ge=0.0, le=1.0)
    reason: str


class FabricVisionObservation(DomainModel):
    """The fused, cross-image result of analyzing a set of fabric images."""

    image_subject: FabricSubject
    subject_confidence: float = Field(ge=0.0, le=1.0)
    dominant_colors: list[ObservedColor] = Field(default_factory=list)
    motifs: list[MotifObservation] = Field(default_factory=list)
    border: BorderObservation | None = None
    embellishment_types: list[str] = Field(default_factory=list)
    wear_potential: WearPotential | None = None
    design_potential_signals: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_additional_photos: list[str] = Field(default_factory=list)


class FabricProfileWithProvenance(DomainModel):
    """Section 18-19: maps 1:1 onto the existing canonical
    `FabricProperties` -- no parallel incompatible model. Provenance/
    confidence per field lives in the sidecar `evidence` list so Phase 1/2
    never need to know this came from a photograph rather than a text
    declaration."""

    fabric_name: str
    resolved_fabric_id: str | None = None
    resolution_method: str  # exact | alias | partial | unresolved
    properties: FabricProperties
    evidence: list[Evidence] = Field(default_factory=list)


class ImageQualityAssessment(DomainModel):
    image_id: str
    usable: bool
    warnings: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    sharpness_score: float | None = None
    brightness_score: float | None = None
    duplicate_of: str | None = Field(
        default=None, description="image_id this is a near-duplicate of, if any (section 26)"
    )


class VisionGenerationMetadata(DomainModel):
    provider: str
    model: str | None = None
    attempts: int = 1
    images_submitted: int = 0
    duplicate_images_dropped: int = 0
    fallback_used: bool = False
    provider_error: str | None = None
    provider_error_code: str | None = None
    timing_ms: dict[str, float] = Field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None


class FabricImageAnalysisResult(DomainModel):
    """Top-level result -- section 29's API response shape
    (`analysis`/`fabric_profile`/`evidence`/`warnings`/`generation_metadata`)."""

    image_quality: list[ImageQualityAssessment] = Field(default_factory=list)
    analysis: FabricVisionObservation
    fabric_profile: FabricProfileWithProvenance
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generation_metadata: VisionGenerationMetadata
