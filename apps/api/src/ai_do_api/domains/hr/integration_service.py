from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import OrgUnit, User
from ai_do_api.domains.hr.groupware_sync import GROUPWARE_SOURCE_SYSTEM
from ai_do_api.domains.hr.history import (
    HR_SNAPSHOT_SCHEMA_VERSION,
    canonical_payload_hash,
    load_latest_applied_groupware_hr_sync_run,
)
from ai_do_api.domains.hr.identity_resolution import EXTERNAL_GROUPWARE_EMPLOYEE_CODES
from ai_do_api.domains.hr.integration_schemas import (
    HrIntegrationBasis,
    HrIntegrationEmployeeResponse,
    HrIntegrationEmployeesResponse,
    HrIntegrationGroupResponse,
    HrIntegrationGroupsResponse,
    HrIntegrationStatusResponse,
    HrIntegrationWorkforceCategoriesResponse,
    HrIntegrationWorkforceCategoryResponse,
)
from ai_do_api.domains.hr.master import (
    HR_MASTER_ERP_VIEW_SCHEMA_VERSION,
    HR_MASTER_SCHEMA_VERSION,
    HrMasterErpEmployeeSnapshotError,
    load_latest_hr_master_erp_employee_snapshot,
    load_latest_succeeded_hr_master_run,
)
from ai_do_api.domains.hr.models import (
    HrMasterConflictRow,
    HrMasterExternalPersonRow,
    HrMasterGroupRow,
    HrMasterPersonRow,
    HrWorkforceCategory,
)


class HrIntegrationProjectionError(RuntimeError):
    def __init__(self, *, basis: HrIntegrationBasis, reason: str):
        super().__init__(reason)
        self.basis = basis
        self.reason = reason


class HrIntegrationSnapshotUnavailable(HrIntegrationProjectionError):
    pass


class HrIntegrationSnapshotChanged(HrIntegrationProjectionError):
    pass


_PUBLIC_CONFLICT_REASON_CODES = frozenset({"duplicate_employee_code"})


@dataclass(frozen=True)
class _HrIntegrationDataset:
    basis: HrIntegrationBasis
    snapshot_id: str
    schema_version: str
    projection_hash: str | None
    source_erp_run_id: str | None
    source_groupware_run_id: str | None
    identity_resolution_revision: int | None
    captured_at: datetime
    employees: tuple[HrIntegrationEmployeeResponse, ...]
    groups: tuple[HrIntegrationGroupResponse, ...]


