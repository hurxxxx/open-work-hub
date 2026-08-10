from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.hr.erp_snapshot import (
    ERP_EMPLOYEE_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCOPE_KEY,
    ERP_SOURCE_SYSTEM,
)
from open_alm_api.domains.hr.groupware_sync import ACTIVE_COM_STATE, GROUPWARE_SOURCE_SYSTEM
from open_alm_api.domains.hr.history import (
    GROUPWARE_SCOPE_KEY,
    HR_SNAPSHOT_SCHEMA_VERSION,
    canonical_payload_hash,
    utcnow_naive,
)
from open_alm_api.domains.hr.identity_resolution import (
    EXTERNAL_GROUPWARE_EMPLOYEE_CODES,
    IdentityResolutionSnapshot,
    load_identity_resolution_snapshot,
)
from open_alm_api.domains.hr.models import (
    HrMasterConflictRow,
    HrMasterExternalPersonRow,
    HrMasterGroupRow,
    HrMasterPersonRow,
    HrMasterRun,
    HR_SNAPSHOT_RETENTION_DAYS,
    HrSyncOrgSnapshotRow,
    HrSyncRun,
    HrSyncUserSnapshotRow,
)


HR_MASTER_SCHEMA_VERSION = "hr-master-v5"
HR_MASTER_ERP_VIEW_SCHEMA_VERSION = "hr-master-erp-employee-v2"
HR_MASTER_CANONICALIZATION_VERSION = "employee-code-strip-uppercase-workforce-phone-v4"
SEOUL_TIME_ZONE = ZoneInfo("Asia/Seoul")


class HrMasterBuildError(RuntimeError):
    """A source pair cannot safely produce an HR master version."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HrMasterSnapshot:
    run: HrMasterRun
    people: tuple[HrMasterPersonRow, ...]
    external_people: tuple[HrMasterExternalPersonRow, ...]
    groups: tuple[HrMasterGroupRow, ...]
    conflicts: tuple[HrMasterConflictRow, ...]


class HrMasterErpEmployeeSnapshotError(RuntimeError):
    """A succeeded HR master cannot safely serve the ERP employee projection."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HrMasterErpEmployee:
    snapshot_row_id: str
    employee_code: str
    name: str
    department_code: str
    department_name: str
    position: str | None
    occupation: str
    birth_date: date
    hire_date: date
    phone_number: str | None = None

    def projection_payload(self) -> dict[str, object]:
        return {
            "employee_code": self.employee_code,
            "name": self.name,
            "department_code": self.department_code,
            "department_name": self.department_name,
            "position": self.position,
            "occupation": self.occupation,
            "birth_date": self.birth_date.isoformat(),
            "hire_date": self.hire_date.isoformat(),
            "phone_number": self.phone_number,
        }


@dataclass(frozen=True)
class HrMasterErpEmployeeSnapshot:
    run_id: str
    erp_run_id: str
    captured_at: datetime
    schema_version: str
    snapshot_hash: str
    employees: tuple[HrMasterErpEmployee, ...]


@dataclass(frozen=True)
class HrMasterErpEmployeeSnapshotMetadata:
    run_id: str
    erp_run_id: str
    captured_at: datetime
    schema_version: str
    snapshot_hash: str
    employee_count: int


@dataclass(frozen=True)
class _PreparedGroup:
    source_system: str
    source_code: str
    name: str
    source_snapshot_row_id: str

    def checksum_payload(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "source_code": self.source_code,
            "name": self.name,
            "source_snapshot_row_id": self.source_snapshot_row_id,
        }


@dataclass(frozen=True)
class _PreparedPerson:
    employee_code: str
    name: str
    position: str | None
    occupation: str | None
    birth_date: date | None
    hire_date: date | None
    phone_number: str | None
    email: str | None
    login_id: str | None
    group_source: str | None
    group_code: str | None
    group_name: str | None
    reconciliation_status: str
    inferred_workforce_category: str
    workforce_category: str
    workforce_category_resolution_kind: str
    workforce_assignment_id: str | None
    identity_resolution_kind: str
    has_identity_conflict: bool
    erp_snapshot_row_id: str | None
    groupware_snapshot_row_id: str | None
    groupware_source_identity: str | None
    manual_identity_link_id: str | None

    def checksum_payload(self) -> dict[str, object]:
        return {
            "employee_code": self.employee_code,
            "name": self.name,
            "position": self.position,
            "occupation": self.occupation,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "phone_number": self.phone_number,
            "email": self.email,
            "login_id": self.login_id,
            "group_source": self.group_source,
            "group_code": self.group_code,
            "group_name": self.group_name,
            "reconciliation_status": self.reconciliation_status,
            "inferred_workforce_category": self.inferred_workforce_category,
            "workforce_category": self.workforce_category,
            "workforce_category_resolution_kind": (self.workforce_category_resolution_kind),
            "workforce_assignment_id": self.workforce_assignment_id,
            "identity_resolution_kind": self.identity_resolution_kind,
            "has_identity_conflict": self.has_identity_conflict,
            "erp_snapshot_row_id": self.erp_snapshot_row_id,
            "groupware_snapshot_row_id": self.groupware_snapshot_row_id,
            "groupware_source_identity": self.groupware_source_identity,
            "manual_identity_link_id": self.manual_identity_link_id,
        }


@dataclass(frozen=True)
class _PreparedExternalPerson:
    groupware_source_identity: str
    employee_code: str | None
    name: str
    position: str | None
    email: str | None
    login_id: str | None
    group_code: str | None
    group_name: str | None
    inferred_workforce_category: str
    workforce_category: str
    workforce_category_resolution_kind: str
    workforce_assignment_id: str | None
    groupware_snapshot_row_id: str

    def checksum_payload(self) -> dict[str, object]:
        return self.__dict__


