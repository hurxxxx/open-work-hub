from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GroupResponse(BaseModel):
    id: str
    kind: Literal["manual", "organization"]
    name: str
    description: str
    organization_unit_id: str | None
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
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)

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

    @field_validator("name", "description", "active", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Explicit null is not a valid group update.")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group name must not be blank.")
        return value.strip()


class GroupMembersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_ids: list[str] = Field(max_length=10000)


class GroupMembersResponse(BaseModel):
    group_id: str
    user_ids: list[str]


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
