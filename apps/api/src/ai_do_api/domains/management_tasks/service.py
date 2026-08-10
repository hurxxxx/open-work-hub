from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import OrgUnit, User
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.hr.master import (
    HR_MASTER_ERP_VIEW_SCHEMA_VERSION,
    HrMasterErpEmployee,
    HrMasterErpEmployeeSnapshot,
    HrMasterErpEmployeeSnapshotError,
    HrMasterErpEmployeeSnapshotMetadata,
    load_latest_hr_master_erp_employee_snapshot,
    load_latest_hr_master_erp_employee_snapshot_metadata,
)
from ai_do_api.domains.hr.groupware_sync import (
    ACTIVE_COM_STATE,
    AUTH_PROVIDER_GROUPWARE,
    GROUPWARE_SOURCE_SYSTEM,
)

from .models import (
    ManagementHealthCheckupSettings,
    ManagementHealthCheckupSettingsHistory,
    ManagementHealthDecisionRow,
    ManagementHealthDecisionRun,
    ManagementHealthPriorRow,
    ManagementHealthPriorUpload,
)
from .rules import DeterminationSettings, determine
from .schemas import (
    EmployeeDetermination,
    HealthCheckupDeterminationListResponse,
    HealthCheckupPriorExamStatus,
    HealthCheckupPriorExamUploadResponse,
    HealthCheckupSettingsHistoryResponse,
    HealthCheckupSettingsResponse,
    HealthCheckupSettingsUpdateRequest,
    HealthCheckupSourceStatusResponse,
    PriorExamMatchedItem,
    PriorExamUnmatchedItem,
    SettingsHistoryItem,
)
from .xlsx import (
    MAX_DETAIL_ROWS,
    ParsedPriorExamRow,
    build_employee_table_xlsx,
    build_target_roster_xlsx,
    parse_prior_exam_workbook_isolated,
)


SETTINGS_ID = "company"
RULES_VERSION = "health-checkup-rules-v1"
PUBLISH_BLOCKER_MISSING_PRIOR_UPLOAD = "missing_prior_exam_upload"
PUBLISH_BLOCKER_UNRESOLVED_PRIOR_ROWS = "unresolved_prior_exam_rows"
PUBLISH_BLOCKER_STALE_INPUTS = "stale_inputs"
MAX_SOURCE_EMPLOYEES = 5_000
MAX_DETERMINATION_RESPONSE_ROWS = 5_000
MAX_EXPORT_ROWS = 5_000
MAX_EXPORT_BYTES = 8 * 1024 * 1024


class SourceUnavailableError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class DecisionRunNotFoundError(RuntimeError):
    pass


class DecisionRunStaleError(RuntimeError):
    pass


class DecisionNotPublishableError(RuntimeError):
    def __init__(self, blockers: list[str]):
        super().__init__("decision is not publishable")
        self.blockers = blockers


class FeatureNotAvailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeterminationExport:
    content: bytes
    run_id: str
    exported_count: int


@dataclass(frozen=True)
class DeterminationInputs:
    snapshot: HrMasterErpEmployeeSnapshotMetadata
    settings_payload: dict[str, object]
    settings_hash: str
    prior_upload: ManagementHealthPriorUpload | None
    input_hash: str


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.isoformat(),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    normalized = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return normalized[:255] or None


def _enforce_row_limit(count: int, *, limit: int, reason: str) -> None:
    if count > limit:
        raise SourceUnavailableError(reason)


def _required_snapshot(db: Session) -> HrMasterErpEmployeeSnapshot:
    metadata = _required_snapshot_metadata(db)
    try:
        snapshot = load_latest_hr_master_erp_employee_snapshot(db)
    except HrMasterErpEmployeeSnapshotError as error:
        raise SourceUnavailableError(error.code) from error
    if snapshot is None:
        raise SourceUnavailableError("integrated_hr_erp_snapshot_not_found")
    if snapshot.schema_version != HR_MASTER_ERP_VIEW_SCHEMA_VERSION:
        raise SourceUnavailableError("unsupported_schema_version")
    _enforce_row_limit(
        len(snapshot.employees),
        limit=MAX_SOURCE_EMPLOYEES,
        reason="source_employee_limit_exceeded",
    )
    if (
        snapshot.run_id != metadata.run_id
        or snapshot.erp_run_id != metadata.erp_run_id
        or snapshot.schema_version != metadata.schema_version
        or snapshot.snapshot_hash != metadata.snapshot_hash
        or len(snapshot.employees) != metadata.employee_count
    ):
        raise SourceUnavailableError("snapshot_changed_during_read")
    return snapshot