@dataclass(frozen=True)
class _PreparedConflict:
    source_system: str
    reason_code: str
    normalized_employee_code: str | None
    source_snapshot_row_id: str
    details: dict[str, Any] | None
    workforce_category: str

    def checksum_payload(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "reason_code": self.reason_code,
            "normalized_employee_code": self.normalized_employee_code,
            "source_snapshot_row_id": self.source_snapshot_row_id,
            "details": self.details,
            "workforce_category": self.workforce_category,
        }


def normalize_employee_code(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _required_text(payload: dict[str, Any], key: str, error_code: str) -> str:
    value = _clean_text(payload.get(key))
    if value is None:
        raise HrMasterBuildError(error_code)
    return value


def _required_date(payload: dict[str, Any], key: str, error_code: str) -> date:
    value = _required_text(payload, key, error_code)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise HrMasterBuildError(error_code) from error


def _erp_projection_hash(
    employees: list[HrMasterErpEmployee] | tuple[HrMasterErpEmployee, ...],
) -> str:
    return canonical_payload_hash([employee.projection_payload() for employee in employees])


def _prepared_erp_employee(person: _PreparedPerson) -> HrMasterErpEmployee:
    if (
        person.erp_snapshot_row_id is None
        or person.group_code is None
        or person.group_name is None
        or person.occupation is None
        or person.birth_date is None
        or person.hire_date is None
    ):
        raise HrMasterBuildError("invalid_erp_projection")
    return HrMasterErpEmployee(
        snapshot_row_id=person.erp_snapshot_row_id,
        employee_code=person.employee_code,
        name=person.name,
        department_code=person.group_code,
        department_name=person.group_name,
        position=person.position,
        occupation=person.occupation,
        birth_date=person.birth_date,
        hire_date=person.hire_date,
        phone_number=person.phone_number,
    )


def _load_source_run(
    db: Session,
    *,
    run_id: str,
    source_system: str,
    scope_key: str,
    schema_version: str,
) -> HrSyncRun:
    run = db.get(HrSyncRun, run_id)
    if run is None:
        raise HrMasterBuildError(f"{source_system}_run_not_found")
    if run.source_system != source_system or run.scope_key != scope_key:
        raise HrMasterBuildError(f"invalid_{source_system}_run")
    if run.status != "succeeded":
        raise HrMasterBuildError(f"{source_system}_run_not_succeeded")
    if run.schema_version != schema_version:
        raise HrMasterBuildError(f"unsupported_{source_system}_schema")
    if run.snapshots_purged_at is not None:
        raise HrMasterBuildError(f"{source_system}_snapshot_unavailable")
    if run.captured_at is None:
        raise HrMasterBuildError(f"{source_system}_metadata_incomplete")
    return run


def _load_snapshot_rows(
    db: Session,
    *,
    run: HrSyncRun,
) -> tuple[list[HrSyncUserSnapshotRow], list[HrSyncOrgSnapshotRow]]:
    user_rows = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == run.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    org_rows = list(
        db.scalars(
            select(HrSyncOrgSnapshotRow)
            .where(HrSyncOrgSnapshotRow.run_id == run.id)
            .order_by(HrSyncOrgSnapshotRow.source_row_no)
        ).all()
    )
    if run.user_row_count is None or len(user_rows) != run.user_row_count:
        raise HrMasterBuildError(f"{run.source_system}_user_row_count_mismatch")
    if run.org_row_count is None or len(org_rows) != run.org_row_count:
        raise HrMasterBuildError(f"{run.source_system}_group_row_count_mismatch")
    user_hash = canonical_payload_hash([row.raw_payload for row in user_rows])
    org_hash = canonical_payload_hash([row.raw_payload for row in org_rows])
    if not run.user_snapshot_hash or user_hash != run.user_snapshot_hash:
        raise HrMasterBuildError(f"{run.source_system}_user_hash_mismatch")
    if not run.org_snapshot_hash or org_hash != run.org_snapshot_hash:
        raise HrMasterBuildError(f"{run.source_system}_group_hash_mismatch")
    return user_rows, org_rows


def _prepare_erp_groups(
    rows: list[HrSyncOrgSnapshotRow],
) -> tuple[list[_PreparedGroup], dict[str, str]]:
    prepared: list[_PreparedGroup] = []
    names_by_code: dict[str, str] = {}
    for row in rows:
        code = normalize_employee_code(row.raw_payload.get("DEPT_CD"))
        name = _clean_text(row.raw_payload.get("DEPT_NM"))
        if code is None or name is None:
            raise HrMasterBuildError("invalid_erp_group")
        existing_name = names_by_code.get(code)
        if existing_name is not None and existing_name != name:
            raise HrMasterBuildError("conflicting_erp_group_name")
        if existing_name is not None:
            raise HrMasterBuildError("duplicate_erp_group")
        names_by_code[code] = name
        prepared.append(
            _PreparedGroup(
                source_system=ERP_SOURCE_SYSTEM,
                source_code=code,
                name=name,
                source_snapshot_row_id=row.id,
            )
        )
    if not prepared:
        raise HrMasterBuildError("empty_erp_groups")
    return prepared, names_by_code


def _prepare_groupware_groups(
    rows: list[HrSyncOrgSnapshotRow],
) -> tuple[list[_PreparedGroup], dict[tuple[int | None, str], str]]:
    prepared: list[_PreparedGroup] = []
    names_by_identity: dict[tuple[int | None, str], str] = {}
    seen_codes: set[str] = set()
    for row in rows:
        code = _clean_text(row.raw_payload.get("org_code"))
        name = _clean_text(row.raw_payload.get("org_depart"))
        domain_num = row.raw_payload.get("domain_num")
        if code is None or name is None:
            raise HrMasterBuildError("invalid_groupware_group")
        identity = (int(domain_num) if domain_num is not None else None, code)
        if identity in names_by_identity:
            raise HrMasterBuildError("duplicate_groupware_group")
        if code in seen_codes:
            raise HrMasterBuildError("ambiguous_groupware_group_code")
        seen_codes.add(code)
        names_by_identity[identity] = name
        prepared.append(
            _PreparedGroup(
                source_system=GROUPWARE_SOURCE_SYSTEM,
                source_code=code,
                name=name,
                source_snapshot_row_id=row.id,
            )
        )
    return prepared, names_by_identity


def _primary_groupware_org_code(payload: dict[str, Any]) -> str | None:
    org_codes = [_clean_text(payload.get(f"org_code{index}")) for index in range(1, 7)]
    raw_level = payload.get("org_level")
    if raw_level is not None:
        try:
            level = int(raw_level)
        except (TypeError, ValueError):
            level = 0
        if 1 <= level <= len(org_codes) and org_codes[level - 1] is not None:
            return org_codes[level - 1]
    return next((code for code in reversed(org_codes) if code is not None), None)


def _prepare_master_rows(
    *,
    erp_user_rows: list[HrSyncUserSnapshotRow],
    groupware_user_rows: list[HrSyncUserSnapshotRow],
    erp_group_names: dict[str, str],
    groupware_group_names: dict[tuple[int | None, str], str],
    identity_resolution: IdentityResolutionSnapshot,
) -> tuple[
    list[_PreparedPerson],
    list[_PreparedExternalPerson],
    list[_PreparedConflict],
]:
    erp_by_code: dict[str, HrSyncUserSnapshotRow] = {}
    for row in erp_user_rows:
        code = normalize_employee_code(row.raw_payload.get("EMP_NO"))
        if code is None:
            raise HrMasterBuildError("missing_erp_employee_code")
        if code in erp_by_code:
            raise HrMasterBuildError("duplicate_normalized_erp_employee_code")
        erp_by_code[code] = row

    workforce_assignments_by_subject = {
        (assignment.subject_kind, assignment.subject_key): assignment
        for assignment in identity_resolution.workforce_assignments
    }
    if len(workforce_assignments_by_subject) != len(identity_resolution.workforce_assignments):
        raise HrMasterBuildError("duplicate_workforce_assignment_subject")

    def resolve_workforce_category(
        inferred_category: str,
        *,
        erp_employee_code: str | None = None,
        groupware_source_identity: str | None = None,
    ) -> tuple[str, str, str | None]:
        assignment = (
            workforce_assignments_by_subject.get(("erp_employee", erp_employee_code))
            if erp_employee_code
            else None
        )
        if assignment is None and groupware_source_identity:
            assignment = workforce_assignments_by_subject.get(
                ("groupware_identity", groupware_source_identity)
            )
        if assignment is None:
            return inferred_category, "inferred", None
        return assignment.category_code, "manual", assignment.id

    groupware_rows_by_code: dict[str, list[HrSyncUserSnapshotRow]] = defaultdict(list)
    groupware_by_source_identity: dict[str, HrSyncUserSnapshotRow] = {}
    external_people: list[_PreparedExternalPerson] = []
    conflicts: list[_PreparedConflict] = []
    for row in groupware_user_rows:
        if row.raw_payload.get("com_state") != ACTIVE_COM_STATE:
            continue
        source_identity = _clean_text(row.source_identity)
        if source_identity is None or source_identity in groupware_by_source_identity:
            raise HrMasterBuildError("invalid_groupware_source_identity")
        groupware_by_source_identity[source_identity] = row
        code = normalize_employee_code(row.raw_payload.get("com_num"))
        if code is None or code in EXTERNAL_GROUPWARE_EMPLOYEE_CODES:
            payload = row.raw_payload
            group_code = _primary_groupware_org_code(payload)
            domain_num_value = payload.get("domain_num")
            domain_num = int(domain_num_value) if domain_num_value is not None else None
            group_name = (
                groupware_group_names.get((domain_num, group_code))
                if group_code is not None
                else None
            )
            if group_code is not None and group_name is None:
                raise HrMasterBuildError("invalid_groupware_employee_group")
            (
                workforce_category,
                workforce_resolution_kind,
                workforce_assignment_id,
            ) = resolve_workforce_category(
                "external",
                groupware_source_identity=source_identity,
            )
            external_people.append(
                _PreparedExternalPerson(
                    groupware_source_identity=source_identity,
                    employee_code=code,
                    name=_clean_text(payload.get("kor_name")) or source_identity,
                    position=_clean_text(payload.get("com_position")),
                    email=_clean_text(payload.get("email")),
                    login_id=_clean_text(payload.get("user_id")),
                    group_code=group_code,
                    group_name=group_name,
                    inferred_workforce_category="external",
                    workforce_category=workforce_category,
                    workforce_category_resolution_kind=workforce_resolution_kind,
                    workforce_assignment_id=workforce_assignment_id,
                    groupware_snapshot_row_id=row.id,
                )
            )
            continue
        groupware_rows_by_code[code].append(row)

    duplicate_groupware_codes = {
        code for code, rows in groupware_rows_by_code.items() if len(rows) > 1
    }
    for code in sorted(duplicate_groupware_codes):
        duplicate_rows = groupware_rows_by_code[code]
        for row in duplicate_rows:
            conflicts.append(
                _PreparedConflict(
                    source_system=GROUPWARE_SOURCE_SYSTEM,
                    reason_code="duplicate_employee_code",
                    normalized_employee_code=code,
                    source_snapshot_row_id=row.id,
                    details={
                        "source_row_no": row.source_row_no,
                        "duplicate_count": len(duplicate_rows),
                    },
                    workforce_category="unresolved",
                )
            )

    unique_groupware_by_code = {
        code: rows[0] for code, rows in groupware_rows_by_code.items() if len(rows) == 1
    }
    manual_groupware_by_erp: dict[str, tuple[HrSyncUserSnapshotRow, str]] = {}
    manually_consumed_groupware_codes: set[str] = set()
    for link in identity_resolution.links:
        groupware_row = groupware_by_source_identity.get(link.groupware_source_identity)
        erp_row = erp_by_code.get(link.erp_employee_code)
        if groupware_row is None or erp_row is None:
            continue
        groupware_code = normalize_employee_code(groupware_row.raw_payload.get("com_num"))
        if (
            groupware_code is None
            or groupware_code in EXTERNAL_GROUPWARE_EMPLOYEE_CODES
            or groupware_code in erp_by_code
            or unique_groupware_by_code.get(groupware_code) is not groupware_row
            or unique_groupware_by_code.get(link.erp_employee_code) is not None
        ):
            raise HrMasterBuildError("stale_manual_identity_link")
        if link.erp_employee_code in manual_groupware_by_erp:
            raise HrMasterBuildError("duplicate_manual_identity_target")
        manual_groupware_by_erp[link.erp_employee_code] = (groupware_row, link.id)
        manually_consumed_groupware_codes.add(groupware_code)

    candidate_erp_names = {
        _clean_text(row.raw_payload.get("NAME"))
        for code, row in erp_by_code.items()
        if code not in unique_groupware_by_code
        and code not in duplicate_groupware_codes
        and code not in manual_groupware_by_erp
    }
    candidate_erp_names.discard(None)
    candidate_names = {
        name
        for code, row in unique_groupware_by_code.items()
        if code not in erp_by_code and code not in manually_consumed_groupware_codes
        if (name := _clean_text(row.raw_payload.get("kor_name"))) in candidate_erp_names
    }

    people: list[_PreparedPerson] = []
    all_codes = sorted(
        set(erp_by_code) | (set(unique_groupware_by_code) - manually_consumed_groupware_codes)
    )
    for code in all_codes:
        erp_row = erp_by_code.get(code)
        groupware_row = unique_groupware_by_code.get(code)
        if erp_row is not None:
            manual_link_id: str | None = None
            if groupware_row is None and code in manual_groupware_by_erp:
                groupware_row, manual_link_id = manual_groupware_by_erp[code]
            erp_payload = erp_row.raw_payload
            group_code = normalize_employee_code(erp_payload.get("DEPT_CD"))
            group_name = _clean_text(erp_payload.get("DEPT_NM"))
            if (
                group_code is None
                or group_name is None
                or erp_group_names.get(group_code) != group_name
            ):
                raise HrMasterBuildError("invalid_erp_employee_group")
            groupware_payload = groupware_row.raw_payload if groupware_row is not None else {}
            groupware_email = _clean_text(groupware_payload.get("email"))
            reconciliation_status = (
                "matched"
                if groupware_row is not None
                else ("identity_conflict" if code in duplicate_groupware_codes else "erp_only")
            )
            erp_name = _required_text(erp_payload, "NAME", "missing_erp_name")
            inferred_workforce_category = (
                "internal"
                if groupware_row is not None
                else (
                    "unresolved"
                    if code in duplicate_groupware_codes or erp_name in candidate_names
                    else "field"
                )
            )
            (
                workforce_category,
                workforce_resolution_kind,
                workforce_assignment_id,
            ) = resolve_workforce_category(
                inferred_workforce_category,
                erp_employee_code=code,
                groupware_source_identity=(
                    groupware_row.source_identity if groupware_row is not None else None
                ),
            )
            people.append(
                _PreparedPerson(
                    employee_code=code,
                    name=erp_name,
                    position=_clean_text(erp_payload.get("ROLL_PSTN_NM")),
                    occupation=_required_text(
                        erp_payload,
                        "OCPT_NM",
                        "missing_erp_occupation",
                    ),
                    birth_date=_required_date(
                        erp_payload,
                        "BIRTHDAY",
                        "invalid_erp_birth_date",
                    ),
                    hire_date=_required_date(
                        erp_payload,
                        "ENTR_DT",
                        "invalid_erp_hire_date",
                    ),
                    phone_number=_clean_text(erp_payload.get("HAND_TEL_NO")),
                    email=groupware_email or _clean_text(erp_payload.get("EMAIL_ADDR")),
                    login_id=_clean_text(groupware_payload.get("user_id")),
                    group_source=ERP_SOURCE_SYSTEM,
                    group_code=group_code,
                    group_name=group_name,
                    reconciliation_status=reconciliation_status,
                    inferred_workforce_category=inferred_workforce_category,
                    workforce_category=workforce_category,
                    workforce_category_resolution_kind=workforce_resolution_kind,
                    workforce_assignment_id=workforce_assignment_id,
                    identity_resolution_kind=(
                        "manual"
                        if manual_link_id is not None
                        else ("employee_code" if groupware_row is not None else "none")
                    ),
                    has_identity_conflict=code in duplicate_groupware_codes,
                    erp_snapshot_row_id=erp_row.id,
                    groupware_snapshot_row_id=groupware_row.id if groupware_row else None,
                    groupware_source_identity=(
                        groupware_row.source_identity if groupware_row is not None else None
                    ),
                    manual_identity_link_id=manual_link_id,
                )
            )
            continue

        if groupware_row is None:
            continue
        groupware_payload = groupware_row.raw_payload
        group_code = _primary_groupware_org_code(groupware_payload)
        domain_num_value = groupware_payload.get("domain_num")
        domain_num = int(domain_num_value) if domain_num_value is not None else None
        group_name = (
            groupware_group_names.get((domain_num, group_code)) if group_code is not None else None
        )
        if group_code is not None and group_name is None:
            raise HrMasterBuildError("invalid_groupware_employee_group")
        (
            workforce_category,
            workforce_resolution_kind,
            workforce_assignment_id,
        ) = resolve_workforce_category(
            "unresolved",
            groupware_source_identity=groupware_row.source_identity,
        )
        people.append(
            _PreparedPerson(
                employee_code=code,
                name=_clean_text(groupware_payload.get("kor_name")) or code,
                position=_clean_text(groupware_payload.get("com_position")),
                occupation=None,
                birth_date=None,
                hire_date=None,
                phone_number=None,
                email=_clean_text(groupware_payload.get("email")),
                login_id=_clean_text(groupware_payload.get("user_id")),
                group_source=GROUPWARE_SOURCE_SYSTEM if group_code is not None else None,
                group_code=group_code,
                group_name=group_name,
                reconciliation_status="groupware_only",
                inferred_workforce_category="unresolved",
                workforce_category=workforce_category,
                workforce_category_resolution_kind=workforce_resolution_kind,
                workforce_assignment_id=workforce_assignment_id,
                identity_resolution_kind="none",
                has_identity_conflict=False,
                erp_snapshot_row_id=None,
                groupware_snapshot_row_id=groupware_row.id,
                groupware_source_identity=groupware_row.source_identity,
                manual_identity_link_id=None,
            )
        )
    return people, external_people, conflicts


def _find_succeeded_run(
    db: Session,
    *,
    erp_run_id: str,
    groupware_run_id: str,
    identity_resolution_revision: int,
) -> HrMasterRun | None:
    return db.scalar(
        select(HrMasterRun).where(
            HrMasterRun.erp_run_id == erp_run_id,
            HrMasterRun.groupware_run_id == groupware_run_id,
            HrMasterRun.schema_version == HR_MASTER_SCHEMA_VERSION,
            HrMasterRun.identity_resolution_revision == identity_resolution_revision,
            HrMasterRun.status == "succeeded",
        )
    )


def build_hr_master_run(
    db: Session,
    *,
    erp_run_id: str,
    groupware_run_id: str,
    idempotency_key: str | None = None,
    built_at: datetime | None = None,
) -> HrMasterRun:
    """Build an idempotent master version from the two explicitly named snapshots."""

    now = built_at or utcnow_naive()
    identity_resolution = load_identity_resolution_snapshot(db)
    stable_key = idempotency_key or (
        f"{HR_MASTER_SCHEMA_VERSION}:{erp_run_id}:{groupware_run_id}:{identity_resolution.revision}"
    )
    existing = _find_succeeded_run(
        db,
        erp_run_id=erp_run_id,
        groupware_run_id=groupware_run_id,
        identity_resolution_revision=identity_resolution.revision,
    )
    if existing is not None:
        return existing

    run = HrMasterRun(
        id=new_id(),
        status="building",
        idempotency_key=stable_key,
        erp_run_id=erp_run_id,
        groupware_run_id=groupware_run_id,
        schema_version=HR_MASTER_SCHEMA_VERSION,
        identity_resolution_revision=identity_resolution.revision,
        identity_resolution_hash=identity_resolution.snapshot_hash,
        started_at=now,
        created_at=now,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = _find_succeeded_run(
            db,
            erp_run_id=erp_run_id,
            groupware_run_id=groupware_run_id,
            identity_resolution_revision=identity_resolution.revision,
        )
        if concurrent is not None:
            return concurrent
        raise

    try:
        erp_run = _load_source_run(
            db,
            run_id=erp_run_id,
            source_system=ERP_SOURCE_SYSTEM,
            scope_key=ERP_EMPLOYEE_SCOPE_KEY,
            schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
        )
        groupware_run = _load_source_run(
            db,
            run_id=groupware_run_id,
            source_system=GROUPWARE_SOURCE_SYSTEM,
            scope_key=GROUPWARE_SCOPE_KEY,
            schema_version=HR_SNAPSHOT_SCHEMA_VERSION,
        )
        erp_user_rows, erp_org_rows = _load_snapshot_rows(db, run=erp_run)
        groupware_user_rows, groupware_org_rows = _load_snapshot_rows(
            db,
            run=groupware_run,
        )
        erp_groups, erp_group_names = _prepare_erp_groups(erp_org_rows)
        groupware_groups, groupware_group_names = _prepare_groupware_groups(groupware_org_rows)
        people, external_people, conflicts = _prepare_master_rows(
            erp_user_rows=erp_user_rows,
            groupware_user_rows=groupware_user_rows,
            erp_group_names=erp_group_names,
            groupware_group_names=groupware_group_names,
            identity_resolution=identity_resolution,
        )
        groups = sorted(
            [*erp_groups, *groupware_groups],
            key=lambda group: (group.source_system, group.source_code),
        )
        people.sort(key=lambda person: person.employee_code)
        external_people.sort(
            key=lambda person: (
                person.employee_code or "",
                person.name,
                person.groupware_source_identity,
            )
        )
        erp_employees = [
            _prepared_erp_employee(person)
            for person in people
            if person.erp_snapshot_row_id is not None
        ]
        erp_projection_hash = _erp_projection_hash(erp_employees)
        conflicts.sort(
            key=lambda conflict: (
                conflict.normalized_employee_code or "",
                conflict.reason_code,
                conflict.source_snapshot_row_id,
            )
        )
        checksum = canonical_payload_hash(
            {
                "schema_version": HR_MASTER_SCHEMA_VERSION,
                "canonicalization_version": HR_MASTER_CANONICALIZATION_VERSION,
                "erp_run_id": erp_run.id,
                "groupware_run_id": groupware_run.id,
                "identity_resolution_revision": identity_resolution.revision,
                "identity_resolution_hash": identity_resolution.snapshot_hash,
                "people": [person.checksum_payload() for person in people],
                "external_people": [person.checksum_payload() for person in external_people],
                "groups": [group.checksum_payload() for group in groups],
                "conflicts": [conflict.checksum_payload() for conflict in conflicts],
            }
        )

        for person in people:
            db.add(
                HrMasterPersonRow(
                    id=new_id(),
                    master_run_id=run.id,
                    **person.__dict__,
                    created_at=now,
                )
            )
        for group in groups:
            db.add(
                HrMasterGroupRow(
                    id=new_id(),
                    master_run_id=run.id,
                    **group.__dict__,
                    created_at=now,
                )
            )
        for external_person in external_people:
            db.add(
                HrMasterExternalPersonRow(
                    id=new_id(),
                    master_run_id=run.id,
                    **external_person.__dict__,
                    created_at=now,
                )
            )
        for conflict in conflicts:
            db.add(
                HrMasterConflictRow(
                    id=new_id(),
                    master_run_id=run.id,
                    **conflict.__dict__,
                    created_at=now,
                )
            )

        status_counts = Counter(person.reconciliation_status for person in people)
        workforce_counts = Counter(person.workforce_category for person in people)
        workforce_counts.update(person.workforce_category for person in external_people)
        conflict_reason_counts = Counter(conflict.reason_code for conflict in conflicts)
        run.status = "succeeded"
        run.checksum = checksum
        run.erp_projection_hash = erp_projection_hash
        run.person_row_count = len(people)
        run.group_row_count = len(groups)
        run.conflict_row_count = len(conflicts)
        run.external_row_count = len(external_people)
        run.result_payload = {
            "erp_run_id": erp_run.id,
            "groupware_run_id": groupware_run.id,
            "checksum": checksum,
            "erp_projection_hash": erp_projection_hash,
            "erp_employee_count": len(erp_employees),
            "identity_resolution_revision": identity_resolution.revision,
            "identity_resolution_hash": identity_resolution.snapshot_hash,
            "manual_identity_link_count": len(identity_resolution.links),
            "workforce_assignment_count": len(identity_resolution.workforce_assignments),
            "person_row_count": len(people),
            "external_row_count": len(external_people),
            "group_row_count": len(groups),
            "conflict_row_count": len(conflicts),
            "status_counts": dict(sorted(status_counts.items())),
            "workforce_counts": dict(sorted(workforce_counts.items())),
            "conflict_reason_counts": dict(sorted(conflict_reason_counts.items())),
        }
        run.completed_at = now
        db.commit()
        return run
    except HrMasterBuildError as error:
        db.rollback()
        failed_run = db.get(HrMasterRun, run.id)
        if failed_run is None:
            raise
        failed_run.status = "failed"
        failed_run.error_code = error.code
        failed_run.error_summary = error.code
        failed_run.result_payload = {
            "erp_run_id": erp_run_id,
            "groupware_run_id": groupware_run_id,
            "identity_resolution_revision": identity_resolution.revision,
            "rejection_reason": error.code,
        }
        failed_run.completed_at = now
        db.commit()
        return failed_run
    except IntegrityError as error:
        db.rollback()
        concurrent = _find_succeeded_run(
            db,
            erp_run_id=erp_run_id,
            groupware_run_id=groupware_run_id,
            identity_resolution_revision=identity_resolution.revision,
        )
        if concurrent is None:
            failed_run = db.get(HrMasterRun, run.id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_code = "unexpected_build_error"
                failed_run.error_summary = type(error).__name__
                failed_run.result_payload = {
                    "erp_run_id": erp_run_id,
                    "groupware_run_id": groupware_run_id,
                    "identity_resolution_revision": identity_resolution.revision,
                    "rejection_reason": "unexpected_build_error",
                }
                failed_run.completed_at = now
                db.commit()
            raise
        failed_run = db.get(HrMasterRun, run.id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_code = "superseded_by_succeeded_run"
            failed_run.error_summary = "superseded_by_succeeded_run"
            failed_run.result_payload = {
                "erp_run_id": erp_run_id,
                "groupware_run_id": groupware_run_id,
                "identity_resolution_revision": identity_resolution.revision,
                "rejection_reason": "superseded_by_succeeded_run",
                "succeeded_run_id": concurrent.id,
            }
            failed_run.completed_at = now
            db.commit()
        return concurrent
    except Exception as error:
        db.rollback()
        failed_run = db.get(HrMasterRun, run.id)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_code = "unexpected_build_error"
            failed_run.error_summary = type(error).__name__
            failed_run.result_payload = {
                "erp_run_id": erp_run_id,
                "groupware_run_id": groupware_run_id,
                "identity_resolution_revision": identity_resolution.revision,
                "rejection_reason": "unexpected_build_error",
            }
            failed_run.completed_at = now
            db.commit()
        raise


def _seoul_day_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    aware_utc = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    localized = aware_utc.astimezone(SEOUL_TIME_ZONE)
    day_start = localized.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = day_start + timedelta(days=1)
    return (
        aware_utc.replace(tzinfo=None),
        day_start.astimezone(UTC).replace(tzinfo=None),
        next_day.astimezone(UTC).replace(tzinfo=None),
    )


def _latest_succeeded_source_run_for_day(
    db: Session,
    *,
    source_system: str,
    scope_key: str,
    schema_version: str,
    day_start: datetime,
    next_day: datetime,
) -> HrSyncRun | None:
    return db.scalar(
        select(HrSyncRun)
        .where(
            HrSyncRun.source_system == source_system,
            HrSyncRun.scope_key == scope_key,
            HrSyncRun.schema_version == schema_version,
            HrSyncRun.status == "succeeded",
            HrSyncRun.captured_at >= day_start,
            HrSyncRun.captured_at < next_day,
            HrSyncRun.snapshots_purged_at.is_(None),
        )
        .order_by(HrSyncRun.captured_at.desc(), HrSyncRun.id.desc())
        .limit(1)
    )


def build_latest_hr_master_run(
    db: Session,
    *,
    now: datetime,
    idempotency_key: str | None = None,
) -> HrMasterRun | None:
    """Build from the latest same-KST-day accepted source pair, or return None."""

    built_at, day_start, next_day = _seoul_day_bounds(now)
    erp_run = _latest_succeeded_source_run_for_day(
        db,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
        day_start=day_start,
        next_day=next_day,
    )
    groupware_run = _latest_succeeded_source_run_for_day(
        db,
        source_system=GROUPWARE_SOURCE_SYSTEM,
        scope_key=GROUPWARE_SCOPE_KEY,
        schema_version=HR_SNAPSHOT_SCHEMA_VERSION,
        day_start=day_start,
        next_day=next_day,
    )
    if erp_run is None or groupware_run is None:
        return None
    return build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key=idempotency_key,
        built_at=built_at,
    )


def load_latest_succeeded_hr_master_run(db: Session) -> HrMasterRun | None:
    return db.scalar(
        select(HrMasterRun)
        .where(HrMasterRun.status == "succeeded")
        .order_by(
            HrMasterRun.identity_resolution_revision.desc(),
            HrMasterRun.completed_at.desc(),
            HrMasterRun.id.desc(),
        )
        .limit(1)
    )


def _load_latest_hr_master_erp_employee_snapshot_metadata(
    db: Session,
) -> tuple[HrMasterRun, HrMasterErpEmployeeSnapshotMetadata] | None:
    run = load_latest_succeeded_hr_master_run(db)
    if run is None:
        return None
    if run.schema_version != HR_MASTER_SCHEMA_VERSION:
        raise HrMasterErpEmployeeSnapshotError("unsupported_schema_version")
    if run.rows_purged_at is not None:
        raise HrMasterErpEmployeeSnapshotError("snapshot_rows_unavailable")
    if not run.erp_projection_hash:
        raise HrMasterErpEmployeeSnapshotError("snapshot_metadata_incomplete")
    erp_run = db.get(HrSyncRun, run.erp_run_id)
    if (
        erp_run is None
        or erp_run.source_system != ERP_SOURCE_SYSTEM
        or erp_run.scope_key != ERP_EMPLOYEE_SCOPE_KEY
        or erp_run.status != "succeeded"
        or erp_run.schema_version != ERP_EMPLOYEE_SCHEMA_VERSION
        or erp_run.captured_at is None
    ):
        raise HrMasterErpEmployeeSnapshotError("snapshot_metadata_incomplete")
    employee_count = db.scalar(
        select(func.count())
        .select_from(HrMasterPersonRow)
        .where(
            HrMasterPersonRow.master_run_id == run.id,
            HrMasterPersonRow.erp_snapshot_row_id.is_not(None),
        )
    )
    expected_employee_count = (run.result_payload or {}).get("erp_employee_count")
    if type(expected_employee_count) is not int or expected_employee_count != int(
        employee_count or 0
    ):
        raise HrMasterErpEmployeeSnapshotError("snapshot_row_count_mismatch")
    return run, HrMasterErpEmployeeSnapshotMetadata(
        run_id=run.id,
        erp_run_id=run.erp_run_id,
        captured_at=erp_run.captured_at,
        schema_version=HR_MASTER_ERP_VIEW_SCHEMA_VERSION,
        snapshot_hash=run.erp_projection_hash,
        employee_count=int(employee_count or 0),
    )


def load_latest_hr_master_erp_employee_snapshot_metadata(
    db: Session,
) -> HrMasterErpEmployeeSnapshotMetadata | None:
    """Return latest master ERP-view metadata without materializing employees."""

    resolved = _load_latest_hr_master_erp_employee_snapshot_metadata(db)
    return resolved[1] if resolved is not None else None


def load_latest_hr_master_erp_employee_snapshot(
    db: Session,
) -> HrMasterErpEmployeeSnapshot | None:
    """Read ERP-connected people from the latest succeeded immutable master."""

    resolved = _load_latest_hr_master_erp_employee_snapshot_metadata(db)
    if resolved is None:
        return None
    run, metadata = resolved
    rows = list(
        db.scalars(
            select(HrMasterPersonRow)
            .where(
                HrMasterPersonRow.master_run_id == run.id,
                HrMasterPersonRow.erp_snapshot_row_id.is_not(None),
            )
            .order_by(HrMasterPersonRow.employee_code, HrMasterPersonRow.id)
        ).all()
    )
    if len(rows) != metadata.employee_count:
        raise HrMasterErpEmployeeSnapshotError("snapshot_row_count_mismatch")

    employees: list[HrMasterErpEmployee] = []
    for row in rows:
        if (
            row.erp_snapshot_row_id is None
            or row.group_code is None
            or row.group_name is None
            or row.occupation is None
            or row.birth_date is None
            or row.hire_date is None
        ):
            raise HrMasterErpEmployeeSnapshotError("snapshot_schema_mismatch")
        employees.append(
            HrMasterErpEmployee(
                snapshot_row_id=row.erp_snapshot_row_id,
                employee_code=row.employee_code,
                name=row.name,
                department_code=row.group_code,
                department_name=row.group_name,
                position=row.position,
                occupation=row.occupation,
                birth_date=row.birth_date,
                hire_date=row.hire_date,
                phone_number=row.phone_number,
            )
        )
    if _erp_projection_hash(employees) != metadata.snapshot_hash:
        raise HrMasterErpEmployeeSnapshotError("snapshot_hash_mismatch")
    return HrMasterErpEmployeeSnapshot(
        run_id=metadata.run_id,
        erp_run_id=metadata.erp_run_id,
        captured_at=metadata.captured_at,
        schema_version=metadata.schema_version,
        snapshot_hash=metadata.snapshot_hash,
        employees=tuple(employees),
    )


def list_hr_master_runs(db: Session, *, limit: int = 50) -> list[HrMasterRun]:
    safe_limit = max(1, min(limit, 500))
    return list(
        db.scalars(
            select(HrMasterRun)
            .order_by(HrMasterRun.created_at.desc(), HrMasterRun.id.desc())
            .limit(safe_limit)
        ).all()
    )


def list_hr_master_person_rows(
    db: Session,
    *,
    master_run_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[HrMasterPersonRow]:
    resolved_run_id = master_run_id
    if resolved_run_id is None:
        latest = load_latest_succeeded_hr_master_run(db)
        if latest is None:
            return []
        resolved_run_id = latest.id
    return list(
        db.scalars(
            select(HrMasterPersonRow)
            .where(HrMasterPersonRow.master_run_id == resolved_run_id)
            .order_by(HrMasterPersonRow.employee_code, HrMasterPersonRow.id)
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
        ).all()
    )


def load_latest_hr_master_snapshot(db: Session) -> HrMasterSnapshot | None:
    run = load_latest_succeeded_hr_master_run(db)
    if run is None:
        return None
    people = tuple(
        db.scalars(
            select(HrMasterPersonRow)
            .where(HrMasterPersonRow.master_run_id == run.id)
            .order_by(HrMasterPersonRow.employee_code, HrMasterPersonRow.id)
        ).all()
    )
    external_people = tuple(
        db.scalars(
            select(HrMasterExternalPersonRow)
            .where(HrMasterExternalPersonRow.master_run_id == run.id)
            .order_by(
                HrMasterExternalPersonRow.employee_code,
                HrMasterExternalPersonRow.name,
                HrMasterExternalPersonRow.groupware_source_identity,
            )
        ).all()
    )
    groups = tuple(
        db.scalars(
            select(HrMasterGroupRow)
            .where(HrMasterGroupRow.master_run_id == run.id)
            .order_by(
                HrMasterGroupRow.source_system,
                HrMasterGroupRow.source_code,
                HrMasterGroupRow.id,
            )
        ).all()
    )
    conflicts = tuple(
        db.scalars(
            select(HrMasterConflictRow)
            .where(HrMasterConflictRow.master_run_id == run.id)
            .order_by(
                HrMasterConflictRow.normalized_employee_code,
                HrMasterConflictRow.reason_code,
                HrMasterConflictRow.id,
            )
        ).all()
    )
    return HrMasterSnapshot(
        run=run,
        people=people,
        external_people=external_people,
        groups=groups,
        conflicts=conflicts,
    )


def prune_hr_master_history(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int = HR_SNAPSHOT_RETENTION_DAYS,
) -> dict[str, int]:
    """Purge expired immutable rows while retaining aggregate run metadata."""

    purged_at = now or utcnow_naive()
    cutoff = purged_at - timedelta(days=max(retention_days, 1))
    latest = load_latest_succeeded_hr_master_run(db)
    eligible_run_ids = list(
        db.scalars(
            select(HrMasterRun.id).where(
                HrMasterRun.completed_at < cutoff,
                HrMasterRun.rows_purged_at.is_(None),
                *((HrMasterRun.id != latest.id,) if latest is not None else ()),
            )
        ).all()
    )
    if not eligible_run_ids:
        return {
            "runs_deleted": 0,
            "people_deleted": 0,
            "external_people_deleted": 0,
            "groups_deleted": 0,
            "conflicts_deleted": 0,
        }

    people_result = db.execute(
        delete(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id.in_(eligible_run_ids))
    )
    external_people_result = db.execute(
        delete(HrMasterExternalPersonRow).where(
            HrMasterExternalPersonRow.master_run_id.in_(eligible_run_ids)
        )
    )
    groups_result = db.execute(
        delete(HrMasterGroupRow).where(HrMasterGroupRow.master_run_id.in_(eligible_run_ids))
    )
    conflicts_result = db.execute(
        delete(HrMasterConflictRow).where(HrMasterConflictRow.master_run_id.in_(eligible_run_ids))
    )
    for run in db.scalars(select(HrMasterRun).where(HrMasterRun.id.in_(eligible_run_ids))).all():
        run.rows_purged_at = purged_at
    db.commit()
    return {
        "runs_deleted": 0,
        "people_deleted": max(people_result.rowcount or 0, 0),
        "external_people_deleted": max(external_people_result.rowcount or 0, 0),
        "groups_deleted": max(groups_result.rowcount or 0, 0),
        "conflicts_deleted": max(conflicts_result.rowcount or 0, 0),
    }


__all__ = [
    "HR_MASTER_CANONICALIZATION_VERSION",
    "HR_MASTER_ERP_VIEW_SCHEMA_VERSION",
    "HR_MASTER_SCHEMA_VERSION",
    "HrMasterBuildError",
    "HrMasterErpEmployee",
    "HrMasterErpEmployeeSnapshot",
    "HrMasterErpEmployeeSnapshotError",
    "HrMasterErpEmployeeSnapshotMetadata",
    "HrMasterSnapshot",
    "build_hr_master_run",
    "build_latest_hr_master_run",
    "list_hr_master_person_rows",
    "list_hr_master_runs",
    "load_latest_hr_master_snapshot",
    "load_latest_hr_master_erp_employee_snapshot",
    "load_latest_hr_master_erp_employee_snapshot_metadata",
    "load_latest_succeeded_hr_master_run",
    "normalize_employee_code",
    "prune_hr_master_history",
]
