from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FailedFile(BaseModel):
    name: str
    reason: str


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    family: str
    family_name: str
    aspect: str
    n_slides: int
    attached_files: list[str] = Field(default_factory=list)
    failed_files: list[FailedFile] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | error | cancelled
    title: str | None = None
    message: str = ""
    family: str
    aspect: str
    n_slides: int = 0
    error: str | None = None
    # 다운로드 캐시버스팅용 (updated_at epoch)
    rev: int = 0
    # 진행 중(pending/running) 작업의 마지막 활동(updated_at)으로부터 경과 초 — 서버 계산.
    # 워커 하트비트가 12초마다 갱신하므로, 이 값이 크게 벌어지면 워커 멈춤 의심.
    heartbeat_age_seconds: int | None = None
    # 챗봇 수정 최신 턴 결과 (있을 때만)
    chat_result: dict | None = None
    # 프론트 HTML 렌더용 구조화 데이터 {family, slides:[{layout, data}]}
    slides_spec: dict | None = None
    # 'PPT로 전환'(finalize)로 .pptx 가 빌드돼 다운로드 가능한지 (= pptx_key 존재)
    pptx_ready: bool = False
    # 외부 웹 검색(Claude)으로 기초 정보 수집 시 참고한 출처 [{url, title}] — 미리보기 우측 표시용
    research_sources: list[dict] = Field(default_factory=list)


class JobListItem(BaseModel):
    job_id: str
    status: str
    title: str | None = None
    family: str
    aspect: str
    n_slides: int = 0
    error: str | None = None
    rev: int = 0
    pptx_ready: bool = False
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobListItem] = Field(default_factory=list)


class TemplatePreviewImageInfo(BaseModel):
    id: str
    url: str
    sort_order: int = 0
    created_at: datetime


class FinalizeResponse(BaseModel):
    ok: bool
    status: str  # processing


class CancelResponse(BaseModel):
    ok: bool
    status: str  # cancelled


class FamilyInfo(BaseModel):
    id: str
    name: str
    aspect: str
    multi_body: bool = True
    preview_images: list[TemplatePreviewImageInfo] = Field(default_factory=list)


class ChatEditRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)


class ChatEditResponse(BaseModel):
    ok: bool
    status: str  # processing
    message: str = ""
    conversation_id: str | None = None
