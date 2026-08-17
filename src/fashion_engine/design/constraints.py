"""build_design_constraints: translates Phase 1 facts + the chosen
(garment, silhouette) into the hard constraints every candidate must respect
(Phase 2, section 2's "DESIGN CONSTRAINTS" stage). Reuses Phase 1's own
`evaluate_candidate` rather than re-deriving fabric/silhouette facts
(section 33: use Phase 1, don't duplicate it inside Phase 2)."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.context import RecommendationContext
from src.domain.models.design_generation import DesignConstraints
from src.domain.models.fabric import Fabric
from src.domain.models.garment import Garment, Silhouette
from src.fashion_engine.design.decoration import max_embellishment_intensity
from src.fashion_engine.scoring.engine import evaluate_candidate


def build_design_constraints(
    fabric: Fabric,
    garment: Garment,
    silhouette: Silhouette,
    context: RecommendationContext,
    client_brief: ClientBrief,
) -> DesignConstraints:
    evaluation = evaluate_candidate(fabric, garment, silhouette, context)

    hard_avoid: list[str] = []
    if evaluation.effective_flare_level != silhouette.default_flare_level:
        hard_avoid.append(
            f"full {silhouette.default_flare_level} flare (this fabric can only comfortably support "
            f"{evaluation.effective_flare_level})"
        )

    return DesignConstraints(
        fabric_id=fabric.id,
        garment_id=garment.id,
        silhouette_id=silhouette.id,
        effective_flare_level=evaluation.effective_flare_level,
        flare_construction=silhouette.flare_construction,
        requires_lining=fabric.properties.transparency in ("sheer", "semi_sheer"),
        max_embellishment_intensity=max_embellishment_intensity(fabric).value,
        consumption=evaluation.consumption,
        hard_avoid=hard_avoid,
        notes=list(evaluation.assumptions),
    )
