"""Pydantic schemas for the personal learning notes API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_COURSE_SLUG_PATTERN = r"^[a-z0-9][a-z0-9\-]{0,63}$"
_LESSON_ID_PATTERN = r"^[a-z0-9][a-z0-9\-]{0,127}$"

MAX_CONTENT_BLOCKS_BYTES = 512 * 1024  # 512 KiB serialized JSON ceiling.

Visibility = Literal["public", "private"]


class LearningPageNoteUpsertRequest(BaseModel):
    course_slug: str = Field(..., min_length=1, max_length=64, pattern=_COURSE_SLUG_PATTERN)
    lesson_id: str = Field(..., min_length=1, max_length=128, pattern=_LESSON_ID_PATTERN)
    lesson_title: str = Field(..., min_length=1, max_length=200)
    visibility: Visibility = "private"
    content_blocks: list[dict] = Field(default_factory=list)


class LearningPageNoteListItem(BaseModel):
    """Minimal representation for the list view — body is fetched via detail."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str
    course_slug: str
    lesson_id: str
    visibility: Visibility
    author_id: str
    author_name: str
    is_mine: bool
    updated_at: datetime


class LearningPageNoteListResponse(BaseModel):
    items: list[LearningPageNoteListItem]


class LearningPageNoteDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doc_id: str
    page_id: str
    course_slug: str
    lesson_id: str
    visibility: Visibility
    author_id: str
    author_name: str
    is_mine: bool
    title: str
    content_blocks: list[dict]
    trashed_at: datetime | None
    created_at: datetime
    updated_at: datetime
