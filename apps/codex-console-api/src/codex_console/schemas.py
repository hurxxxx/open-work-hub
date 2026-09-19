from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DOCUMENT_CHAR_LIMIT = 100000
MESSAGE_CHAR_LIMIT = 32000


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=1, max_length=1024)


class NewTask(Input):
    title: str = Field(min_length=1, max_length=200)


class ImportThread(Input):
    thread_id: str = Field(min_length=1, max_length=160)
    confirm_inactive: Literal[True]


class Message(Input):
    operation_id: UUID
    text: str = Field(default="", max_length=MESSAGE_CHAR_LIMIT)
    stage: Literal["requirements", "plan"] = "requirements"
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.text and not self.attachment_ids:
            raise ValueError("A message or attachment is required")
        return self


class Implement(Input):
    operation_id: UUID
    revision_id: int = Field(gt=0)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)


class DocumentInput(Input):
    kind: Literal["requirements", "plan"]
    base_version: int = Field(ge=0)
    body: str = Field(min_length=1, max_length=DOCUMENT_CHAR_LIMIT)


class Recover(Input):
    confirm_workspace: bool = False


class Answer(Input):
    decision: Literal["accept", "decline", "cancel"] | None = None
    answers: dict[str, list[str]] | None = None


class SessionOut(BaseModel):
    authenticated: bool


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    version: int
    body: str
    created_at: str


class TaskOut(BaseModel):
    id: str
    title: str
    stage: str
    status: str
    thread_id: str | None
    turn_id: str | None
    root: str
    isolated: bool
    approved_revision: int | None
    error_code: str | None
    updated_at: str


class RequestOut(BaseModel):
    id: str
    method: str
    payload: dict[str, Any]


class TaskDetail(TaskOut):
    revisions: list[RevisionOut]
    items: list[dict[str, Any]]
    history_truncated: bool
    requests: list[RequestOut]
    event_id: int
    attachments: list["AttachmentOut"]
    attachment_limits: "AttachmentLimits"


class AttachmentOut(BaseModel):
    id: str
    name: str
    size: int
    deleted: bool


class AttachmentLimits(BaseModel):
    file_bytes: int
    task_bytes: int
    files: int
    selection: int


class AccountOut(BaseModel):
    connected: bool
    auth_type: str | None = None
    plan_type: str | None = None
    rate_limits: dict[str, Any] | None = None
    error_code: str | None = None


class DeviceLoginOut(BaseModel):
    login_id: str
    verification_url: str
    user_code: str


class ThreadSummary(BaseModel):
    id: str
    title: str
    preview: str
    updated_at: int


class ThreadPage(BaseModel):
    items: list[ThreadSummary]
    cursor: str | None


class ChangeOut(BaseModel):
    path: str
    status: str
    old_path: str | None


class DiffOut(BaseModel):
    path: str
    binary: bool
    old: str
    new: str


class Ok(BaseModel):
    ok: bool = True
