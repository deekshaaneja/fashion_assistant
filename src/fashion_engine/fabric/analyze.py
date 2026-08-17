"""analyze_fabric: structured metadata in (image analysis is a later phase),
inferred properties/strengths/limitations/garment fit out. Every property in
the output either came from the seed catalog or the caller's own declaration
-- nothing is invented, and unknowns stay unknown (None), never silently
defaulted to something that then looks authoritative."""
from __future__ import annotations

from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_analysis import FabricAnalysis, FabricObservation
from src.rules.repository import get_fabric_repository, get_garment_repository, get_silhouette_repository


def merge_fabric_properties(catalog: FabricProperties, declared: FabricProperties) -> FabricProperties:
    """Declared (per-swatch) properties override the catalog default field by
    field -- e.g. "embroidered organza" overrides organza's default
    surface_density=none with the caller's declared dense. Uses
    `model_fields_set` (which fields were actually passed in), not a value
    comparison -- several fields (surface_density, stretch) have "none" as a
    real, meaningful value, not just a not-declared sentinel, so comparing
    against the string "none" would wrongly skip an explicit override."""
    merged = catalog.model_dump()
    for field_name in declared.model_fields_set:
        merged[field_name] = getattr(declared, field_name)
    return FabricProperties(**merged)


def _strengths_for(properties: FabricProperties) -> list[str]:
    strengths: list[str] = []
    if properties.structure == "structured":
        strengths.append("clean, structured silhouettes")
    if properties.drape in ("fluid", "soft"):
        strengths.append("flowing, movement-driven silhouettes")
    if properties.transparency == "sheer":
        strengths.append("sheer sleeve/overlay treatments")
    if properties.sheen in ("high_sheen", "metallic"):
        strengths.append("statement occasionwear surfaces")
    if properties.embellishment_tolerance == "high":
        strengths.append("can carry heavy additional embellishment")
    if properties.surface_density == "dense":
        strengths.append("already reads as a finished, decorated surface on its own")
    return strengths or ["general-purpose use -- no standout structural strengths identified"]


def _limitations_for(properties: FabricProperties) -> list[str]:
    limitations: list[str] = []
    if properties.drape in ("crisp", "stiff"):
        limitations.append("very high flare may become bulky rather than elegant")
    if properties.surface_density == "dense" or properties.embellishment_tolerance == "low":
        limitations.append("heavy additional embroidery may overwork the surface")
    if properties.transparency == "sheer":
        limitations.append("sheer base will likely need a lining for full coverage")
    if properties.weight_class == "heavy":
        limitations.append("less suited to lightweight daytime/summer wear")
    if properties.stretch in (None, "none"):
        limitations.append("no stretch -- fitted/body-conscious cuts need precise tailoring")
    return limitations


def analyze_fabric(observation: FabricObservation) -> FabricAnalysis:
    fabric_repo = get_fabric_repository()
    garment_repo = get_garment_repository()
    silhouette_repo = get_silhouette_repository()

    resolution = fabric_repo.resolve(observation.fabric_name)
    catalog_fabric = resolution.profile
    properties = merge_fabric_properties(catalog_fabric.properties, observation.declared_properties)

    assumptions: list[str] = []
    if resolution.method == "unresolved":
        assumptions.append(
            f"'{observation.fabric_name}' did not match the seed catalog -- properties are unknown."
        )
    elif resolution.method == "partial":
        assumptions.append(
            f"'{observation.fabric_name}' partially matched '{catalog_fabric.name}' in the catalog."
        )

    suitable_silhouette_ids = set(catalog_fabric.strong_fit_silhouettes)
    unsuitable_silhouette_ids = set(catalog_fabric.avoid_silhouettes)
    if properties.structure == "structured":
        suitable_silhouette_ids |= {s.id for s in silhouette_repo.all() if s.structure_affinity == "structured"}
    if properties.drape in ("fluid", "soft"):
        suitable_silhouette_ids |= {s.id for s in silhouette_repo.all() if s.structure_affinity == "fluid"}

    def _garment_families(silhouette_ids: set[str]) -> list[str]:
        garment_ids: set[str] = set()
        for silhouette_id in silhouette_ids:
            silhouette = silhouette_repo.get(silhouette_id)
            if silhouette:
                garment_ids |= set(silhouette.applicable_garment_ids)
        names = sorted(garment_repo.get(gid).name for gid in garment_ids if garment_repo.get(gid))
        return names

    suitable_families = _garment_families(suitable_silhouette_ids)
    unsuitable_families = [f for f in _garment_families(unsuitable_silhouette_ids) if f not in suitable_families]

    wear_leans = [
        garment_repo.get(gid).wear_category
        for silhouette_id in suitable_silhouette_ids
        if (silhouette := silhouette_repo.get(silhouette_id))
        for gid in silhouette.applicable_garment_ids
        if garment_repo.get(gid)
    ]
    wear_category_lean = max(set(wear_leans), key=wear_leans.count) if wear_leans else None

    base_confidence = resolution.confidence
    if observation.declared_properties.model_dump(exclude_defaults=True):
        base_confidence = min(0.95, base_confidence + 0.15)

    return FabricAnalysis(
        fabric_name=observation.fabric_name,
        resolved_fabric_id=catalog_fabric.id if resolution.method != "unresolved" else None,
        resolution_method=resolution.method,
        properties=properties,
        strengths=_strengths_for(properties),
        limitations=_limitations_for(properties),
        suitable_garment_families=suitable_families,
        unsuitable_garment_families=unsuitable_families,
        wear_category_lean=wear_category_lean,
        confidence=round(base_confidence, 2),
        assumptions=assumptions,
    )
