"""recommend_neckline: Phase 2, section 10. Considers garment architecture
(via candidate_families, drawn from the design archetype in play), fabric
transparency, aesthetic (DesignDNA), and an explicit client coverage
preference. Deliberately no body-shape framing anywhere in this module."""
from __future__ import annotations

from src.domain.enums import NecklineType
from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import NecklineSpec
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Silhouette

_COVERAGE_MIN_DEPTH = {"modest": "high", "moderate": "moderate", "open": "deep"}
_GLAMOUR_DEEP_FAMILIES = {
    NecklineType.DEEP_V,
    NecklineType.HALTER,
    NecklineType.OFF_SHOULDER,
    NecklineType.SWEETHEART,
    NecklineType.KEYHOLE,
}


def recommend_neckline(
    fabric: Fabric,
    silhouette: Silhouette,
    design_dna: DesignDNA,
    client_brief: ClientBrief,
    candidate_families: tuple[str, ...] = (),
) -> NecklineSpec:
    reasons: list[str] = []

    if client_brief.preferred_neckline is not None:
        chosen = client_brief.preferred_neckline
        reasons.append(f"Client specified a {chosen.replace('_', ' ')} neckline.")
    elif candidate_families:
        chosen = NecklineType(candidate_families[0])
        tags = ", ".join(silhouette.aesthetic_tags[:2]) or "overall"
        reasons.append(f"{silhouette.name}'s {tags} character suits a {chosen.value.replace('_', ' ')} neckline.")
    else:
        chosen = NecklineType.ROUND
        reasons.append("No stronger signal available -- a round neckline is a safe, versatile default.")

    depth = "moderate"
    if client_brief.preferred_coverage:
        depth = _COVERAGE_MIN_DEPTH.get(client_brief.preferred_coverage, depth)
        reasons.append(f"Depth calibrated to the client's stated '{client_brief.preferred_coverage}' coverage.")
    elif design_dna.understated_glamorous >= 0.7 and chosen in _GLAMOUR_DEEP_FAMILIES:
        depth = "deep"
        reasons.append("This direction's glamour-leaning character supports a deeper neckline.")

    lining_required = fabric.properties.transparency in ("sheer", "semi_sheer")
    if lining_required:
        reasons.append(
            f"{fabric.name} is {fabric.properties.transparency} -- neckline facing needs its own lining."
        )

    return NecklineSpec(type=chosen, depth=depth, lining_required=lining_required, rationale=" ".join(reasons))
