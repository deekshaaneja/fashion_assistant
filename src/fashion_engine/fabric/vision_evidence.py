"""Phase 3, sections 3-4 & 18-20: turns one `VisionModelOutput` (the raw
model-facing shape) into a fused `FabricVisionObservation` with full
observed/inferred/user_confirmed/unknown provenance, then maps that into the
existing canonical `FabricProperties` -- no parallel incompatible model
(section 18). User-confirmed properties always take precedence over AI
inference (section 19), with the original AI inference preserved as a
secondary alternative for audit (section 20).

Multi-image strategy (section 25): one bounded vision call is made per
analysis with ALL (deduplicated) images attached at once, and the model is
asked to cite which image(s) support each judgement (`source_images`,
translated here from its "image_N" labels back to real image ids) -- this
gives per-property traceability without the cost/latency of N independent
calls. True cross-call statistical fusion (weighted-averaging independently
generated observations) is not implemented; it's a natural extension point
if a future case needs images split across multiple calls."""
from __future__ import annotations

from src.domain.enums import (
    Drape,
    EmbellishmentTolerance,
    Sheen,
    Stiffness,
    StructureLevel,
    SurfaceDensity,
    Transparency,
    WeightClass,
)
from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import (
    BorderObservation,
    Evidence,
    EvidenceAlternative,
    EvidenceType,
    FabricSubject,
    FabricVisionObservation,
    MotifObservation,
    MotifPlacement,
    MotifType,
    ObservedColor,
    VisionModelOutput,
    VisionPropertyOut,
    WearPotential,
)

# Section 3: which properties are directly visually apparent (OBSERVED) vs.
# which require material/textile inference beyond what's literally visible
# (INFERRED, the default for anything not in this set). Fixed, not
# something the model itself decides.
_OBSERVED_PROPERTIES = {"transparency", "sheen", "surface_density"}

_ALLOWED_VALUES: dict[str, tuple[str, ...]] = {
    "transparency": tuple(v.value for v in Transparency),
    "sheen": tuple(v.value for v in Sheen),
    "drape": tuple(v.value for v in Drape),
    "stiffness": tuple(v.value for v in Stiffness),
    "structure": tuple(v.value for v in StructureLevel),
    "surface_density": tuple(v.value for v in SurfaceDensity),
    "weight_class": tuple(v.value for v in WeightClass),
    "embellishment_tolerance": tuple(v.value for v in EmbellishmentTolerance),
}

_CERTAINTY_CONFIDENCE = {"high": 0.85, "medium": 0.6, "low": 0.35, "unknown": 0.0}

_VALID_EMBELLISHMENT_TYPES = frozenset(
    {
        "zari", "zardozi", "aari", "threadwork", "mirror_work", "sequins", "cutdana", "beads", "pearls",
        "gota_patti", "applique", "lace", "embroidery", "piping", "metallic_thread", "printed", "woven_jacquard",
    }
)

# Section 3: never visually determinable, regardless of what any model says
# -- always UNKNOWN unless a human explicitly confirms them.
_ALWAYS_UNKNOWN_PROPERTIES = {
    "gsm": "Exact GSM cannot be established reliably from photographs.",
    "width_cm": "Exact fabric width cannot be established reliably without a reference scale.",
    "stretch": "Exact stretch behavior cannot be established reliably from a photograph.",
}


def _certainty_to_confidence(certainty: str) -> float:
    return _CERTAINTY_CONFIDENCE.get((certainty or "unknown").strip().lower(), 0.0)


