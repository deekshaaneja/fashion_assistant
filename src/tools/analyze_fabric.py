"""Tool: analyze_fabric.

Input: structured fabric metadata (a name plus optional declared per-swatch
properties -- image analysis is a later phase, see section 6).
Output: inferred properties, strengths, limitations, suitable/unsuitable
garment families, confidence, and any assumptions made.
Deterministic: pure lookup + merge over the seed catalog, no LLM involved.
"""
from __future__ import annotations

from src.domain.models.fabric_analysis import FabricAnalysis, FabricObservation
from src.fashion_engine.fabric.analyze import analyze_fabric as _analyze_fabric

__all__ = ["analyze_fabric", "FabricObservation", "FabricAnalysis"]


def analyze_fabric(observation: FabricObservation) -> FabricAnalysis:
    return _analyze_fabric(observation)
