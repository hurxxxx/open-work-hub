from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UNIT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


def _normalize_unit_type(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if not UNIT_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("Organization unit type must be a lowercase identifier.")
    return normalized


class OrganizationUnitSummaryResponse(BaseModel):
    id: str
    name: str
    slug: str
    unit_type: str
    active: bool
    head_user_id: str | None = None


class GroupResponse(BaseModel):
    id: str
    source: Literal["local", "hr"]
    membership_mode: Literal["manual", "hr_assignment"]
    name: str
    description: str
    source_reference: str | None
    slug: str | None
    unit_type: str | None
    parent_id: str | None
    head_user_id: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class GroupListResponse(BaseModel):
    items: list[GroupResponse]
    total: int
    page: int
    page_size: int


class GroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["local", "hr"] = "local"
    source_reference: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    unit_type: str | None = Field(default=None, min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, min_length=1, max_length=36)
    head_user_id: str | None = Field(default=None, min_length=1, max_length=36)
    active: bool = True
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("unit_type")
    @classmethod
    def normalize_unit_type(cls, value: str | None) -> str | None:
        return _normalize_unit_type(value) if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group name must not be blank.")
        return value.strip()


class GroupUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    active: bool | None = None
    source_reference: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    unit_type: str | None = Field(default=None, min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, min_length=1, max_length=36)
    head_user_id: str | None = Field(default=None, min_length=1, max_length=36)

    @field_validator("name", "description", "active", "slug", "unit_type", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Explicit null is not a valid group update.")
        return value

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("unit_type")
    @classmethod
    def normalize_unit_type(cls, value: str | None) -> str | None:
        return _normalize_unit_type(value) if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group name must not be blank.")
        return value.strip()


class GroupMembersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[str] = Field(max_length=10000)


class GroupMemberResponse(BaseModel):
    id: str
    display_name: str
    login_id: str
    status: str
    login_blocked: bool


class GroupMembersResponse(BaseModel):
    group_id: str
    user_ids: list[str]
    items: list[GroupMemberResponse] = Field(default_factory=list)


class GroupMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned: bool


class CompanyDirectoryPersonResponse(BaseModel):
    id: str
    display_name: str
    primary_organization_unit_id: str | None
    job_title: str | None
    managed_organization_unit_ids: list[str]
    is_department_head: bool


class CompanyDirectoryPeopleResponse(BaseModel):
    items: list[CompanyDirectoryPersonResponse]
    total: int
    page: int
    page_size: int