def _normalized_employee_code(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    return normalized or None


def _employee_subject_id(employee_code: str) -> str:
    return f"employee:{employee_code}"


def _groupware_subject_id(user_id: str) -> str:
    return _opaque_subject_id("groupware", user_id)


def _opaque_subject_id(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


def _public_email(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized or normalized.casefold().endswith("@groupware.local"):
        return None
    return normalized


def _subject_id_for_groupware_user(user: User) -> str:
    return _groupware_subject_id(user.id)


def _ensure_snapshot_pin(
    *,
    basis: HrIntegrationBasis,
    requested_snapshot_id: str | None,
    actual_snapshot_id: str,
) -> None:
    if requested_snapshot_id is None or requested_snapshot_id == actual_snapshot_id:
        return
    raise HrIntegrationSnapshotChanged(
        basis=basis,
        reason="requested_snapshot_is_not_current",
    )


def _erp_dataset(
    db: Session,
    *,
    snapshot_id: str | None,
) -> _HrIntegrationDataset:
    try:
        snapshot = load_latest_hr_master_erp_employee_snapshot(db)
    except HrMasterErpEmployeeSnapshotError as error:
        raise HrIntegrationSnapshotUnavailable(
            basis="erp",
            reason=error.code,
        ) from error
    if snapshot is None:
        raise HrIntegrationSnapshotUnavailable(
            basis="erp",
            reason="snapshot_not_found",
        )
    _ensure_snapshot_pin(
        basis="erp",
        requested_snapshot_id=snapshot_id,
        actual_snapshot_id=snapshot.run_id,
    )

    employees = tuple(
        sorted(
            (
                HrIntegrationEmployeeResponse(
                    subject_id=_employee_subject_id(employee.employee_code),
                    record_kind="employee",
                    employee_code=employee.employee_code,
                    name=employee.name,
                    position=employee.position,
                    occupation=employee.occupation,
                    group_code=employee.department_code,
                    group_name=employee.department_name,
                    group_source="erp",
                    source_systems=["erp"],
                    has_erp=True,
                    has_groupware=False,
                    birth_date=employee.birth_date,
                    hire_date=employee.hire_date,
                    phone_number=employee.phone_number,
                )
                for employee in snapshot.employees
            ),
            key=_employee_sort_key,
        )
    )

    group_names: dict[str, str] = {}
    for employee in snapshot.employees:
        existing_name = group_names.get(employee.department_code)
        if existing_name is not None and existing_name != employee.department_name:
            raise HrIntegrationSnapshotUnavailable(
                basis="erp",
                reason="conflicting_group_name",
            )
        group_names[employee.department_code] = employee.department_name
    groups = tuple(
        HrIntegrationGroupResponse(
            subject_id=f"group:erp:{code}",
            code=code,
            name=name,
            source="erp",
            is_active=True,
        )
        for code, name in sorted(group_names.items(), key=lambda item: (item[0], item[1]))
    )
    return _HrIntegrationDataset(
        basis="erp",
        snapshot_id=snapshot.run_id,
        schema_version=HR_MASTER_ERP_VIEW_SCHEMA_VERSION,
        projection_hash=snapshot.snapshot_hash,
        source_erp_run_id=snapshot.erp_run_id,
        source_groupware_run_id=None,
        identity_resolution_revision=None,
        captured_at=snapshot.captured_at,
        employees=employees,
        groups=groups,
    )


def _load_groupware_projection_rows(
    db: Session,
    *,
    applied_at: datetime,
) -> tuple[list[tuple[User, OrgUnit | None]], list[OrgUnit]]:
    user_rows = list(
        db.execute(
            select(User, OrgUnit)
            .outerjoin(OrgUnit, OrgUnit.id == User.primary_org_unit_id)
            .where(
                User.hr_source_system == GROUPWARE_SOURCE_SYSTEM,
                User.hr_last_synced_at == applied_at,
            )
            .order_by(
                func.lower(User.login_id),
                User.id,
            )
        ).all()
    )
    groups = list(
        db.scalars(
            select(OrgUnit)
            .where(
                OrgUnit.hr_source_system == GROUPWARE_SOURCE_SYSTEM,
                OrgUnit.hr_last_synced_at == applied_at,
            )
            .order_by(
                OrgUnit.hr_org_code,
                func.lower(OrgUnit.name),
                OrgUnit.id,
            )
        ).all()
    )
    return user_rows, groups


def _groupware_dataset(
    db: Session,
    *,
    snapshot_id: str | None,
) -> _HrIntegrationDataset:
    run = load_latest_applied_groupware_hr_sync_run(db)
    if run is None or run.schema_version != HR_SNAPSHOT_SCHEMA_VERSION or run.applied_at is None:
        raise HrIntegrationSnapshotUnavailable(
            basis="groupware",
            reason="snapshot_metadata_unavailable",
        )
    user_rows, group_rows = _load_groupware_projection_rows(
        db,
        applied_at=run.applied_at,
    )
    employees = tuple(
        sorted(
            (
                HrIntegrationEmployeeResponse(
                    subject_id=_subject_id_for_groupware_user(user),
                    record_kind=(
                        "external"
                        if _normalized_employee_code(user.employee_code)
                        in EXTERNAL_GROUPWARE_EMPLOYEE_CODES
                        or _normalized_employee_code(user.employee_code) is None
                        else "employee"
                    ),
                    employee_code=_normalized_employee_code(user.employee_code),
                    name=user.full_name,
                    email=_public_email(user.email),
                    position=user.job_title,
                    group_code=group.hr_org_code if group else None,
                    group_name=group.name if group else None,
                    group_source="groupware" if group else None,
                    source_systems=["groupware"],
                    has_erp=False,
                    has_groupware=True,
                    login_id=user.login_id,
                    account_status=user.status,
                )
                for user, group in user_rows
            ),
            key=_employee_sort_key,
        )
    )
    groups = tuple(
        HrIntegrationGroupResponse(
            subject_id=f"group:groupware:{group.hr_org_code}",
            code=group.hr_org_code,
            name=group.name,
            source="groupware",
            parent_code=group.hr_parent_org_code,
            is_active=group.active,
        )
        for group in group_rows
        if group.hr_org_code
    )
    projection_hash = canonical_payload_hash(
        {
            "schema_version": run.schema_version,
            "source_groupware_run_id": run.id,
            "captured_at": run.applied_at.isoformat(),
            "employees": [item.model_dump(mode="json") for item in employees],
            "groups": [item.model_dump(mode="json") for item in groups],
        }
    )
    _ensure_snapshot_pin(
        basis="groupware",
        requested_snapshot_id=snapshot_id,
        actual_snapshot_id=projection_hash,
    )
    return _HrIntegrationDataset(
        basis="groupware",
        snapshot_id=projection_hash,
        schema_version=run.schema_version,
        projection_hash=projection_hash,
        source_erp_run_id=None,
        source_groupware_run_id=run.id,
        identity_resolution_revision=None,
        captured_at=run.applied_at,
        employees=employees,
        groups=groups,
    )


def _integrated_person_item(row: HrMasterPersonRow) -> HrIntegrationEmployeeResponse:
    sources = [
        source
        for source, present in (
            ("erp", row.erp_snapshot_row_id is not None),
            ("groupware", row.groupware_snapshot_row_id is not None),
        )
        if present
    ]
    return HrIntegrationEmployeeResponse(
        subject_id=_employee_subject_id(row.employee_code),
        record_kind="employee",
        employee_code=row.employee_code,
        name=row.name,
        email=_public_email(row.email),
        position=row.position,
        occupation=row.occupation,
        group_code=row.group_code,
        group_name=row.group_name,
        group_source=row.group_source,
        source_systems=sources,
        has_erp=row.erp_snapshot_row_id is not None,
        has_groupware=row.groupware_snapshot_row_id is not None,
        reconciliation_status=(
            "identity_conflict" if row.has_identity_conflict else row.reconciliation_status
        ),
        inferred_workforce_category=row.inferred_workforce_category,
        workforce_category=row.workforce_category,
        workforce_category_resolution_kind=row.workforce_category_resolution_kind,
        identity_resolution_kind=row.identity_resolution_kind,
        login_id=row.login_id,
        birth_date=row.birth_date,
        hire_date=row.hire_date,
        phone_number=row.phone_number,
    )


def _integrated_external_item(
    row: HrMasterExternalPersonRow,
) -> HrIntegrationEmployeeResponse:
    return HrIntegrationEmployeeResponse(
        subject_id=_opaque_subject_id("external", row.groupware_source_identity),
        record_kind="external",
        employee_code=row.employee_code,
        name=row.name,
        email=_public_email(row.email),
        position=row.position,
        group_code=row.group_code,
        group_name=row.group_name,
        group_source="groupware" if row.group_code else None,
        source_systems=["groupware"],
        has_erp=False,
        has_groupware=True,
        reconciliation_status="groupware_only",
        inferred_workforce_category=row.inferred_workforce_category,
        workforce_category=row.workforce_category,
        workforce_category_resolution_kind=row.workforce_category_resolution_kind,
        identity_resolution_kind="none",
        login_id=row.login_id,
    )


def _integrated_conflict_item(row: HrMasterConflictRow) -> HrIntegrationEmployeeResponse:
    opaque_seed = ":".join(
        (
            row.master_run_id,
            row.id,
            row.source_system,
            row.reason_code,
        )
    )
    return HrIntegrationEmployeeResponse(
        subject_id=_opaque_subject_id("conflict", opaque_seed),
        record_kind="conflict",
        source_systems=[row.source_system],
        has_erp=row.source_system == "erp",
        has_groupware=row.source_system == "groupware",
        reconciliation_status="identity_conflict",
        reconciliation_detail=(
            row.reason_code
            if row.reason_code in _PUBLIC_CONFLICT_REASON_CODES
            else "unclassified_conflict"
        ),
        inferred_workforce_category=row.workforce_category,
        workforce_category=row.workforce_category,
        identity_resolution_kind="none",
    )


def _validate_integrated_counts(
    *,
    run_person_count: int,
    run_external_count: int,
    run_group_count: int,
    run_conflict_count: int,
    people: list[HrMasterPersonRow],
    external_people: list[HrMasterExternalPersonRow],
    groups: list[HrMasterGroupRow],
    conflicts: list[HrMasterConflictRow],
) -> bool:
    return (
        run_person_count == len(people)
        and run_external_count == len(external_people)
        and run_group_count == len(groups)
        and run_conflict_count == len(conflicts)
    )


def _integrated_dataset(
    db: Session,
    *,
    snapshot_id: str | None,
) -> _HrIntegrationDataset:
    run = load_latest_succeeded_hr_master_run(db)
    if (
        run is None
        or run.schema_version != HR_MASTER_SCHEMA_VERSION
        or run.rows_purged_at is not None
        or run.completed_at is None
        or not run.checksum
    ):
        raise HrIntegrationSnapshotUnavailable(
            basis="integrated",
            reason="snapshot_metadata_unavailable",
        )
    _ensure_snapshot_pin(
        basis="integrated",
        requested_snapshot_id=snapshot_id,
        actual_snapshot_id=run.id,
    )
    people = list(
        db.scalars(select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == run.id)).all()
    )
    external_people = list(
        db.scalars(
            select(HrMasterExternalPersonRow).where(
                HrMasterExternalPersonRow.master_run_id == run.id
            )
        ).all()
    )
    groups = list(
        db.scalars(select(HrMasterGroupRow).where(HrMasterGroupRow.master_run_id == run.id)).all()
    )
    conflicts = list(
        db.scalars(
            select(HrMasterConflictRow).where(HrMasterConflictRow.master_run_id == run.id)
        ).all()
    )
    if not _validate_integrated_counts(
        run_person_count=run.person_row_count,
        run_external_count=run.external_row_count,
        run_group_count=run.group_row_count,
        run_conflict_count=run.conflict_row_count,
        people=people,
        external_people=external_people,
        groups=groups,
        conflicts=conflicts,
    ):
        raise HrIntegrationSnapshotUnavailable(
            basis="integrated",
            reason="snapshot_row_count_mismatch",
        )

    employees = tuple(
        sorted(
            (
                *(_integrated_person_item(row) for row in people),
                *(_integrated_external_item(row) for row in external_people),
                *(_integrated_conflict_item(row) for row in conflicts),
            ),
            key=_employee_sort_key,
        )
    )
    group_items = tuple(
        sorted(
            (
                HrIntegrationGroupResponse(
                    subject_id=f"group:{row.source_system}:{row.source_code}",
                    code=row.source_code,
                    name=row.name,
                    source=row.source_system,
                    is_active=True,
                )
                for row in groups
            ),
            key=lambda item: (item.source, item.code, item.name, item.subject_id),
        )
    )
    return _HrIntegrationDataset(
        basis="integrated",
        snapshot_id=run.id,
        schema_version=run.schema_version,
        projection_hash=run.checksum,
        source_erp_run_id=run.erp_run_id,
        source_groupware_run_id=run.groupware_run_id,
        identity_resolution_revision=run.identity_resolution_revision,
        captured_at=run.completed_at,
        employees=employees,
        groups=group_items,
    )


def _employee_sort_key(item: HrIntegrationEmployeeResponse) -> tuple[object, ...]:
    return (
        item.employee_code is None,
        item.employee_code or "",
        (item.name or "").casefold(),
        item.record_kind,
        item.subject_id,
    )


def _load_dataset(
    db: Session,
    *,
    basis: HrIntegrationBasis,
    snapshot_id: str | None,
) -> _HrIntegrationDataset:
    if basis == "erp":
        return _erp_dataset(db, snapshot_id=snapshot_id)
    if basis == "groupware":
        return _groupware_dataset(db, snapshot_id=snapshot_id)
    return _integrated_dataset(db, snapshot_id=snapshot_id)


def list_hr_integration_employees(
    db: Session,
    *,
    basis: HrIntegrationBasis,
    snapshot_id: str | None,
    page: int,
    page_size: int,
) -> HrIntegrationEmployeesResponse:
    dataset = _load_dataset(db, basis=basis, snapshot_id=snapshot_id)
    start = (page - 1) * page_size
    return HrIntegrationEmployeesResponse(
        basis=basis,
        snapshot_id=dataset.snapshot_id,
        schema_version=dataset.schema_version,
        projection_hash=dataset.projection_hash,
        source_erp_run_id=dataset.source_erp_run_id,
        source_groupware_run_id=dataset.source_groupware_run_id,
        identity_resolution_revision=dataset.identity_resolution_revision,
        captured_at=dataset.captured_at,
        items=list(dataset.employees[start : start + page_size]),
        total=len(dataset.employees),
        page=page,
        page_size=page_size,
    )


def list_hr_integration_groups(
    db: Session,
    *,
    basis: HrIntegrationBasis,
    snapshot_id: str | None,
    page: int,
    page_size: int,
) -> HrIntegrationGroupsResponse:
    dataset = _load_dataset(db, basis=basis, snapshot_id=snapshot_id)
    start = (page - 1) * page_size
    return HrIntegrationGroupsResponse(
        basis=basis,
        snapshot_id=dataset.snapshot_id,
        schema_version=dataset.schema_version,
        projection_hash=dataset.projection_hash,
        source_erp_run_id=dataset.source_erp_run_id,
        source_groupware_run_id=dataset.source_groupware_run_id,
        identity_resolution_revision=dataset.identity_resolution_revision,
        captured_at=dataset.captured_at,
        items=list(dataset.groups[start : start + page_size]),
        total=len(dataset.groups),
        page=page,
        page_size=page_size,
    )


def get_hr_integration_status(
    db: Session,
    *,
    basis: HrIntegrationBasis,
) -> HrIntegrationStatusResponse:
    try:
        dataset = _load_dataset(db, basis=basis, snapshot_id=None)
    except HrIntegrationSnapshotUnavailable:
        return HrIntegrationStatusResponse(
            basis=basis,
            available=False,
        )
    return HrIntegrationStatusResponse(
        basis=basis,
        available=True,
        snapshot_id=dataset.snapshot_id,
        schema_version=dataset.schema_version,
        projection_hash=dataset.projection_hash,
        source_erp_run_id=dataset.source_erp_run_id,
        source_groupware_run_id=dataset.source_groupware_run_id,
        identity_resolution_revision=dataset.identity_resolution_revision,
        captured_at=dataset.captured_at,
        employee_count=len(dataset.employees),
        group_count=len(dataset.groups),
    )


def list_hr_integration_workforce_categories(
    db: Session,
    *,
    include_inactive: bool,
) -> HrIntegrationWorkforceCategoriesResponse:
    query = select(HrWorkforceCategory)
    if not include_inactive:
        query = query.where(HrWorkforceCategory.is_active.is_(True))
    rows = list(
        db.scalars(
            query.order_by(
                HrWorkforceCategory.sort_order,
                HrWorkforceCategory.code,
            )
        ).all()
    )
    items = [
        HrIntegrationWorkforceCategoryResponse(
            code=row.code,
            name=row.name,
            description=row.description,
            is_system=row.is_system,
            is_active=row.is_active,
            sort_order=row.sort_order,
        )
        for row in rows
    ]
    return HrIntegrationWorkforceCategoriesResponse(
        items=items,
        total=len(items),
    )
