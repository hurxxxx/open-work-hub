"""Pydantic schemas for the industry-report API."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TrendCompanyOut(BaseModel):
    code: str
    label: str
    file_count: int = 0


class TrendCompanyListResponse(BaseModel):
    status: str = "success"
    companies: list[TrendCompanyOut]


class TrendFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company: str
    title: str
    filename: str
    content_type: str = ""
    size_bytes: int = 0
    published_date: str = ""
    source: str = "upload"


class TrendFileListResponse(BaseModel):
    status: str = "success"
    company: str
    company_label: str = ""
    files: list[TrendFileOut]


class IndustryReportItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    keyword: str = ""
    title: str
    org: str = ""
    summary: str = ""
    url: str
    published_date: str = ""
    extra: dict | None = None


class ItemListResponse(BaseModel):
    status: str = "success"
    source: str
    collected_at: str | None = None
    items: list[IndustryReportItemOut]


class AutojournalTocEntry(BaseModel):
    page: int
    title: str


class AutojournalIssueDetail(BaseModel):
    status: str = "success"
    issue_id: str
    total_pages: int = 0
    toc: list[AutojournalTocEntry] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)


class KdiPdfUrlResponse(BaseModel):
    status: str = "success"
    page_url: str
    pdf_url: str | None = None


class ReportSnapshotRequest(BaseModel):
    kind: str
    title: str
    org: str = ""
    published_date: str = ""
    url: str = ""
    file_id: str | None = None
    company: str = ""


class RecommendedReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: str
    org: str = ""
    published_date: str = ""
    url: str = ""
    file_id: str | None = None
    company: str = ""
    origin: str = "manual"
    reason: str = ""
    reason_detail: str = ""


class RecommendedReportListResponse(BaseModel):
    status: str = "success"
    items: list[RecommendedReportOut]


class ScrapReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: str
    org: str = ""
    published_date: str = ""
    url: str = ""
    file_id: str | None = None
    company: str = ""


class ScrapReportListResponse(BaseModel):
    status: str = "success"
    items: list[ScrapReportOut]


class ReportCurateResponse(BaseModel):
    status: str = "success"
    evaluated: int = 0
    saved: int = 0
    by_reason: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class ReportStatusResponse(BaseModel):
    collecting: bool = False
    collected_at: str | None = None
    is_today: bool = False


class ReportFetchResponse(BaseModel):
    status: str
    message: str
