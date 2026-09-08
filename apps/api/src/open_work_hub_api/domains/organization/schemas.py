from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNIT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


def _normalize_unit_type(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if not UNIT_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("Organization unit type must be a lowercase identifier.")
    return normalized


def _normalize_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 2:
        raise ValueError("Organization unit name must contain at least two characters.")
    return normalized


class OrganizationUnitResponse(BaseModel):
    id: str
    name: str
    slug: str
    unit_type: str
    parent_id: str | None
    active: bool
    head_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationUnitSummaryResponse(BaseModel):
    id: str
    name: str
    slug: str
    unit_type: str
    active: bool
    head_user_id: str | None = None


class OrganizationUnitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    unit_type: str = Field(default="department", min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, max_length=36)
    active: bool = True
    head_user_id: str | None = Field(default=None, min_length=1, max_length=36)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_name(value)

    @field_validator("unit_type")
    @classmethod
    def validate_unit_type(cls, value: str) -> str:
        return _normalize_unit_type(value)


class OrganizationUnitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    unit_type: str | None = Field(default=None, min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, max_length=36)
    active: bool | None = None
    head_user_id: str | None = Field(default=None, min_length=1, max_length=36)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _normalize_name(value) if value is not None else None

    @field_validator("unit_type")
    @classmethod
    def validate_unit_type(cls, value: str | None) -> str | None:
        return _normalize_unit_type(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one organization unit field is required.")
        return self
