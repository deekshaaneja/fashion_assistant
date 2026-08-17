"""Tool: recommend_neckline (Phase 2, section 10)."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import NecklineSpec
from src.fashion_engine.design.neckline import recommend_neckline as _recommend_neckline
from src.rules.repository import get_fabric_repository, get_silhouette_repository

__all__ = ["recommend_neckline"]


def recommend_neckline(
    fabric_name: str,
    silhouette_id: str,
    design_dna: DesignDNA | None = None,
    client_brief: ClientBrief | None = None,
) -> NecklineSpec:
    fabric = get_fabric_repository().resolve(fabric_name).profile
    silhouette = get_silhouette_repository().get(silhouette_id)
    if silhouette is None:
        raise ValueError(f"Unknown silhouette id '{silhouette_id}'.")
    # No archetype selected here (this is the standalone tool, not the
    # generation pipeline) -- candidate_families is left empty so the
    # recommendation falls back to the client's stated preference or a
    # safe default, rather than guessing a family from aesthetic_tags
    # (which describe overall character, not neckline shape).
    return _recommend_neckline(
        fabric,
        silhouette,
        design_dna or DesignDNA(),
        client_brief or ClientBrief(),
        candidate_families=(),
    )
