"""Tool: analyze_fabric_image -- Phase 3, "what can the system reliably
understand about this fabric from photographs?"

Input: one or more fabric photographs (raw bytes) plus optional fabric-name
hint and user-confirmed properties/name.
Output: structured observed/inferred/user_confirmed/unknown evidence and a
canonical `FabricProperties`-shaped declaration ready to hand to Phase 1/2
exactly like a text-declared `FabricObservation` would be.
"""
from __future__ import annotations

from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage, analyze_fabric_images

__all__ = ["analyze_fabric_image", "UploadedFabricImage", "FabricImageAnalysisResult"]


def analyze_fabric_image(
    images: list[UploadedFabricImage],
    fabric_name_hint: str | None = None,
    user_confirmed_properties: FabricProperties | None = None,
    user_confirmed_fabric_name: str | None = None,
) -> FabricImageAnalysisResult:
    return analyze_fabric_images(images, fabric_name_hint, user_confirmed_properties, user_confirmed_fabric_name)