def _required_snapshot_metadata(db: Session) -> HrMasterErpEmployeeSnapshotMetadata:
    try:
        snapshot = load_latest_hr_master_erp_employee_snapshot_metadata(db)
    except HrMasterErpEmployeeSnapshotError as error:
        raise SourceUnavailableError(error.code) from error
    if snapshot is None:
        raise SourceUnavailableError("integrated_hr_erp_snapshot_not_found")
    if snapshot.schema_version != HR_MASTER_ERP_VIEW_SCHEMA_VERSION:
        raise SourceUnavailableError("unsupported_schema_version")
    _enforce_row_limit(
        snapshot.employee_count,
        limit=MAX_SOURCE_EMPLOYEES,
        reason="source_employee_limit_exceeded",
    )
    return snapshot


def get_source_status(db: Session) -> HealthCheckupSourceStatusResponse:
    try:
        snapshot = _required_snapshot_metadata(db)
    except SourceUnavailableError as error:
        return HealthCheckupSourceStatusResponse(
            available=False,
            reason=error.reason,
        )
    return HealthCheckupSourceStatusResponse(
        available=True,
        run_id=snapshot.run_id,
        erp_run_id=snapshot.erp_run_id,
        captured_at=snapshot.captured_at,
        employee_count=snapshot.employee_count,
        schema_version=snapshot.schema_version,
    )


def _settings_or_default(db: Session) -> ManagementHealthCheckupSettings:
    row = db.get(ManagementHealthCheckupSettings, SETTINGS_ID)
    if row is not None:
        return row
    return ManagementHealthCheckupSettings(
        id=SETTINGS_ID,
        age_calc_method="korean",
        senior_age=57,
        adult_age=40,
        service_years_threshold=10,
        updated_by_user_id=None,
        updated_at=None,
    )


def _settings_out(
    row: ManagementHealthCheckupSettings,
) -> HealthCheckupSettingsResponse:
    return HealthCheckupSettingsResponse(
        age_calc_method=row.age_calc_method,
        senior_age=row.senior_age,
        adult_age=row.adult_age,
        service_years_threshold=row.service_years_threshold,
        updated_by=row.updated_by_user_id,
        updated_at=row.updated_at,
    )


def get_settings(db: Session) -> HealthCheckupSettingsResponse:
    return _settings_out(_settings_or_default(db))


