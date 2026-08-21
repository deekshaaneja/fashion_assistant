"""Tool: visualize_design -- Phase 4, "what could this specific design look
like when made from this specific fabric?"

Input: a validated `DesignProposal` (Phase 2), the `FabricImageAnalysisResult`
it was designed against (Phase 3, including the original image quality/
evidence), the original fabric photograph(s), and visualization options.
Output: a `VisualizationResult` -- a concept visualization, never treated as
a replacement for the structured `DesignProposal` (section 2).
"""
from __future__ import annotations

from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric_vision import FabricImageAnalysisResult
from src.domain.models.visualization import VisualizationOptions, VisualizationResult
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage
from src.fashion_engine.visualization.pipeline import visualize_design as _visualize_design

__all__ = ["visualize_design"]


def visualize_design(
    design: DesignProposal,
    image_analysis: FabricImageAnalysisResult,
    fabric_images: list[UploadedFabricImage],
    options: VisualizationOptions | None = None,
) -> VisualizationResult:
    return _visualize_design(design, image_analysis, fabric_images, options)
