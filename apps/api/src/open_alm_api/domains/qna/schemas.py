from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from open_alm_api.domains.qna.models import QnaDocument


class QnaAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=20, ge=1, le=50)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)
    workspace_key: str | None = Field(default=None, min_length=1, max_length=120)


class QnaDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    title: str
    category: str
    author: str | None = None
    posted_at: str | None = None
    attachments: list[str] = Field(default_factory=list)
    char_count: int
    rag_status: str
    chunk_count: int
    uploaded_by: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, doc: QnaDocument) -> "QnaDocumentResponse":
        return cls(
            id=doc.id,
            kind=doc.kind,
            title=doc.title,
            category=doc.category,
            author=doc.author,
            posted_at=doc.posted_at,
            attachments=list(doc.attachments or []),
            char_count=doc.char_count,
            rag_status=doc.rag_status,
            chunk_count=doc.chunk_count,
            uploaded_by=doc.uploaded_by,
            indexed_at=doc.indexed_at,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class QnaDocumentDetailResponse(QnaDocumentResponse):
    body_text: str

    @classmethod
    def from_model(cls, doc: QnaDocument) -> "QnaDocumentDetailResponse":
        return cls(
            **QnaDocumentResponse.from_model(doc).model_dump(),
            body_text=doc.body_text or "",
        )


class QnaDocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[QnaDocumentResponse] = Field(default_factory=list)


class QnaNoticeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notices: list[QnaDocumentResponse] = Field(default_factory=list)


class QnaBoardSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queued: bool
