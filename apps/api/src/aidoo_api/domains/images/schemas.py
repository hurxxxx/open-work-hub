from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ImageBriefStatus = Literal["drafting", "ready", "approved"]
ImageGenerationStatus = Literal["idle", "queued", "running", "succeeded", "failed"]
ReferenceImageRole = Literal["style", "composition", "content"]
ContextRefKind = Literal["meeting", "task", "doc"]


class StylePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chips: list[str] = Field(default_factory=list, max_length=12)
    palette: str = Field(default="", max_length=32)
    background: str = Field(default="", max_length=32)
    quality: str = Field(default="high", max_length=32)


class LayoutPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    layout_id: str = Field(default="", max_length=64)
    aspect: str = Field(default="1024x1024", max_length=32)


class DetailsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    audience: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    source_generation_id: str = Field(default="", max_length=64)
    source_image_edit_instruction: str = Field(default="", max_length=2000)
    source_image_requires_plan: bool = False


class ContextRefSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=2000)


class ContextRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: ContextRefKind
    id: str = Field(max_length=128)
    snapshot: ContextRefSnapshot = Field(default_factory=ContextRefSnapshot)


class ReferenceImageRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    storage_key: str = Field(max_length=512)
    role: ReferenceImageRole = "style"
    content_type: str = Field(default="image/png", max_length=100)
    size_bytes: int = 0
    original_name: str = Field(default="", max_length=200)


class BriefVersion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(max_length=8000)
    created_at: datetime
    edit_instruction: str | None = None


class ImageGenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    owner_id: str
    template_id: str | None = None
    use_case: str
    use_case_other: str
    style: dict
    layout: dict
    details: dict
    context_refs: list[dict]
    reference_image_keys: list[dict]
    brief_versions: list[dict]
    brief_status: ImageBriefStatus
    image_status: ImageGenerationStatus
    image_storage_key: str | None
    image_model: str | None
    agent_trace_id: str | None
    failure_reason: str | None
    approved_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImageGenerationListResponse(BaseModel):
    items: list[ImageGenerationOut]
    next_cursor: str | None = None


class ImageGenerationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str | None = Field(default=None, max_length=80)
    use_case: str = Field(default="", max_length=64)
    use_case_other: str = Field(default="", max_length=200)
    style: StylePayload = Field(default_factory=StylePayload)
    layout: LayoutPayload = Field(default_factory=LayoutPayload)
    details: DetailsPayload = Field(default_factory=DetailsPayload)
    context_refs: list[ContextRef] = Field(default_factory=list, max_length=20)


class ImageGenerationPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str | None = Field(default=None, max_length=80)
    use_case: str | None = Field(default=None, max_length=64)
    use_case_other: str | None = Field(default=None, max_length=200)
    style: StylePayload | None = None
    layout: LayoutPayload | None = None
    details: DetailsPayload | None = None
    context_refs: list[ContextRef] | None = Field(default=None, max_length=20)


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edit_instruction: str | None = Field(default=None, max_length=2000)


class BriefVersionOut(BaseModel):
    text: str
    created_at: datetime
    edit_instruction: str | None = None


class ReferenceImageUploadOut(BaseModel):
    storage_key: str
    role: ReferenceImageRole
    content_type: str
    size_bytes: int
    original_name: str


class ImageDownloadResponse(BaseModel):
    url: str
    expires_at: datetime
