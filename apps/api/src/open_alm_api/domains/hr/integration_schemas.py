from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HrIntegrationBasis = Literal["erp", "groupware", "integrated"]
HrIntegrationSource = Literal["erp", "groupware"]
HrIntegrationRecordKind = Literal["employee", "external", "conflict"]
HrIntegrationReconciliationStatus = Literal[
    "matched",
    "erp_only",
    "groupware_only",
    "identity_conflict",
]


class _HrIntegrationResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HrIntegrationEmployeeResponse(_HrIntegrationResponseModel):
    subject_id: str
    record_kind: HrIntegrationRecordKind
    employee_code: str | None = None
    name: str | None = None
    email: str | None = None
    position: str | None = None
    occupation: str | None = None
    group_code: str | None = None
    group_name: str | None = None
    group_source: HrIntegrationSource | None = None
    source_systems: list[HrIntegrationSource] = Field(default_factory=list)
    has_erp: bool
    has_groupware: bool
    reconciliation_status: HrIntegrationReconciliationStatus | None = None
    reconciliation_detail: str | None = None
    inferred_workforce_category: str | None = None
    workforce_category: str | None = None
    workforce_category_resolution_kind: Literal["inferred", "manual"] | None = None
    identity_resolution_kind: Literal["employee_code", "manual", "none"] | None = None
    login_id: str | None = None
    account_status: str | None = None
    birth_date: date | None = None
    hire_date: date | None = None
    phone_number: str | None = None


class HrIntegrationEmployeesResponse(_HrIntegrationResponseModel):
    basis: HrIntegrationBasis
    snapshot_id: str
    schema_version: str
    projection_hash: str | None = None
    source_erp_run_id: str | None = None
    source_groupware_run_id: str | None = None
    identity_resolution_revision: int | None = None
    captured_at: datetime
    items: list[HrIntegrationEmployeeResponse]
    total: int
    page: int
    page_size: int


class HrIntegrationGroupResponse(_HrIntegrationResponseModel):
    subject_id: str
    code: str
    name: str
    source: HrIntegrationSource
    parent_code: str | None = None
    is_active: bool


class HrIntegrationGroupsResponse(_HrIntegrationResponseModel):
    basis: HrIntegrationBasis
    snapshot_id: str
    schema_version: str
    projection_hash: str | None = None
    source_erp_run_id: str | None = None
    source_groupware_run_id: str | None = None
    identity_resolution_revision: int | None = None
    captured_at: datetime
    items: list[HrIntegrationGroupResponse]
    total: int
    page: int
    page_size: int


class HrIntegrationStatusResponse(_HrIntegrationResponseModel):
    basis: HrIntegrationBasis
    available: bool
    snapshot_id: str | None = None
    schema_version: str | None = None
    projection_hash: str | None = None
    source_erp_run_id: str | None = None
    source_groupware_run_id: str | None = None
    identity_resolution_revision: int | None = None
    captured_at: datetime | None = None
    employee_count: int = 0
    group_count: int = 0


class HrIntegrationWorkforceCategoryResponse(_HrIntegrationResponseModel):
    code: str
    name: str
    description: str | None = None
    is_system: bool
    is_active: bool
    sort_order: int


class HrIntegrationWorkforceCategoriesResponse(_HrIntegrationResponseModel):
    items: list[HrIntegrationWorkforceCategoryResponse]
    total: int
