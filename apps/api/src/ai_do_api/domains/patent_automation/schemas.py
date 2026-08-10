"""Pydantic request/response models for the patent-automation tool."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Field registry ──────────────────────────────────────────────────────────
class PatentFieldDefOut(BaseModel):
    key: str
    label_ko: str
    group_ko: str
    column_letter: str
    type: str
    is_promoted: bool


class PatentFieldsResponse(BaseModel):
    fields: list[PatentFieldDefOut]


# ── Progress timeline ─────────────────────────────────────────────────────────
class ProgressEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    seq: int
    event_date: str | None = None
    stage: str
    note: str | None = None


class ProgressEventIn(BaseModel):
    kind: str
    event_date: str | None = None
    stage: str = Field(min_length=1, max_length=200)
    note: str | None = None
    seq: int | None = None


# ── Records ───────────────────────────────────────────────────────────────────
class PatentRecordOut(BaseModel):
    id: str
    stable_record_id: str | None = None
    application_no: str | None = None
    registration_no: str | None = None
    invention_title: str | None = None
    inventors: str | None = None
    disclosure_date: str | None = None
    disclosure_year: int | None = None
    application_date: str | None = None
    application_year: int | None = None
    patent_status: str | None = None
    current_stage: str | None = None
    lifecycle_phase: str | None = None
    source_sheet: str | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)
    progress_events: list[ProgressEventOut] = Field(default_factory=list)
    updated_at: str | None = None


class PatentRecordListResponse(BaseModel):
    items: list[PatentRecordOut]
    total: int
    limit: int
    offset: int
    revision_id: str | None = None


class PatentRecordUpsert(BaseModel):
    """Create/update payload: arbitrary field_values keyed by field_defs key."""

    field_values: dict[str, Any] = Field(default_factory=dict)
    stable_record_id: str | None = None


# ── Import ────────────────────────────────────────────────────────────────────
class ImportPreviewColumn(BaseModel):
    index: int
    header: str
    sample_values: list[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    columns: list[ImportPreviewColumn]
    preview_rows: list[list[str]]
    suggested_mapping: dict[str, int]
    sheet_names: list[str] = Field(default_factory=list)
    total_preview_rows: int


class ImportResultResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    removed: int = 0
    total_rows: int
    progress_events: int = 0
    sheets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Revisions ─────────────────────────────────────────────────────────────────
class RevisionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_key: str
    revision_no: int | None = None
    status: str
    note: str | None = None


class RevisionListResponse(BaseModel):
    items: list[RevisionItem]
    active_draft_id: str | None = None
    published_id: str | None = None


class RevisionCreate(BaseModel):
    note: str | None = None


# ── History ───────────────────────────────────────────────────────────────────
class HistoryEntryOut(BaseModel):
    id: str
    action: str
    field_key: str | None = None
    field_label: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    actor_user_id: str | None = None
    created_at: str | None = None


class HistoryListResponse(BaseModel):
    items: list[HistoryEntryOut]


# ── Cost runs ─────────────────────────────────────────────────────────────────
class CostLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    region: str
    section: str
    seq: int | None = None
    vendor: str | None = None
    invoice_no: str | None = None
    application_no: str | None = None
    registration_no: str | None = None
    title: str | None = None
    inventors: str | None = None
    annuity_year: str | None = None
    supply_amount: int | None = None
    vat: int | None = None
    gov_fee: int | None = None
    line_total: int | None = None
    foreign_currency: str | None = None
    reconciled: bool = False
    record_id: str | None = None


class CostRunOut(BaseModel):
    id: str
    fiscal_period: str | None = None
    status: str
    industrial_total: int | None = None
    overseas_total: int | None = None
    warnings: list[str] = Field(default_factory=list)
    lines: list[CostLineOut] = Field(default_factory=list)
    has_industrial: bool = False
    has_overseas: bool = False
    created_at: str | None = None


class ApprovalHtmlOut(BaseModel):
    """품의 본문 HTML 생성 결과(클립보드 복사 + .txt 저장용)."""

    html: str
    filename: str
