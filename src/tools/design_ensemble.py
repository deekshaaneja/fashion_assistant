"""Tool: design_ensemble (Phase 2, section 9). Thinks about the complete
look for an already-generated primary design, not just the main garment."""
from __future__ import annotations

from src.domain.models.design_proposal import DesignEnsemble, DesignProposal
from src.fashion_engine.design.ensemble import design_ensemble as _design_ensemble
from src.rules.repository import get_garment_repository

__all__ = ["design_ensemble"]


def design_ensemble(primary_design: DesignProposal) -> DesignEnsemble:
    garment = get_garment_repository().get(primary_design.garment.garment.id)
    if garment is None:
        raise ValueError(f"Unknown garment id '{primary_design.garment.garment.id}'.")
    return _design_ensemble(primary_design, garment)
