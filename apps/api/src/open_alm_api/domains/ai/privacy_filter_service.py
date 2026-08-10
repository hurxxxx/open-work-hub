from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.ai.privacy_filter import (
    PrivacyFilterDetection,
    PrivacyFilterHealth,
    PrivacyFilterSpan,
    check_privacy_filter_health,
    detect_privacy_filter_spans,
    prepare_privacy_filter,
)


class PrivacyFilterDetectRequest(BaseModel):
    texts: list[str] = Field(default_factory=list, max_length=128)


class PrivacyFilterSpanResponse(BaseModel):
    text_index: int
    start: int
    end: int
    label: str
    blocker_type: str
    entity_type: str


class PrivacyFilterDetectionResponse(BaseModel):
    status: str
    spans: list[PrivacyFilterSpanResponse]
    entity_types: list[str]
    blocker_types: list[str]
    pii_hits: list[str]
    enabled: bool
    used: bool
    error: str | None = None


class PrivacyFilterHealthResponse(BaseModel):
    enabled: bool
    ready: bool
    status: str
    checkpoint: str
    device: str
    detail: str | None = None


def _serialize_span(span: PrivacyFilterSpan) -> PrivacyFilterSpanResponse:
    return PrivacyFilterSpanResponse(
        text_index=span.text_index,
        start=span.start,
        end=span.end,
        label=span.label,
        blocker_type=span.blocker_type,
        entity_type=span.entity_type,
    )


def _serialize_detection(
    detection: PrivacyFilterDetection,
) -> PrivacyFilterDetectionResponse:
    return PrivacyFilterDetectionResponse(
        status=detection.status,
        spans=[_serialize_span(span) for span in detection.spans],
        entity_types=list(detection.entity_types),
        blocker_types=list(detection.blocker_types),
        pii_hits=list(detection.pii_hits),
        enabled=detection.enabled,
        used=detection.used,
        error=detection.error,
    )


def _serialize_health(health: PrivacyFilterHealth) -> PrivacyFilterHealthResponse:
    return PrivacyFilterHealthResponse(
        enabled=health.enabled,
        ready=health.ready,
        status=health.status,
        checkpoint=health.checkpoint,
        device=health.device,
        detail=health.detail,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.privacy_filter_health = prepare_privacy_filter(
        settings=settings,
        download=settings.opf_download_on_startup,
        use_service=False,
    )
    yield


app = FastAPI(
    title="Open ALM Privacy Filter",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/healthz", response_model=PrivacyFilterHealthResponse)
def healthz() -> PrivacyFilterHealthResponse:
    return _serialize_health(check_privacy_filter_health(deep=False, use_service=False))


@app.post("/detect", response_model=PrivacyFilterDetectionResponse)
def detect(request: PrivacyFilterDetectRequest) -> PrivacyFilterDetectionResponse:
    return _serialize_detection(
        detect_privacy_filter_spans(request.texts, use_service=False),
    )
