from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SpecCompareJobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
SpecCompareRowStatus = Literal["same", "different", "base_only", "target_only", "unknown"]


class SpecCompareFileOut(BaseModel):
    name: str
    mime_type: str
    size_bytes: int


class SpecCompareJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    owner_id: str
    title: str
    status: SpecCompareJobStatus
    progress: int
    status_message: str
    failure_reason: str | None
    base_file: SpecCompareFileOut
    target_file: SpecCompareFileOut
    result_summary: dict | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SpecCompareJobListResponse(BaseModel):
    items: list[SpecCompareJobOut]


class SpecCompareRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spec_name: str = Field(max_length=300)
    base_value: str = ""
    target_value: str = ""
    status: SpecCompareRowStatus = "unknown"
    summary: str = ""
    base_evidence_ids: list[str] = Field(default_factory=list)
    target_evidence_ids: list[str] = Field(default_factory=list)


class SpecCompareResultResponse(BaseModel):
    job: SpecCompareJobOut
    report_markdown: str
    comparison_rows: list[SpecCompareRowOut]
    evidence_blocks: list[dict]
    summary: dict
    spec_items: dict[str, list[dict]] = Field(default_factory=dict)