def _normalize_enum_value(value: str | None, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    return normalized if normalized in allowed else None


def _resolve_source_images(labels: list[str], image_id_map: dict[str, str]) -> list[str]:
    return [image_id_map.get(label, label) for label in labels]


def _property_evidence(
    name: str, prop: VisionPropertyOut, image_id_map: dict[str, str], warnings: list[str]
) -> Evidence:
    allowed = _ALLOWED_VALUES.get(name)
    source_images = _resolve_source_images(prop.source_images, image_id_map)

    if prop.certainty == "unknown" or not prop.value:
        return Evidence(
            property=name,
            value=None,
            evidence_type=EvidenceType.UNKNOWN,
            confidence=0.0,
            source_images=source_images,
            reason=prop.reason or f"{name.replace('_', ' ')} cannot be reliably determined from the photographs.",
        )

    normalized = _normalize_enum_value(prop.value, allowed) if allowed is not None else prop.value.strip()
    if allowed is not None and normalized is None:
        warnings.append(f"Model returned an unrecognized value ({prop.value!r}) for {name} -- treated as unknown.")
        return Evidence(
            property=name,
            value=None,
            evidence_type=EvidenceType.UNKNOWN,
            confidence=0.0,
            source_images=source_images,
            reason=f"Model's answer ({prop.value!r}) was outside the allowed vocabulary for {name}.",
        )

    evidence_type = EvidenceType.OBSERVED if name in _OBSERVED_PROPERTIES else EvidenceType.INFERRED
    alternatives = []
    if prop.alternative:
        alt_normalized = (
            _normalize_enum_value(prop.alternative, allowed) if allowed is not None else prop.alternative
        )
        if alt_normalized:
            alt_confidence = max(_certainty_to_confidence(prop.certainty) - 0.25, 0.05)
            alternatives.append(EvidenceAlternative(value=alt_normalized, confidence=alt_confidence))

    return Evidence(
        property=name,
        value=normalized,
        evidence_type=evidence_type,
        confidence=_certainty_to_confidence(prop.certainty),
        source_images=source_images,
        reason=prop.reason or "",
        alternatives=alternatives,
    )


def _color_evidence(colors: list[ObservedColor]) -> Evidence | None:
    if not colors:
        return None
    top = colors[0]
    return Evidence(
        property="dominant_color",
        value=top.name,
        evidence_type=EvidenceType.OBSERVED,
        confidence=top.confidence,
        reason="Image-estimated color -- actual physical color may shift under different lighting (section 8).",
    )


def normalize_observation(
    output: VisionModelOutput, image_ids_in_order: list[str], warnings: list[str] | None = None
) -> FabricVisionObservation:
    """Turns the raw model-facing `VisionModelOutput` into the fused,
    provenance-carrying `FabricVisionObservation`. `image_ids_in_order`
    maps "image_1".."image_N" (the labels used in the prompt/schema) back
    to the real image ids the caller supplied."""
    warnings = warnings if warnings is not None else []
    image_id_map = {f"image_{i}": image_id for i, image_id in enumerate(image_ids_in_order, start=1)}

    subject = _normalize_enum_value(output.image_subject, tuple(v.value for v in FabricSubject)) or "uncertain"
    subject_confidence = 0.85 if subject != "uncertain" else 0.3

    evidence: list[Evidence] = []
    for name in (
        "transparency",
        "sheen",
        "drape",
        "stiffness",
        "structure",
        "surface_density",
        "weight_class",
        "embellishment_tolerance",
        "fabric_family",
    ):
        evidence.append(_property_evidence(name, getattr(output, name), image_id_map, warnings))

    dominant_colors = [
        ObservedColor(
            name=c.name,
            hex_estimate=c.hex_estimate,
            proportion=c.proportion,
            confidence=0.75 if c.role == "dominant" else 0.55,
            role=c.role,
        )
        for c in output.dominant_colors
    ]
    color_evidence = _color_evidence(dominant_colors)
    if color_evidence is not None:
        evidence.append(color_evidence)

    motif_type_values = tuple(v.value for v in MotifType)
    motif_placement_values = tuple(v.value for v in MotifPlacement)
    motifs: list[MotifObservation] = []
    any_directional = False
    for m in output.motifs:
        motif_type = _normalize_enum_value(m.motif_type, motif_type_values) or MotifType.OTHER.value
        placement = _normalize_enum_value(m.placement, motif_placement_values) or MotifPlacement.NONE.value
        if m.directional:
            any_directional = True
        motifs.append(
            MotifObservation(
                motif_type=motif_type,
                placement=placement,
                scale=m.scale,
                density=m.density,
                directional=m.directional,
                confidence=0.65,
                reason="Visible pattern/motif observed in the photographs.",
            )
        )
    evidence.append(
        Evidence(
            property="motif_directional",
            value=any_directional if motifs else None,
            evidence_type=EvidenceType.OBSERVED if motifs else EvidenceType.UNKNOWN,
            confidence=0.6 if motifs else 0.0,
            reason="Derived from observed motif directionality." if motifs else "No motifs observed.",
        )
    )

    border = None
    if output.border is not None:
        border = BorderObservation(
            present=output.border.present,
            relative_width=output.border.relative_width,
            decorative_density=output.border.decorative_density,
            style=output.border.style,
            directional=output.border.directional,
            preserve_as_design_element=output.border.preserve_as_design_element,
            confidence=0.7 if not output.border.present else 0.6,
            reason="Border presence/absence observed directly; finer detail is a softer judgement.",
        )
    evidence.append(
        Evidence(
            property="border_available",
            value=border.present if border else None,
            evidence_type=EvidenceType.OBSERVED if border else EvidenceType.UNKNOWN,
            confidence=border.confidence if border else 0.0,
            reason=border.reason if border else "Border presence was not assessed.",
        )
    )

    for name, reason in _ALWAYS_UNKNOWN_PROPERTIES.items():
        evidence.append(
            Evidence(property=name, value=None, evidence_type=EvidenceType.UNKNOWN, confidence=0.0, reason=reason)
        )

    embellishment_types = [
        e.strip().lower() for e in output.embellishment_types if e.strip().lower() in _VALID_EMBELLISHMENT_TYPES
    ]
    if embellishment_types:
        evidence.append(
            Evidence(
                property="embellishment_types",
                value=", ".join(embellishment_types),
                evidence_type=EvidenceType.OBSERVED,
                confidence=0.65,
                reason="Surface work visually identified across the photographs.",
            )
        )

    wear_potential = WearPotential(
        indian=output.wear_potential_indian,
        western=output.wear_potential_western,
        fusion=output.wear_potential_fusion,
        reason=output.wear_potential_reason or "No specific reasoning provided.",
    )

    return FabricVisionObservation(
        image_subject=subject,
        subject_confidence=subject_confidence,
        dominant_colors=dominant_colors,
        motifs=motifs,
        border=border,
        embellishment_types=embellishment_types,
        wear_potential=wear_potential,
        design_potential_signals=list(output.design_potential_signals),
        evidence=evidence,
        warnings=list(output.warnings) + warnings,
        suggested_additional_photos=list(output.suggested_additional_photos),
    )


_FABRIC_PROPERTY_ENUM_FIELDS = {
    "transparency": Transparency,
    "sheen": Sheen,
    "drape": Drape,
    "stiffness": Stiffness,
    "structure": StructureLevel,
    "surface_density": SurfaceDensity,
    "weight_class": WeightClass,
    "embellishment_tolerance": EmbellishmentTolerance,
}


def build_fabric_properties(evidence: list[Evidence]) -> FabricProperties:
    """Maps evidence entries whose `property` matches a canonical
    `FabricProperties` field into an actual instance -- UNKNOWN evidence
    (or a property with no evidence at all) leaves the field `None`, never
    silently defaulted to something that would look authoritative
    downstream (section 18, matching `FabricProperties`'s own philosophy)."""
    by_property = {e.property: e for e in evidence}
    fields: dict[str, object] = {}

    for name, enum_cls in _FABRIC_PROPERTY_ENUM_FIELDS.items():
        e = by_property.get(name)
        if e is not None and e.evidence_type != EvidenceType.UNKNOWN and e.value is not None:
            fields[name] = enum_cls(e.value)

    border_evidence = by_property.get("border_available")
    if border_evidence is not None and border_evidence.evidence_type != EvidenceType.UNKNOWN:
        fields["border_available"] = bool(border_evidence.value)

    motif_evidence = by_property.get("motif_directional")
    if motif_evidence is not None and motif_evidence.evidence_type != EvidenceType.UNKNOWN:
        fields["motif_directional"] = bool(motif_evidence.value)

    return FabricProperties(**fields)


def apply_user_overrides(
    evidence: list[Evidence],
    user_confirmed_properties: FabricProperties | None,
) -> list[Evidence]:
    """Section 19-20: a user-confirmed value always wins outright, but the
    prior AI evidence is preserved as a secondary alternative for audit
    rather than discarded."""
    if user_confirmed_properties is None:
        return evidence

    result = list(evidence)
    by_property = {e.property: i for i, e in enumerate(result)}

    for field_name in user_confirmed_properties.model_fields_set:
        value = getattr(user_confirmed_properties, field_name)
        if value is None:
            continue
        raw_value = value.value if hasattr(value, "value") else value
        prior = result[by_property[field_name]] if field_name in by_property else None
        alternatives = list(prior.alternatives) if prior else []
        if prior is not None and prior.evidence_type != EvidenceType.UNKNOWN and prior.value is not None:
            alternatives.insert(0, EvidenceAlternative(value=str(prior.value), confidence=prior.confidence))

        confirmed = Evidence(
            property=field_name,
            value=raw_value,
            evidence_type=EvidenceType.USER_CONFIRMED,
            confidence=1.0,
            source_images=[],
            reason="Boutique owner confirmed this directly.",
            alternatives=alternatives,
        )
        if field_name in by_property:
            result[by_property[field_name]] = confirmed
        else:
            result.append(confirmed)

    return result


def apply_user_confirmed_fabric_name(evidence: list[Evidence], fabric_name: str | None) -> list[Evidence]:
    if fabric_name is None:
        return evidence
    result = list(evidence)
    by_property = {e.property: i for i, e in enumerate(result)}
    prior = result[by_property["fabric_family"]] if "fabric_family" in by_property else None
    alternatives = []
    if prior is not None and prior.evidence_type != EvidenceType.UNKNOWN and prior.value is not None:
        alternatives.append(EvidenceAlternative(value=str(prior.value), confidence=prior.confidence))

    confirmed = Evidence(
        property="fabric_family",
        value=fabric_name,
        evidence_type=EvidenceType.USER_CONFIRMED,
        confidence=1.0,
        reason="Boutique owner confirmed the fabric name directly.",
        alternatives=alternatives,
    )
    if "fabric_family" in by_property:
        result[by_property["fabric_family"]] = confirmed
    else:
        result.append(confirmed)
    return result