def _locked_settings(db: Session) -> ManagementHealthCheckupSettings:
    db.execute(
        text(
            """
            INSERT INTO management_health_checkup_settings (
                id,
                age_calc_method,
                senior_age,
                adult_age,
                service_years_threshold,
                updated_by_user_id,
                updated_at
            ) VALUES (
                :id,
                :age_calc_method,
                :senior_age,
                :adult_age,
                :service_years_threshold,
                NULL,
                :updated_at
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": SETTINGS_ID,
            "age_calc_method": "korean",
            "senior_age": 57,
            "adult_age": 40,
            "service_years_threshold": 10,
            "updated_at": _now_naive(),
        },
    )
    row = db.scalar(
        select(ManagementHealthCheckupSettings)
        .where(ManagementHealthCheckupSettings.id == SETTINGS_ID)
        .with_for_update()
    )
    if row is None:  # pragma: no cover - insert/select is an internal invariant
        raise RuntimeError("health-checkup settings row was not created")
    return row


def update_settings(
    db: Session,
    *,
    payload: HealthCheckupSettingsUpdateRequest,
    actor_user_id: str,
) -> HealthCheckupSettingsResponse:
    row = _locked_settings(db)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    next_senior = int(changes.get("senior_age", row.senior_age))
    next_adult = int(changes.get("adult_age", row.adult_age))
    if next_senior < next_adult:
        raise ValueError("senior_age must be greater than or equal to adult_age")

    actual_changes = {
        field_key: new_value
        for field_key, new_value in changes.items()
        if getattr(row, field_key) != new_value
    }
    if not actual_changes:
        return _settings_out(row)

    db.add(row)
    changed_at = _now_naive()
    for field_key, new_value in actual_changes.items():
        old_value = getattr(row, field_key)
        db.add(
            ManagementHealthCheckupSettingsHistory(
                id=new_id(),
                field_key=field_key,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                changed_by_user_id=actor_user_id,
                created_at=changed_at,
            )
        )
        setattr(row, field_key, new_value)
    row.updated_by_user_id = actor_user_id
    row.updated_at = changed_at
    db.flush()
    db.refresh(row)
    return _settings_out(row)


def list_settings_history(db: Session, *, limit: int = 200) -> HealthCheckupSettingsHistoryResponse:
    rows = list(
        db.scalars(
            select(ManagementHealthCheckupSettingsHistory)
            .order_by(
                ManagementHealthCheckupSettingsHistory.created_at.desc(),
                ManagementHealthCheckupSettingsHistory.id.desc(),
            )
            .limit(limit)
        ).all()
    )
    user_ids = {row.changed_by_user_id for row in rows if row.changed_by_user_id}
    users = (
        {
            user.id: user.display_name or user.full_name or None
            for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
        }
        if user_ids
        else {}
    )
    return HealthCheckupSettingsHistoryResponse(
        items=[
            SettingsHistoryItem(
                id=row.id,
                field_key=row.field_key,
                old_value=row.old_value,
                new_value=row.new_value,
                changed_by=row.changed_by_user_id,
                changed_by_name=users.get(row.changed_by_user_id),
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


def _latest_prior_upload(db: Session, *, exam_year: int) -> ManagementHealthPriorUpload | None:
    return db.scalar(
        select(ManagementHealthPriorUpload)
        .where(
            ManagementHealthPriorUpload.exam_year == exam_year,
            ManagementHealthPriorUpload.status == "accepted",
        )
        .order_by(
            ManagementHealthPriorUpload.uploaded_at.desc(),
            ManagementHealthPriorUpload.id.desc(),
        )
        .limit(1)
    )


def _normalized_identity(value: str) -> str:
    return " ".join(value.split()).casefold()


def _match_key(name: str) -> str:
    """Normalize a person name for matching.

    Rosters distinguish same-named employees by appending a single latin letter
    (e.g. "정성문A" / "정성문B"). Strip that disambiguation suffix so both sides
    key on the real name; the homonym is then resolved by department below.
    """

    normalized = _normalized_identity(name)
    if len(normalized) >= 2 and normalized[-1].isascii() and normalized[-1].isalpha():
        head = normalized[:-1].strip()
        if head and any(not character.isascii() for character in head):
            return head
    return normalized


def _homonym_suffix(name: str) -> str | None:
    normalized = _normalized_identity(name)
    if len(normalized) < 2 or not normalized[-1].isascii() or not normalized[-1].isalpha():
        return None
    head = normalized[:-1].strip()
    if not head or not any(not character.isascii() for character in head):
        return None
    return normalized[-1]


@dataclass(frozen=True)
class _EmployeeNameIndex:
    # Exact key preserves any A/B suffix; ERP uses it to distinguish homonyms
    # (정호철A / 정호철B), so an exact hit is the most precise match.
    exact: dict[str, list[HrMasterErpEmployee]]
    # Base key drops the suffix; used only when the file's suffixed name has no
    # exact counterpart (file 정성문A ↔ ERP plain 정성문).
    base: dict[str, list[HrMasterErpEmployee]]


def _index_employees(
    employees: tuple[HrMasterErpEmployee, ...],
) -> _EmployeeNameIndex:
    exact: dict[str, list[HrMasterErpEmployee]] = {}
    base: dict[str, list[HrMasterErpEmployee]] = {}
    for employee in employees:
        exact.setdefault(_normalized_identity(employee.name), []).append(employee)
        base.setdefault(_match_key(employee.name), []).append(employee)
    return _EmployeeNameIndex(exact=exact, base=base)


def _department_matches(file_dept: str, candidate_dept: str | None) -> bool:
    left = _normalized_identity(file_dept)
    right = _normalized_identity(candidate_dept or "")
    if not left or not right:
        return False
    if left == right:
        return True
    # The file records a parent department ("기술연구소") while ERP/groupware store
    # the sub-team ("기술연구소 시작평가팀"). Only a whitespace-delimited hierarchy
    # counts as containment; arbitrary substrings such as 영업팀/해외영업팀 do not.
    # fuzzy edit similarity makes meaningful siblings such as 생산1팀/생산2팀
    # look deceptively close and is unsafe for employee identity.
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 2 and longer.startswith(f"{shorter} ")


def _resolve_homonym(
    file_dept: str,
    candidates: list[HrMasterErpEmployee],
    groupware_departments: dict[str, list[str]],
) -> HrMasterErpEmployee | None:
    """Return the sole candidate with an exact or explicit parent/child match."""

    matches = [
        candidate
        for candidate in candidates
        if any(
            _department_matches(file_dept, source)
            for source in [
                candidate.department_name,
                *groupware_departments.get(candidate.employee_code, ()),
            ]
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _groupware_department_chains(db: Session, employee_codes: set[str]) -> dict[str, list[str]]:
    """Map each employee code to its groupware org-unit name chain (self→parents).

    Only consulted to break homonym ties, so callers pass just the codes that
    share a name; an empty input avoids touching the auth tables entirely.
    """

    codes = {code for code in employee_codes if code}
    if not codes:
        return {}
    org_units = {
        unit_id: (name, parent_id)
        for unit_id, name, parent_id in db.execute(
            select(OrgUnit.id, OrgUnit.name, OrgUnit.parent_id).where(OrgUnit.active.is_(True))
        ).all()
    }

    def chain(org_unit_id: str | None) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        while org_unit_id and org_unit_id in org_units and org_unit_id not in seen:
            seen.add(org_unit_id)
            name, parent_id = org_units[org_unit_id]
            names.append(name)
            org_unit_id = parent_id
        return names

    rows_by_code: dict[str, list[str]] = {}
    for employee_code, org_unit_id in db.execute(
        select(User.employee_code, User.primary_org_unit_id).where(
            User.hr_source_system == GROUPWARE_SOURCE_SYSTEM,
            User.auth_provider == AUTH_PROVIDER_GROUPWARE,
            User.status == "active",
            User.hr_com_state == ACTIVE_COM_STATE,
            User.employee_code.in_(codes),
            User.primary_org_unit_id.is_not(None),
        )
    ).all():
        cleaned = (employee_code or "").strip()
        if cleaned and org_unit_id:
            rows_by_code.setdefault(cleaned, []).append(org_unit_id)
    # Employee code is not a unique database key. If more than one active
    # groupware identity claims it, omit that signal instead of choosing an
    # arbitrary row for a PII-sensitive identity decision.
    chains: dict[str, list[str]] = {}
    for employee_code, org_unit_ids in rows_by_code.items():
        if len(org_unit_ids) != 1:
            continue
        names = chain(org_unit_ids[0])
        if names:
            chains[employee_code] = names
    return chains


def _match_by_name(
    parsed: ParsedPriorExamRow,
    name_index: _EmployeeNameIndex,
    groupware_departments: dict[str, list[str]],
) -> tuple[HrMasterErpEmployee | None, list[HrMasterErpEmployee], str]:
    base_key = _match_key(parsed.person_name)
    base_group = name_index.base.get(base_key, [])
    if not base_group:
        # Not on the current ERP roster: retired/left, or a typo. Left unmatched
        # and excluded — it never blocks publishing.
        return None, [], "unmatched"
    exact_key = _normalized_identity(parsed.person_name)
    exact_group = name_index.exact.get(exact_key, [])
    candidate_suffixes = {
        suffix
        for candidate in base_group
        if (suffix := _homonym_suffix(candidate.name)) is not None
    }
    if candidate_suffixes and not exact_group:
        # When both sides carry an explicit ERP A/B disambiguation suffix, only
        # an exact suffixed name is safe. Never strip a missing or mismatching
        # file suffix and then accept a unique base-name candidate.
        return None, base_group, "ambiguous"
    if len(base_group) == 1:
        # The name is unique across the roster, so it identifies one person.
        return base_group[0], base_group, "matched"
    # Homonyms share this base name. Only an exact hit on a *distinct* (suffixed)
    # name — where the file itself carries the disambiguating suffix, e.g. 정호철B —
    # is precise enough to confirm directly. A bare name (정호철) that also collides
    # with a suffixed homonym (정호철A) must NOT be confirmed on the exact hit alone;
    # it is disambiguated by department, and stays ambiguous when that is unclear,
    # so we never silently defer the wrong same-name employee.
    if len(exact_group) == 1 and exact_key != base_key:
        return exact_group[0], exact_group, "matched"
    matched = _resolve_homonym(parsed.dept_name, base_group, groupware_departments)
    return matched, base_group, "matched" if matched is not None else "ambiguous"


def _matched_prior_row(
    *,
    upload_id: str,
    parsed: ParsedPriorExamRow,
    employees_by_code: dict[str, HrMasterErpEmployee],
    name_index: _EmployeeNameIndex,
    groupware_departments: dict[str, list[str]],
) -> ManagementHealthPriorRow:
    relation_kind = "dependent" if parsed.is_dependent else "self"
    match_status = "spouse_excluded" if parsed.is_dependent else "unmatched"
    matched: HrMasterErpEmployee | None = None
    candidates: list[HrMasterErpEmployee] = []
    if not parsed.is_dependent:
        if parsed.provided_employee_code:
            # Primary key: an explicit employee code always wins when present.
            matched = employees_by_code.get(parsed.provided_employee_code.strip())
            match_status = "matched" if matched is not None else "unmatched"
        else:
            matched, candidates, match_status = _match_by_name(
                parsed, name_index, groupware_departments
            )
    row_payload = {
        "sheet_name": parsed.sheet_name,
        "row_ordinal": parsed.row_ordinal,
        "dept_name": parsed.dept_name,
        "person_name": parsed.person_name,
        "raw_relation": parsed.raw_relation,
        "provided_employee_code": parsed.provided_employee_code,
    }
    return ManagementHealthPriorRow(
        id=new_id(),
        upload_id=upload_id,
        row_ordinal=parsed.row_ordinal,
        sheet_name=parsed.sheet_name,
        file_dept_name=parsed.dept_name,
        person_name=parsed.person_name,
        raw_relation=parsed.raw_relation,
        relation_kind=relation_kind,
        provided_employee_code=parsed.provided_employee_code,
        match_status=match_status,
        matched_snapshot_row_id=matched.snapshot_row_id if matched else None,
        matched_employee_code=matched.employee_code if matched else None,
        matched_employee_name=matched.name if matched else None,
        matched_department_name=matched.department_name if matched else None,
        candidate_employee_codes=(
            [employee.employee_code for employee in candidates]
            if match_status == "ambiguous"
            else []
        ),
        row_hash=_canonical_hash(row_payload),
    )


def _prior_upload_out(
    db: Session, upload: ManagementHealthPriorUpload, *, target_year: int
) -> HealthCheckupPriorExamUploadResponse:
    rows = list(
        db.scalars(
            select(ManagementHealthPriorRow)
            .where(ManagementHealthPriorRow.upload_id == upload.id)
            .order_by(ManagementHealthPriorRow.row_ordinal)
        ).all()
    )
    detail_candidates = [
        *[row for row in rows if row.match_status == "ambiguous"],
        *[row for row in rows if row.match_status == "unmatched"],
        *[row for row in rows if row.match_status == "matched"],
    ]
    detail_rows = detail_candidates[:MAX_DETAIL_ROWS]
    unmatched = [
        PriorExamUnmatchedItem(
            sheet_name=row.sheet_name,
            dept_name=row.file_dept_name,
            person_name=row.person_name,
            raw_relation=row.raw_relation,
            match_status=row.match_status,
        )
        for row in detail_rows
        if row.match_status in {"unmatched", "ambiguous"}
    ]
    matched = [
        PriorExamMatchedItem(
            sheet_name=row.sheet_name,
            employee_code=row.matched_employee_code or "",
            person_name=row.person_name,
            employee_name=row.matched_employee_name or "",
            erp_dept_name=row.matched_department_name or "",
            file_dept_name=row.file_dept_name,
        )
        for row in detail_rows
        if row.match_status == "matched"
    ]
    ambiguous_count = sum(row.match_status == "ambiguous" for row in rows)
    return HealthCheckupPriorExamUploadResponse(
        upload_id=upload.id,
        target_year=target_year,
        exam_year=upload.exam_year,
        source_filename=upload.source_filename,
        total_rows=upload.total_row_count,
        matched_count=upload.matched_count,
        spouse_excluded_count=upload.dependent_excluded_count,
        unmatched_count=sum(row.match_status == "unmatched" for row in rows),
        ambiguous_count=ambiguous_count,
        publish_blockers=([PUBLISH_BLOCKER_UNRESOLVED_PRIOR_ROWS] if ambiguous_count else []),
        details_truncated=len(detail_candidates) > MAX_DETAIL_ROWS,
        unmatched=unmatched,
        matched=matched,
    )


def upload_prior_exam(
    db: Session,
    *,
    target_year: int,
    filename: str | None,
    content: bytes,
    actor_user_id: str,
) -> HealthCheckupPriorExamUploadResponse:
    parsed_rows = parse_prior_exam_workbook_isolated(content)
    snapshot = _required_snapshot(db)
    exam_year = target_year - 1
    content_hash = hashlib.sha256(content).hexdigest()
    upload_id = new_id()
    employees_by_code = {employee.employee_code: employee for employee in snapshot.employees}
    name_index = _index_employees(snapshot.employees)
    # Groupware departments only break homonym ties, so resolve just the codes
    # that share a name — non-homonym uploads never query the auth tables.
    homonym_codes = {
        employee.employee_code
        for index in (name_index.exact, name_index.base)
        for group in index.values()
        if len(group) > 1
        for employee in group
    }
    groupware_departments = _groupware_department_chains(db, homonym_codes)
    rows = [
        _matched_prior_row(
            upload_id=upload_id,
            parsed=parsed,
            employees_by_code=employees_by_code,
            name_index=name_index,
            groupware_departments=groupware_departments,
        )
        for parsed in parsed_rows
    ]
    matched_count = len(
        {
            row.matched_employee_code
            for row in rows
            if row.match_status == "matched" and row.matched_employee_code
        }
    )
    dependent_count = sum(row.match_status == "spouse_excluded" for row in rows)
    # Only genuinely undecided rows (homonyms we could not disambiguate) block
    # publishing. Unmatched rows are people absent from the current ERP roster
    # (retired/left) and are legitimately excluded, so they never block.
    unresolved_count = sum(row.match_status == "ambiguous" for row in rows)
    upload = ManagementHealthPriorUpload(
        id=upload_id,
        exam_year=exam_year,
        source_filename=_safe_filename(filename),
        content_sha256=content_hash,
        content_size=len(content),
        status="accepted",
        source_run_id=snapshot.run_id,
        source_erp_run_id=snapshot.erp_run_id,
        source_schema_version=snapshot.schema_version,
        source_snapshot_hash=snapshot.snapshot_hash,
        source_captured_at=snapshot.captured_at,
        total_row_count=len(rows),
        matched_count=matched_count,
        dependent_excluded_count=dependent_count,
        unresolved_count=unresolved_count,
        uploaded_by_user_id=actor_user_id,
    )
    db.add(upload)
    # These models intentionally do not expose ORM relationships. Flush the
    # parent explicitly so PostgreSQL's immediate FK check cannot observe rows
    # before their upload record.
    db.flush()
    db.add_all(rows)
    db.flush()
    return _prior_upload_out(db, upload, target_year=target_year)


def _has_ambiguous_prior_rows(db: Session, *, upload_id: str) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(ManagementHealthPriorRow)
            .where(
                ManagementHealthPriorRow.upload_id == upload_id,
                ManagementHealthPriorRow.match_status == "ambiguous",
            )
        )
        or 0
    ) > 0


def get_prior_exam_status(db: Session, *, target_year: int) -> HealthCheckupPriorExamStatus:
    exam_year = target_year - 1
    upload = _latest_prior_upload(db, exam_year=exam_year)
    if upload is None:
        return HealthCheckupPriorExamStatus(
            exam_year=exam_year,
            uploaded=False,
            source_filename=None,
            matched_count=0,
            uploaded_at=None,
            publish_blockers=[PUBLISH_BLOCKER_MISSING_PRIOR_UPLOAD],
        )
    return HealthCheckupPriorExamStatus(
        exam_year=exam_year,
        uploaded=True,
        source_filename=upload.source_filename,
        matched_count=upload.matched_count,
        uploaded_at=upload.uploaded_at,
        publish_blockers=(
            [PUBLISH_BLOCKER_UNRESOLVED_PRIOR_ROWS]
            if _has_ambiguous_prior_rows(db, upload_id=upload.id)
            else []
        ),
    )


def _settings_snapshot(row: ManagementHealthCheckupSettings) -> dict[str, object]:
    return {
        "age_calc_method": row.age_calc_method,
        "senior_age": row.senior_age,
        "adult_age": row.adult_age,
        "service_years_threshold": row.service_years_threshold,
    }


def _determination_inputs(
    db: Session,
    *,
    target_year: int,
    snapshot: HrMasterErpEmployeeSnapshotMetadata | None = None,
) -> DeterminationInputs:
    snapshot = snapshot or _required_snapshot_metadata(db)
    settings_row = _settings_or_default(db)
    settings_payload = _settings_snapshot(settings_row)
    settings_hash = _canonical_hash(settings_payload)
    prior_upload = _latest_prior_upload(db, exam_year=target_year - 1)
    input_hash = _canonical_hash(
        {
            "rules_version": RULES_VERSION,
            "target_year": target_year,
            "source_schema_version": snapshot.schema_version,
            "source_snapshot_hash": snapshot.snapshot_hash,
            "prior_upload_id": prior_upload.id if prior_upload else None,
            "prior_upload_hash": prior_upload.content_sha256 if prior_upload else None,
            "settings_hash": settings_hash,
        }
    )
    return DeterminationInputs(
        snapshot=snapshot,
        settings_payload=settings_payload,
        settings_hash=settings_hash,
        prior_upload=prior_upload,
        input_hash=input_hash,
    )


def refresh_determinations(
    db: Session,
    *,
    target_year: int,
    actor_user_id: str,
) -> HealthCheckupDeterminationListResponse:
    snapshot = _required_snapshot(db)
    inputs = _determination_inputs(
        db,
        target_year=target_year,
        snapshot=HrMasterErpEmployeeSnapshotMetadata(
            run_id=snapshot.run_id,
            erp_run_id=snapshot.erp_run_id,
            schema_version=snapshot.schema_version,
            captured_at=snapshot.captured_at,
            snapshot_hash=snapshot.snapshot_hash,
            employee_count=len(snapshot.employees),
        ),
    )
    settings_payload = inputs.settings_payload
    determination_settings = DeterminationSettings(**settings_payload)
    prior_upload = inputs.prior_upload
    blockers: list[str] = []
    examined_codes: set[str] = set()
    if prior_upload is None:
        blockers.append(PUBLISH_BLOCKER_MISSING_PRIOR_UPLOAD)
    else:
        if _has_ambiguous_prior_rows(db, upload_id=prior_upload.id):
            blockers.append(PUBLISH_BLOCKER_UNRESOLVED_PRIOR_ROWS)
        examined_codes = {
            code
            for code in db.scalars(
                select(ManagementHealthPriorRow.matched_employee_code).where(
                    ManagementHealthPriorRow.upload_id == prior_upload.id,
                    ManagementHealthPriorRow.match_status == "matched",
                    ManagementHealthPriorRow.matched_employee_code.is_not(None),
                )
            ).all()
            if code
        }

    run_id = new_id()
    decision_rows: list[ManagementHealthDecisionRow] = []
    target_count = 0
    for employee in snapshot.employees:
        result = determine(
            birth_date=employee.birth_date,
            hire_date=employee.hire_date,
            occupation=employee.occupation,
            prior_year_examined=employee.employee_code in examined_codes,
            settings=determination_settings,
            target_year=target_year,
        )
        target_count += int(result.is_target)
        decision_rows.append(
            ManagementHealthDecisionRow(
                id=new_id(),
                decision_run_id=run_id,
                source_snapshot_row_id=employee.snapshot_row_id,
                employee_code=employee.employee_code,
                employee_name=employee.name,
                department_code=employee.department_code,
                department_name=employee.department_name,
                position=employee.position,
                occupation=employee.occupation,
                birth_date=employee.birth_date,
                hire_date=employee.hire_date,
                age=result.age,
                service_years=result.service_years,
                is_senior=result.is_senior,
                is_adult=result.is_adult,
                is_long_service=result.is_long_service,
                prior_year_examined=result.prior_year_examined,
                is_target=result.is_target,
                reason=result.reason,
            )
        )
    run = ManagementHealthDecisionRun(
        id=run_id,
        input_hash=inputs.input_hash,
        target_year=target_year,
        prior_exam_year=target_year - 1,
        status="preview" if blockers else "ready",
        publishable=not blockers,
        publish_blockers=blockers,
        source_run_id=snapshot.run_id,
        source_erp_run_id=snapshot.erp_run_id,
        source_schema_version=snapshot.schema_version,
        source_snapshot_hash=snapshot.snapshot_hash,
        source_captured_at=snapshot.captured_at,
        source_employee_count=len(snapshot.employees),
        prior_upload_id=prior_upload.id if prior_upload else None,
        settings_snapshot=settings_payload,
        settings_hash=inputs.settings_hash,
        total_count=len(decision_rows),
        target_count=target_count,
        created_by_user_id=actor_user_id,
    )
    db.add(run)
    # See upload_prior_exam: without an ORM relationship SQLAlchemy may batch
    # child rows before the run on PostgreSQL even though the table FK exists.
    db.flush()
    db.add_all(decision_rows)
    db.flush()
    return _decision_out(db, run)


def _latest_decision_run(db: Session, *, target_year: int) -> ManagementHealthDecisionRun | None:
    return db.scalar(
        select(ManagementHealthDecisionRun)
        .where(ManagementHealthDecisionRun.target_year == target_year)
        .order_by(
            ManagementHealthDecisionRun.created_at.desc(),
            ManagementHealthDecisionRun.id.desc(),
        )
        .limit(1)
    )


def _decision_rows(
    db: Session,
    run_id: str,
    *,
    max_rows: int,
    targets_only: bool = False,
) -> list[ManagementHealthDecisionRow]:
    filters = [ManagementHealthDecisionRow.decision_run_id == run_id]
    if targets_only:
        filters.append(ManagementHealthDecisionRow.is_target.is_(True))
    row_count = db.scalar(
        select(func.count()).select_from(ManagementHealthDecisionRow).where(*filters)
    )
    _enforce_row_limit(
        row_count or 0,
        limit=max_rows,
        reason="determination_row_limit_exceeded",
    )
    return list(
        db.scalars(
            select(ManagementHealthDecisionRow)
            .where(*filters)
            .order_by(
                ManagementHealthDecisionRow.department_name,
                ManagementHealthDecisionRow.employee_name,
                ManagementHealthDecisionRow.employee_code,
            )
        ).all()
    )


def _decision_out(
    db: Session, run: ManagementHealthDecisionRun
) -> HealthCheckupDeterminationListResponse:
    rows = _decision_rows(
        db,
        run.id,
        max_rows=MAX_DETERMINATION_RESPONSE_ROWS,
    )
    return HealthCheckupDeterminationListResponse(
        run_id=run.id,
        status=run.status,
        target_year=run.target_year,
        prior_year=run.prior_exam_year,
        publishable=run.publishable,
        publish_blockers=list(run.publish_blockers),
        source=HealthCheckupSourceStatusResponse(
            available=True,
            run_id=run.source_run_id,
            erp_run_id=run.source_erp_run_id,
            captured_at=run.source_captured_at,
            employee_count=run.source_employee_count,
            schema_version=run.source_schema_version,
        ),
        prior_exam_uploaded=run.prior_upload_id is not None,
        total=run.total_count,
        target_count=run.target_count,
        items=[
            EmployeeDetermination(
                employee_id=row.source_snapshot_row_id,
                employee_code=row.employee_code,
                name=row.employee_name,
                dept_name=row.department_name,
                position=row.position,
                hire_date=row.hire_date,
                birth_date=row.birth_date,
                age=row.age,
                service_years=row.service_years,
                is_senior=row.is_senior,
                is_adult=row.is_adult,
                is_long_service=row.is_long_service,
                prior_year_examined=row.prior_year_examined,
                is_target=row.is_target,
                reason=row.reason,
            )
            for row in rows
        ],
    )


def list_determinations(db: Session, *, target_year: int) -> HealthCheckupDeterminationListResponse:
    run = _latest_decision_run(db, target_year=target_year)
    if run is None:
        raise DecisionRunNotFoundError(target_year)
    if run.input_hash != _determination_inputs(db, target_year=target_year).input_hash:
        raise DecisionRunStaleError(target_year)
    return _decision_out(db, run)


_MARK_TRUE = "O"
_MARK_FALSE = "-"


def _mark(value: bool) -> str:
    return _MARK_TRUE if value else _MARK_FALSE


def _reason_label(reason: str, settings: dict[str, object]) -> str:
    """Human-readable Korean determination reason using the run's thresholds."""

    senior = settings.get("senior_age")
    adult = settings.get("adult_age")
    service = settings.get("service_years_threshold")
    labels = {
        "senior": f"{senior}세 이상",
        "adult_or_service": f"{adult}세 이상 또는 근속 {service}년 이상",
        "deferred": "전년도 수검 (2년 주기 유예)",
        "dispatch": "파견직 제외",
        "not_eligible": "대상 아님",
    }
    return labels.get(reason, reason)


def export_determinations(
    db: Session,
    *,
    target_year: int,
    export_kind: Literal["employees", "targets", "roster"],
) -> DeterminationExport:
    run = _latest_decision_run(db, target_year=target_year)
    if run is None:
        raise DecisionRunNotFoundError(target_year)
    if run.input_hash != _determination_inputs(db, target_year=target_year).input_hash:
        raise DecisionNotPublishableError([PUBLISH_BLOCKER_STALE_INPUTS])
    if export_kind in {"targets", "roster"} and not run.publishable:
        raise DecisionNotPublishableError(list(run.publish_blockers))
    rows = _decision_rows(
        db,
        run.id,
        max_rows=MAX_EXPORT_ROWS,
        targets_only=export_kind in {"targets", "roster"},
    )
    output_rows = [
        {
            "dept_name": row.department_name,
            "position": row.position,
            "name": row.employee_name,
            "employee_code": row.employee_code,
            "hire_date": row.hire_date.isoformat(),
            "birth_date": row.birth_date.isoformat(),
            "age": row.age,
            "service_years": row.service_years,
            "prior_year_examined": row.prior_year_examined,
            "is_target": row.is_target,
            "reason": row.reason,
        }
        for row in rows
    ]
    settings_snapshot = dict(run.settings_snapshot)
    if export_kind == "roster":
        content = build_target_roster_xlsx(
            target_year=target_year, rows=output_rows, settings=settings_snapshot
        )
    else:
        content = build_employee_table_xlsx(
            sheet_title="대상자" if export_kind == "targets" else "전직원",
            headers=[
                "부서명",
                "직급",
                "이름",
                "사번",
                "입사일",
                "생년월일",
                "나이",
                "근속연수",
                "전년도 수검",
                "대상 여부",
                "판정 사유",
            ],
            rows=[
                [
                    row["dept_name"],
                    row["position"],
                    row["name"],
                    row["employee_code"],
                    row["hire_date"],
                    row["birth_date"],
                    row["age"],
                    row["service_years"],
                    _mark(row["prior_year_examined"]),
                    _mark(row["is_target"]),
                    _reason_label(row["reason"], settings_snapshot),
                ]
                for row in output_rows
            ],
        )
    if len(content) > MAX_EXPORT_BYTES:
        raise SourceUnavailableError("export_size_limit_exceeded")
    return DeterminationExport(
        content=content,
        run_id=run.id,
        exported_count=len(output_rows),
    )
