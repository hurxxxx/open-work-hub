from fastapi import APIRouter
from pydantic import BaseModel


class OcrRouteRequest(BaseModel):
    asset_uri: str
    layout_mode: str = "mixed"


class OcrRouteResponse(BaseModel):
    scenario_id: str = "ocr-pipeline"
    selected_engine: str
    fallback_engine: str
    quality_policy: str


router = APIRouter(prefix="/connectors", tags=["ocr"])


@router.post("/ocr/route", response_model=OcrRouteResponse)
def route_ocr(_: OcrRouteRequest) -> OcrRouteResponse:
    return OcrRouteResponse(
        selected_engine="PaddleOCR-VL-1.5",
        fallback_engine="DeepSeek-OCR",
        quality_policy="quality-first",
    )
