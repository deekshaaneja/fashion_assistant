"""check_fabric_feasibility: rule-based feasibility framing + redesign
suggestions when the fabric on hand falls short. Returns FEASIBLE / MARGINAL /
INSUFFICIENT -- never UNKNOWN, since this tool always receives an explicit
required range from its caller (see `MaterialFeasibilityStatus`)."""
from __future__ import annotations

from src.domain.enums import MaterialFeasibilityStatus
from src.domain.models.common import Range
from src.domain.models.feasibility import FeasibilityResult

_MARGINAL_MARGIN_M = 0.3  # within this much of the minimum -> marginal, not a hard fail


def check_fabric_feasibility(
    available_metres: float,
    required_range: Range,
    garment_name: str | None = None,
    silhouette_name: str | None = None,
    high_flare: bool = False,
    has_directional_motif: bool = False,
) -> FeasibilityResult:
    label = f"{silhouette_name} {garment_name}".strip() if (garment_name or silhouette_name) else "this design"

    if available_metres >= required_range.min:
        return FeasibilityResult(
            status=MaterialFeasibilityStatus.FEASIBLE,
            available_metres=available_metres,
            required_range=required_range,
            shortage_range=None,
            redesign_options=[],
            reasoning=(
                f"{available_metres:.1f}m covers the {required_range.min:.1f}-{required_range.max:.1f}m "
                f"needed for {label}."
            ),
        )

    if available_metres >= required_range.min - _MARGINAL_MARGIN_M:
        return FeasibilityResult(
            status=MaterialFeasibilityStatus.MARGINAL,
            available_metres=available_metres,
            required_range=required_range,
            shortage_range=Range(min=0.0, max=round(required_range.min - available_metres, 2)),
            redesign_options=[
                "Reduce flare very slightly to fit within the fabric on hand.",
                "Use a plain complementary fabric for an inner lining panel to stretch the hero fabric further.",
            ],
            reasoning=(
                f"{available_metres:.1f}m is just under the {required_range.min:.1f}m minimum for {label} -- "
                "a small design adjustment closes the gap."
            ),
        )

    shortage = Range(
        min=round(required_range.min - available_metres, 2),
        max=round(required_range.max - available_metres, 2),
    )
    redesign_options = [
        "Reduce flare to a lower tier -- typically saves 10-15% of yardage.",
        "Use a plain complementary fabric for lower panels, lining, sleeves, or the dupatta.",
        "Convert to a shorter or lower-volume silhouette that needs less yardage.",
        "Use a contrast fabric for the dupatta/sleeves so the hero fabric only covers the main body.",
    ]
    if high_flare:
        redesign_options.insert(
            0,
            "Move to a lower-flare silhouette variant -- this design's flare is the main driver of the shortage.",
        )
    if has_directional_motif:
        redesign_options.append(
            "A directional motif adds wastage from pattern-matching -- a non-directional cut "
            "placement may recover some yardage."
        )

    return FeasibilityResult(
        status=MaterialFeasibilityStatus.INSUFFICIENT,
        available_metres=available_metres,
        required_range=required_range,
        shortage_range=shortage,
        redesign_options=redesign_options,
        reasoning=(
            f"{available_metres:.1f}m is short of the {required_range.min:.1f}-{required_range.max:.1f}m "
            f"needed for {label} by roughly {shortage.min:.1f}-{shortage.max:.1f}m."
        ),
    )
