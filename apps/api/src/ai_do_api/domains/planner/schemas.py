"""Planner event schemas."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _camel_config() -> ConfigDict:
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PlannerEventCreateRequest(BaseModel):
    model_config = _camel_config()

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=240)
    all_day: bool = False
    start: str
    end: str


class PlannerEventUpdateRequest(BaseModel):
    model_config = _camel_config()

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=240)
    all_day: bool | None = None
    start: str | None = None
    end: str | None = None


class PlannerEventOut(BaseModel):
    model_config = _camel_config()

    id: str
    owner_id: str
    owner_name: str
    title: str
    description: str
    location: str
    time_zone: str
    all_day: bool
    start_has_time: bool
    end_has_time: bool
    start: str
    end: str
    created_at: datetime
    updated_at: datetime


class PlannerEventsResponse(BaseModel):
    model_config = _camel_config()

    items: list[PlannerEventOut]
