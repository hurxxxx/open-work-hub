"""Announcement schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


AnnouncementScope = Literal["workspace", "company"]


def _camel_config() -> ConfigDict:
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AnnouncementCreateRequest(BaseModel):
    model_config = _camel_config()

    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)
    scope: AnnouncementScope = "workspace"
    is_pinned: bool = False


class AnnouncementUpdateRequest(BaseModel):
    model_config = _camel_config()

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=20000)
    is_pinned: bool | None = None


class AnnouncementOut(BaseModel):
    model_config = _camel_config()

    id: str
    workspace_id: str
    author_id: str
    author_name: str
    scope: AnnouncementScope
    title: str
    body: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime


class AnnouncementsResponse(BaseModel):
    model_config = _camel_config()

    items: list[AnnouncementOut]
