"""recommend_sleeves: Phase 2, section 11. Fabric transparency/structure
influences sleeve recommendations -- e.g. a sheer fabric can carry a
statement sheer sleeve without needing additional decoration."""
from __future__ import annotations

from src.domain.enums import SleeveLength, SleeveStyle
from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import SleeveSpec
from src.domain.models.fabric import Fabric


def recommend_sleeves(
    fabric: Fabric,
    client_brief: ClientBrief,
    candidate_length: str = "three_quarter",
    candidate_style: str = "straight",
) -> SleeveSpec:
    reasons: list[str] = []

    if client_brief.preferred_sleeve is not None:
        length = client_brief.preferred_sleeve
        reasons.append(f"Client specified a {length.replace('_', ' ')} sleeve.")
    else:
        length = SleeveLength(candidate_length)
        reasons.append(f"{length.value.replace('_', ' ')} length matches this direction's construction language.")

    style = SleeveStyle(candidate_style)
    sheer = fabric.properties.transparency == "sheer" and length != SleeveLength.SLEEVELESS
    if sheer:
        reasons.append(
            f"{fabric.name}'s sheerness lets these sleeves read as a statement on their own, "
            "without needing additional decoration."
        )

    return SleeveSpec(length=length, style=style, sheer=sheer, rationale=" ".join(reasons))
