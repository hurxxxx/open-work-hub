from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReleaseNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    release_key: str
    title: str
    summary: str
    body: str
    published_at: datetime
    dismissed_at: datetime | None = None


class CurrentReleaseNoteResponse(BaseModel):
    item: ReleaseNoteOut | None


class ReleaseNotesResponse(BaseModel):
    items: list[ReleaseNoteOut]
