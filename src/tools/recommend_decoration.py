"""Tool: recommend_decoration (Phase 2, section 13-14). Genuinely capable of
returning NO_ADDITIONAL_DECORATION -- occasion never implies heavy decoration."""
from __future__ import annotations

from src.domain.models.client_brief import ClientBrief
from src.domain.models.design_proposal import DecorationSpec
from src.fashion_engine.design.decoration import recommend_decoration as _recommend_decoration
from src.rules.repository import get_fabric_repository

__all__ = ["recommend_decoration"]


def recommend_decoration(
    fabric_name: str,
    decoration_philosophy: str = "restrained_frame",
    client_brief: ClientBrief | None = None,
) -> DecorationSpec:
    fabric = get_fabric_repository().resolve(fabric_name).profile
    return _recommend_decoration(fabric, decoration_philosophy, client_brief or ClientBrief())
