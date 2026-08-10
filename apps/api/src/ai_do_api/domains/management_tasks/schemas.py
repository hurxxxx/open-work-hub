from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AgeCalcMethod = Literal["korean", "international"]
DeterminationReason = Literal["senior", "adult_or_service", "deferred", "not_eligible", "dispatch"]
MatchStatus = Literal["matched", "unmatched", "ambiguous", "spouse_excluded"]


class HealthCheckupSourceStatusResponse(BaseModel):
    available: bool
    basis: Literal["erp"] = "erp"
    reason: str | None = None
    run_id: str | None = None
    erp_run_id: str | None = None
    captured_at: datetime | None = None
    employee_count: int = 0
    schema_version: str | None = None


class EmployeeDetermination(BaseModel):
    employee_id: str
    employee_code: str
    name: str
    dept_name: str
    position: str | None
    hire_date: date
    birth_date: date
    age: int
    service_years: int
    is_senior: bool
    is_adult: bool
    is_long_service: bool
    prior_year_examined: bool
    is_target: bool
    reason: DeterminationReason


class HealthCheckupDeterminationListResponse(BaseModel):
    run_id: str
    status: Literal["preview", "ready"]
    target_year: int
    prior_year: int
    publishable: bool
    publish_blockers: list[str]
    source: HealthCheckupSourceStatusResponse
    prior_exam_uploaded: bool
    total: int
    target_count: int
    items: list[EmployeeDetermination]


class PriorExamUnmatchedItem(BaseModel):
    sheet_name: str | None
    dept_name: str
    person_name: str
    raw_relation: str | None
    match_status: MatchStatus


class PriorExamMatchedItem(BaseModel):
    sheet_name: str | None
    employee_code: str
    person_name: str
    employee_name: str
    erp_dept_name: str
    file_dept_name: str


class HealthCheckupPriorExamUploadResponse(BaseModel):
    upload_id: str
    target_year: int
    exam_year: int
    source_filename: str | None
    total_rows: int
    matched_count: int
    spouse_excluded_count: int
    unmatched_count: int
    ambiguous_count: int
    publish_blockers: list[str]
    details_truncated: bool
    unmatched: list[PriorExamUnmatchedItem]
    matched: list[PriorExamMatchedItem]


class HealthCheckupPriorExamStatus(BaseModel):
    exam_year: int
    uploaded: bool
    source_filename: str | None
    matched_count: int
    uploaded_at: datetime | None
    publish_blockers: list[str]
    details_truncated: bool = False


class HealthCheckupSettingsResponse(BaseModel):
    age_calc_method: AgeCalcMethod
    senior_age: int
    adult_age: int
    service_years_threshold: int
    updated_by: str | None
    updated_at: datetime | None


class HealthCheckupSettingsUpdateRequest(BaseModel):
    age_calc_method: AgeCalcMethod | None = None
    senior_age: int | None = Field(default=None, ge=1, le=120)
    adult_age: int | None = Field(default=None, ge=1, le=120)
    service_years_threshold: int | None = Field(default=None, ge=0, le=80)

    @model_validator(mode="after")
    def validate_update(self) -> HealthCheckupSettingsUpdateRequest:
        values = (
            self.age_calc_method,
            self.senior_age,
            self.adult_age,
            self.service_years_threshold,
        )
        if not any(value is not None for value in values):
            raise ValueError("at least one setting is required")
        senior_age = self.senior_age
        adult_age = self.adult_age
        if senior_age is not None and adult_age is not None and senior_age < adult_age:
            raise ValueError("senior_age must be greater than or equal to adult_age")
        return self


class SettingsHistoryItem(BaseModel):
    id: str
    field_key: str
    old_value: str | None
    new_value: str | None
    changed_by: str | None
    changed_by_name: str | None
    created_at: datetime


class HealthCheckupSettingsHistoryResponse(BaseModel):
    items: list[SettingsHistoryItem]
