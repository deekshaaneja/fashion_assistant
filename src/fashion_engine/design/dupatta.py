"""recommend_dupatta (design-level): Phase 2, section 16. Decides whether a
dupatta belongs in this design at all, then its fabric role, weight,
transparency, color strategy, border, and embellishment -- support, not an
afterthought."""
from __future__ import annotations

from src.domain.enums import DupattaColorStrategy
from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import DupattaSpec
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment

_PHILOSOPHY_TO_STRATEGY = {
    "lightweight_contrast_or_tonal": DupattaColorStrategy.CONTRAST,
    "structural_or_omit": DupattaColorStrategy.TONAL,
    "omit_or_minimal_scarf": DupattaColorStrategy.TONAL,
    "heavy_border_contrast": DupattaColorStrategy.CONTRAST,
    "omit_or_statement_drape": DupattaColorStrategy.METALLIC,
    "optional_replaced_by_overlay": DupattaColorStrategy.TONAL,
}
_OMIT_PHILOSOPHIES = {"omit_or_minimal_scarf", "optional_replaced_by_overlay"}


def recommend_dupatta(
    garment: Garment,
    fabric: Fabric,
    dupatta_philosophy: str,
    client_brief: ClientBrief,
) -> DupattaSpec | None:
    """Returns None when the garment has no dupatta component at all (a
    structural fact about the garment, not a design choice)."""
    if "dupatta" not in garment.typical_components:
        return None

    reasons: list[str] = []
    include = dupatta_philosophy not in _OMIT_PHILOSOPHIES
    if not include and client_brief.preferred_coverage == "modest":
        include = True
        reasons.append(
            "Client's modest coverage preference calls for a dupatta even where this direction would "
            "otherwise omit it."
        )

    if not include:
        reasons.append(
            "This direction's construction language already carries the silhouette's visual weight -- "
            "omitting the dupatta keeps the look clean rather than adding it back in as an afterthought."
        )
        return DupattaSpec(included=False, rationale=" ".join(reasons))

    heavy_or_dense = fabric.properties.weight_class == "heavy" or fabric.properties.surface_density == "dense"
    fabric_role = "supporting" if heavy_or_dense else "main"
    if fabric_role == "supporting":
        fabric_description = "lightweight plain organza" if fabric.properties.transparency != "opaque" else (
            "lightweight fabric in a matching weight class"
        )
        weight, transparency = "light", "semi_sheer"
        reasons.append(
            f"{fabric.name} is too heavy/dense to drape well as a dupatta -- a lighter supporting fabric "
            "carries it instead."
        )
    else:
        fabric_description = f"{fabric.name.lower()}, matching the main garment"
        weight, transparency = None, fabric.properties.transparency

    color_strategy = _PHILOSOPHY_TO_STRATEGY.get(dupatta_philosophy, DupattaColorStrategy.TONAL)
    border = None
    if color_strategy == DupattaColorStrategy.CONTRAST:
        border = "contrast border"
    if dupatta_philosophy == "heavy_border_contrast":
        border = "heavy contrast border with embellishment"

    return DupattaSpec(
        included=True,
        fabric_role=fabric_role,
        fabric_description=fabric_description,
        weight=weight,
        transparency=transparency,
        color_strategy=color_strategy,
        border=border,
        rationale=" ".join(reasons) or "A dupatta completes this ensemble's silhouette.",
    )
