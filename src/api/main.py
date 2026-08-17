"""FastAPI application: thin programmatic tool boundary over the fashion
intelligence kernel (section 25, Step 7). No frontend, no CRM, no
persistence -- every endpoint is a direct, stateless call into src/tools/*.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from src.domain.models.client_brief import ClientBrief
from src.domain.models.common import Range
from src.domain.models.context import RecommendationContext
from src.domain.models.design_dna import DesignDNA
from src.domain.models.design_proposal import DesignProposal
from src.domain.models.fabric import FabricProperties
from src.domain.models.fabric_analysis import FabricObservation
from src.tools.analyze_fabric import analyze_fabric as _analyze_fabric
from src.tools.calculate_consumption import calculate_consumption as _calculate_consumption
from src.tools.check_fabric_feasibility import check_fabric_feasibility as _check_fabric_feasibility
from src.tools.design_ensemble import design_ensemble as _design_ensemble
from src.tools.generate_colorways import generate_colorways as _generate_colorways
from src.tools.generate_design_colorways import generate_design_colorways as _generate_design_colorways
from src.tools.generate_design_directions import generate_design_directions as _generate_design_directions
from src.tools.recommend_decoration import recommend_decoration as _recommend_decoration
from src.tools.recommend_dupatta import recommend_dupatta as _recommend_dupatta
from src.tools.recommend_fabrics import recommend_fabrics as _recommend_fabrics
from src.tools.recommend_neckline import recommend_neckline as _recommend_neckline
from src.tools.recommend_proportions import recommend_proportions as _recommend_proportions
from src.tools.recommend_silhouettes import recommend_silhouettes as _recommend_silhouettes
from src.tools.recommend_sleeves import recommend_sleeves as _recommend_sleeves
from src.tools.recommend_styling import recommend_styling as _recommend_styling

app = FastAPI(
    title="Fashion Intelligence Kernel",
    version="0.1.0",
    description="Deterministic fashion domain tools -- the future tool layer behind a co-designer agent.",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class RecommendSilhouettesRequest(StrictModel):
    fabric_name: str
    declared_properties: FabricProperties | None = None
    context: RecommendationContext | None = None


@app.post("/v1/tools/recommend-silhouettes")
def recommend_silhouettes(req: RecommendSilhouettesRequest) -> dict:
    result = _recommend_silhouettes(req.fabric_name, req.declared_properties, req.context)
    return result.model_dump()


class RecommendFabricsRequest(StrictModel):
    silhouette_id: str
    garment_id: str | None = None
    context: RecommendationContext | None = None


@app.post("/v1/tools/recommend-fabrics")
def recommend_fabrics(req: RecommendFabricsRequest) -> dict:
    try:
        result = _recommend_fabrics(req.silhouette_id, req.garment_id, req.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class RecommendStylingRequest(StrictModel):
    garment_id: str
    silhouette_id: str
    fabric_name: str
    context: RecommendationContext | None = None


@app.post("/v1/tools/recommend-styling")
def recommend_styling(req: RecommendStylingRequest) -> dict:
    try:
        result = _recommend_styling(req.garment_id, req.silhouette_id, req.fabric_name, req.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class CalculateConsumptionRequest(StrictModel):
    garment_id: str
    silhouette_id: str
    size: str | None = None
    fabric_width_cm: float = 112.0
    flare_level: str | None = None
    include_sleeve_allowance: bool = False
    include_lining: bool = True
    include_border: bool = False
    directional_motif: bool = False
    batch_quantity: int = 1


@app.post("/v1/tools/calculate-consumption")
def calculate_consumption(req: CalculateConsumptionRequest) -> dict:
    try:
        result = _calculate_consumption(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class CheckFeasibilityRequest(StrictModel):
    available_metres: float
    required_range: Range
    garment_name: str | None = None
    silhouette_name: str | None = None
    high_flare: bool = False
    has_directional_motif: bool = False


@app.post("/v1/tools/check-fabric-feasibility")
def check_fabric_feasibility(req: CheckFeasibilityRequest) -> dict:
    # Not **req.model_dump() -- that would flatten the nested `required_range`
    # (a real Range object on the validated request) back into a plain dict.
    result = _check_fabric_feasibility(
        req.available_metres,
        req.required_range,
        garment_name=req.garment_name,
        silhouette_name=req.silhouette_name,
        high_flare=req.high_flare,
        has_directional_motif=req.has_directional_motif,
    )
    return result.model_dump()


class GenerateColorwaysRequest(StrictModel):
    fabric_name: str
    garment_id: str | None = None
    context: RecommendationContext | None = None


@app.post("/v1/tools/generate-colorways")
def generate_colorways(req: GenerateColorwaysRequest) -> dict:
    result = _generate_colorways(req.fabric_name, req.garment_id, req.context)
    return result.model_dump()


@app.post("/v1/tools/analyze-fabric")
def analyze_fabric(observation: FabricObservation) -> dict:
    result = _analyze_fabric(observation)
    return result.model_dump()


# --- Phase 2: Design Intelligence Engine ------------------------------------


class GenerateDesignDirectionsRequest(StrictModel):
    fabric_name: str
    declared_properties: FabricProperties | None = None
    fashion_context: RecommendationContext | None = None
    client_brief: ClientBrief | None = None
    selected_garment_id: str | None = None
    selected_silhouette_id: str | None = None
    count: int = 3


@app.post("/v1/tools/generate-design-directions")
def generate_design_directions(req: GenerateDesignDirectionsRequest) -> dict:
    try:
        result = _generate_design_directions(
            req.fabric_name,
            req.declared_properties,
            req.fashion_context,
            req.client_brief,
            selected_garment_id=req.selected_garment_id,
            selected_silhouette_id=req.selected_silhouette_id,
            count=req.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class DesignEnsembleRequest(StrictModel):
    primary_design: DesignProposal


@app.post("/v1/tools/design-ensemble")
def design_ensemble(req: DesignEnsembleRequest) -> dict:
    try:
        result = _design_ensemble(req.primary_design)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class RecommendNecklineRequest(StrictModel):
    fabric_name: str
    silhouette_id: str
    design_dna: DesignDNA | None = None
    client_brief: ClientBrief | None = None


@app.post("/v1/tools/recommend-neckline")
def recommend_neckline(req: RecommendNecklineRequest) -> dict:
    try:
        result = _recommend_neckline(req.fabric_name, req.silhouette_id, req.design_dna, req.client_brief)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class RecommendSleevesRequest(StrictModel):
    fabric_name: str
    client_brief: ClientBrief | None = None


@app.post("/v1/tools/recommend-sleeves")
def recommend_sleeves(req: RecommendSleevesRequest) -> dict:
    result = _recommend_sleeves(req.fabric_name, req.client_brief)
    return result.model_dump()


class RecommendProportionsRequest(StrictModel):
    fabric_name: str
    garment_id: str
    silhouette_id: str
    declared_properties: FabricProperties | None = None
    fashion_context: RecommendationContext | None = None
    client_brief: ClientBrief | None = None
    has_dupatta: bool = False
    has_overlay: bool = False


@app.post("/v1/tools/recommend-proportions")
def recommend_proportions(req: RecommendProportionsRequest) -> dict:
    try:
        result = _recommend_proportions(
            req.fabric_name,
            req.garment_id,
            req.silhouette_id,
            req.declared_properties,
            req.fashion_context,
            req.client_brief,
            has_dupatta=req.has_dupatta,
            has_overlay=req.has_overlay,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class RecommendDecorationRequest(StrictModel):
    fabric_name: str
    decoration_philosophy: str = "restrained_frame"
    client_brief: ClientBrief | None = None


@app.post("/v1/tools/recommend-decoration")
def recommend_decoration(req: RecommendDecorationRequest) -> dict:
    result = _recommend_decoration(req.fabric_name, req.decoration_philosophy, req.client_brief)
    return result.model_dump()


class RecommendDupattaRequest(StrictModel):
    garment_id: str
    fabric_name: str
    dupatta_philosophy: str = "lightweight_contrast_or_tonal"
    client_brief: ClientBrief | None = None


@app.post("/v1/tools/recommend-dupatta")
def recommend_dupatta(req: RecommendDupattaRequest) -> dict:
    try:
        result = _recommend_dupatta(req.garment_id, req.fabric_name, req.dupatta_philosophy, req.client_brief)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump() if result is not None else None


class GenerateDesignColorwaysRequest(StrictModel):
    fabric_name: str
    design: DesignProposal
    client_brief: ClientBrief | None = None
    fashion_context: RecommendationContext | None = None
    count: int = 3


@app.post("/v1/tools/generate-design-colorways")
def generate_design_colorways(req: GenerateDesignColorwaysRequest) -> list[dict]:
    results = _generate_design_colorways(
        req.fabric_name, req.design, req.client_brief, req.fashion_context, count=req.count
    )
    return [r.model_dump() for r in results]
