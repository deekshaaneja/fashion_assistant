"""design_ensemble: Phase 2, section 9. Thinks about the complete look, not
only the main garment -- built directly from the garment's own
`typical_components` (Phase 1 catalog data, section 33: reuse, don't
duplicate), so a suit, a lehenga, and a jacket set naturally get different
ensembles without any garment-specific branching here."""
from __future__ import annotations

from src.domain.models.design_proposal import DesignEnsemble, DesignProposal, EnsembleComponent
from src.domain.models.garment import Garment


def design_ensemble(primary_design: DesignProposal, garment: Garment) -> DesignEnsemble:
    components: list[EnsembleComponent] = []

    for component_name in garment.typical_components:
        if component_name == "top":
            components.append(
                EnsembleComponent(
                    component="main_garment",
                    included=True,
                    fabric_role="main",
                    description=f"{garment.name}, {primary_design.garment.silhouette.name} silhouette.",
                    rationale=primary_design.design_intent,
                )
            )
        elif component_name == "blouse":
            components.append(
                EnsembleComponent(
                    component="blouse",
                    included=True,
                    fabric_role="main",
                    description="Fitted blouse in the main fabric.",
                    rationale=f"{garment.name} pairs a fitted blouse with the draped/skirted lower body.",
                )
            )
        elif component_name == "bottom" and primary_design.bottom:
            components.append(
                EnsembleComponent(
                    component="bottom",
                    included=True,
                    fabric_role=primary_design.bottom.fabric_role,
                    description=primary_design.bottom.type,
                    rationale=primary_design.bottom.rationale,
                )
            )
        elif component_name == "dupatta":
            if primary_design.dupatta and primary_design.dupatta.included:
                components.append(
                    EnsembleComponent(
                        component="dupatta",
                        included=True,
                        fabric_role=primary_design.dupatta.fabric_role or "supporting",
                        description=primary_design.dupatta.fabric_description or "dupatta",
                        rationale=primary_design.dupatta.rationale,
                    )
                )
            else:
                omitted_reason = (
                    primary_design.dupatta.rationale if primary_design.dupatta else "Not part of this design."
                )
                components.append(
                    EnsembleComponent(
                        component="dupatta",
                        included=False,
                        fabric_role="not_applicable",
                        description="omitted",
                        rationale=omitted_reason,
                    )
                )
        elif component_name == "lining" and primary_design.lining and primary_design.lining.required:
            components.append(
                EnsembleComponent(
                    component="lining",
                    included=True,
                    fabric_role="supporting",
                    description=primary_design.lining.fabric_description or "lining",
                    rationale=primary_design.lining.rationale,
                )
            )
        elif component_name == "jacket":
            components.append(
                EnsembleComponent(
                    component="jacket",
                    included=True,
                    fabric_role="supporting",
                    description="Structured overlay jacket.",
                    rationale="This garment's architecture is built around a layered jacket component.",
                )
            )
        elif component_name == "cape":
            components.append(
                EnsembleComponent(
                    component="cape",
                    included=True,
                    fabric_role="supporting",
                    description="Dramatic cape layer.",
                    rationale="This garment's architecture is built around a cape component.",
                )
            )
        # "border" is a fabric/construction attribute (data/seed/garments.yaml), not a separate ensemble piece.

    rationale = (
        f"Ensemble derived from {garment.name}'s own typical components -- only what this garment "
        "architecture actually calls for."
    )
    return DesignEnsemble(components=components, rationale=rationale)
