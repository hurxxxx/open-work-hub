from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import AuditLog
from ai_do_api.domains.auth.security import new_id, normalize_login_id
from ai_do_api.domains.hr.groupware_sync import (
    ACTIVE_COM_STATE,
    GROUPWARE_SOURCE_SYSTEM,
    GroupwareOrgRow,
    GroupwareUserRow,
    sync_groupware_hr,
)
from ai_do_api.domains.hr.models import (
    HR_SNAPSHOT_RETENTION_DAYS,
    HR_SYNC_LIVE_RUN_STATUSES,
    HrSyncChange,
    HrSyncOrgSnapshotRow,
    HrSyncRun,
    HrSyncUserSnapshotRow,
)


GROUPWARE_SCOPE_KEY = "groupware:domain-1"
HR_SNAPSHOT_SCHEMA_VERSION = "groupware-v1"
HR_CANONICALIZATION_VERSION = "json-sort-keys-v1"
HR_SYNC_TERMINAL_RUN_STATUSES = {
    "rejected",
    "succeeded",
    "failed",
    "skipped",
    "abandoned",
}
_MASS_MISSING_MINIMUM = 10
_MASS_MISSING_RATIO = 0.20
_RUN_LEASE_DURATION = timedelta(minutes=20)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_payload_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


_payload_hash = canonical_payload_hash


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _user_identity(domain_num: int, user_num: int) -> str:
    return f"{domain_num}:{user_num}"


def _org_identity(domain_num: int, org_code: str) -> str:
    return f"{domain_num}:{org_code.strip()}"


def _primary_org_code(row: GroupwareUserRow) -> str | None:
    org_codes = (
        row.org_code1,
        row.org_code2,
        row.org_code3,
        row.org_code4,
        row.org_code5,
        row.org_code6,
    )
    if row.org_level is not None and 1 <= row.org_level <= len(org_codes):
        selected = _clean_text(org_codes[row.org_level - 1])
        if selected is not None:
            return selected
    return next(
        (code for value in reversed(org_codes) if (code := _clean_text(value)) is not None),
        None,
    )


def _safe_error_summary(error: Exception) -> str:
    message = str(error).replace("\n", " ").strip()
    message = re.sub(r"://([^:/\s]+):([^@\s]+)@", r"://\1:[redacted]@", message)
    message = re.sub(
        r"(?i)(password|pwd|token|secret)\s*[=:]\s*[^\s,;]+",
        r"\1=[redacted]",
        message,
    )
    return f"{type(error).__name__}: {message}"[:500]


def list_hr_sync_runs(
    db: Session,
    *,
    source_system: str,
    scope_key: str,
    limit: int = 50,
) -> list[HrSyncRun]:
    safe_limit = max(1, min(limit, 500))
    return list(
        db.scalars(
            select(HrSyncRun)
            .where(
                HrSyncRun.source_system == source_system,
                HrSyncRun.scope_key == scope_key,
            )
            .order_by(HrSyncRun.created_at.desc(), HrSyncRun.id.desc())
            .limit(safe_limit)
        ).all()
    )


def list_groupware_hr_sync_runs(db: Session, *, limit: int = 50) -> list[HrSyncRun]:
    return list_hr_sync_runs(
        db,
        source_system=GROUPWARE_SOURCE_SYSTEM,
        scope_key=GROUPWARE_SCOPE_KEY,
        limit=limit,
    )


def load_latest_succeeded_hr_sync_run(
    db: Session,
    *,
    source_system: str,
    scope_key: str,
    before_run_id: str | None = None,
) -> HrSyncRun | None:
    query = select(HrSyncRun).where(
        HrSyncRun.source_system == source_system,
        HrSyncRun.scope_key == scope_key,
        HrSyncRun.status == "succeeded",
    )
    if before_run_id is not None:
        query = query.where(HrSyncRun.id != before_run_id)
    return db.scalar(query.order_by(HrSyncRun.applied_at.desc(), HrSyncRun.id.desc()).limit(1))


def load_latest_applied_groupware_hr_sync_run(
    db: Session,
    *,
    before_run_id: str | None = None,
) -> HrSyncRun | None:
    return load_latest_succeeded_hr_sync_run(
        db,
        source_system=GROUPWARE_SOURCE_SYSTEM,
        scope_key=GROUPWARE_SCOPE_KEY,
        before_run_id=before_run_id,
    )


def begin_hr_sync_run(
    db: Session,
    *,
    source_system: str,
    scope_key: str,
    schema_version: str,
    idempotency_key: str | None,
    trigger_kind: str = "scheduled",
    requested_by_user_id: str | None = None,
    synced_at: datetime | None = None,
    canonicalization_version: str = HR_CANONICALIZATION_VERSION,
) -> HrSyncRun:
    now = synced_at or utcnow_naive()
    stable_key = (idempotency_key or new_id()).strip() or new_id()
    existing = db.scalar(
        select(HrSyncRun).where(
            HrSyncRun.source_system == source_system,
            HrSyncRun.scope_key == scope_key,
            HrSyncRun.idempotency_key == stable_key,
        )
    )
    if existing is not None:
        return existing

    live_run = db.scalar(
        select(HrSyncRun)
        .where(
            HrSyncRun.source_system == source_system,
            HrSyncRun.scope_key == scope_key,
            HrSyncRun.status.in_(HR_SYNC_LIVE_RUN_STATUSES),
        )
        .order_by(HrSyncRun.started_at.asc())
        .limit(1)
    )
    if live_run is not None and (
        (live_run.lease_expires_at is not None and live_run.lease_expires_at <= now)
        or (live_run.lease_expires_at is None and live_run.started_at <= now - _RUN_LEASE_DURATION)
    ):
        live_run.status = "abandoned"
        live_run.error_phase = "lease"
        live_run.error_code = "stale_run_lease"
        live_run.error_summary = "HR sync run lease expired before completion"
        live_run.completed_at = now
        live_run.lease_owner = None
        live_run.lease_expires_at = None
        live_run.updated_at = now
        db.commit()
        live_run = None
    if live_run is not None:
        skipped = HrSyncRun(
            id=new_id(),
            source_system=source_system,
            scope_key=scope_key,
            trigger_kind=trigger_kind,
            requested_by_user_id=requested_by_user_id,
            celery_task_id=stable_key,
            idempotency_key=stable_key,
            blocked_by_run_id=live_run.id,
            status="skipped",
            attempts=0,
            schema_version=schema_version,
            canonicalization_version=canonicalization_version,
            result_payload={"reason": "another_sync_run_is_active"},
            started_at=now,
            completed_at=now,
            snapshot_purge_after=now + timedelta(days=HR_SNAPSHOT_RETENTION_DAYS),
            created_at=now,
            updated_at=now,
        )
        db.add(skipped)
        db.commit()
        return skipped

    run = HrSyncRun(
        id=new_id(),
        source_system=source_system,
        scope_key=scope_key,
        trigger_kind=trigger_kind,
        requested_by_user_id=requested_by_user_id,
        celery_task_id=stable_key,
        idempotency_key=stable_key,
        status="pending",
        attempts=1,
        lease_owner=stable_key,
        lease_expires_at=now + _RUN_LEASE_DURATION,
        schema_version=schema_version,
        canonicalization_version=canonicalization_version,
        started_at=now,
        snapshot_purge_after=now + timedelta(days=HR_SNAPSHOT_RETENTION_DAYS),
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(HrSyncRun).where(
                HrSyncRun.source_system == source_system,
                HrSyncRun.scope_key == scope_key,
                HrSyncRun.idempotency_key == stable_key,
            )
        )
        if raced is None:
            raise
        return raced
    return run


def begin_groupware_hr_sync_run(
    db: Session,
    *,
    idempotency_key: str | None,
    trigger_kind: str = "scheduled",
    requested_by_user_id: str | None = None,
    synced_at: datetime | None = None,
) -> HrSyncRun:
    return begin_hr_sync_run(
        db,
        source_system=GROUPWARE_SOURCE_SYSTEM,
        scope_key=GROUPWARE_SCOPE_KEY,
        schema_version=HR_SNAPSHOT_SCHEMA_VERSION,
        idempotency_key=idempotency_key,
        trigger_kind=trigger_kind,
        requested_by_user_id=requested_by_user_id,
        synced_at=synced_at,
    )


def _capture_snapshot(
    db: Session,
    *,
    run: HrSyncRun,
    departments: list[GroupwareOrgRow],
    users: list[GroupwareUserRow],
    captured_at: datetime,
) -> None:
    org_payloads = [asdict(row) for row in departments]
    user_payloads = [asdict(row) for row in users]

    for source_row_no, (row, raw_payload) in enumerate(zip(departments, org_payloads)):
        org_code = _clean_text(row.org_code)
        db.add(
            HrSyncOrgSnapshotRow(
                id=new_id(),
                run_id=run.id,
                source_row_no=source_row_no,
                domain_num=row.domain_num,
                org_code=org_code,
                source_identity=(
                    _org_identity(row.domain_num, org_code) if org_code is not None else None
                ),
                raw_payload=raw_payload,
                row_hash=_payload_hash(raw_payload),
                created_at=captured_at,
            )
        )
    for source_row_no, (row, raw_payload) in enumerate(zip(users, user_payloads)):
        db.add(
            HrSyncUserSnapshotRow(
                id=new_id(),
                run_id=run.id,
                source_row_no=source_row_no,
                domain_num=row.domain_num,
                user_num=row.user_num,
                source_identity=_user_identity(row.domain_num, row.user_num),
                employee_code=_clean_text(row.com_num),
                raw_payload=raw_payload,
                row_hash=_payload_hash(raw_payload),
                created_at=captured_at,
            )
        )

    run.status = "validating"
    run.org_row_count = len(departments)
    run.user_row_count = len(users)
    run.active_user_row_count = sum(row.com_state == ACTIVE_COM_STATE for row in users)
    run.org_snapshot_hash = _payload_hash(org_payloads)
    run.user_snapshot_hash = _payload_hash(user_payloads)
    run.captured_at = captured_at
    run.updated_at = captured_at
    db.commit()


def _duplicates(values: Iterable[object]) -> list[str]:
    counts = Counter(values)
    return sorted(str(value) for value, count in counts.items() if count > 1)


def _validate_snapshot(
    *,
    departments: list[GroupwareOrgRow],
    users: list[GroupwareUserRow],
    baseline_user_rows: list[HrSyncUserSnapshotRow],
    baseline_org_rows: list[HrSyncOrgSnapshotRow],
    allow_large_changes: bool,
) -> tuple[list[dict[str, object]], str | None]:
    errors: list[dict[str, object]] = []
    if not departments and not users:
        errors.append({"code": "empty_snapshot"})
        return errors, "empty_snapshot"
    if not departments or not users:
        errors.append(
            {
                "code": "partial_snapshot",
                "departments_present": bool(departments),
                "users_present": bool(users),
            }
        )
        return errors, "partial_snapshot"

    missing_org_identity_rows = [
        index
        for index, row in enumerate(departments)
        if row.domain_num is None or _clean_text(row.org_code) is None
    ]
    missing_user_identity_rows = [
        index for index, row in enumerate(users) if row.domain_num is None or row.user_num is None
    ]
    duplicate_orgs = _duplicates((row.domain_num, _clean_text(row.org_code)) for row in departments)
    duplicate_users = _duplicates((row.domain_num, row.user_num) for row in users)
    duplicate_logins = _duplicates(
        normalize_login_id(row.user_id) for row in users if row.com_state == ACTIVE_COM_STATE
    )
    org_identities = {
        (row.domain_num, org_code)
        for row in departments
        if (org_code := _clean_text(row.org_code)) is not None
    }
    missing_org_references = [
        {"source_row": index, "domain_num": row.domain_num, "org_code": org_code}
        for index, row in enumerate(users)
        if (org_code := _primary_org_code(row)) is not None
        and (row.domain_num, org_code) not in org_identities
    ]
    if duplicate_orgs:
        errors.append({"code": "duplicate_org_identity", "values": duplicate_orgs[:20]})
    if duplicate_users:
        errors.append({"code": "duplicate_user_identity", "values": duplicate_users[:20]})
    if missing_org_identity_rows:
        errors.append(
            {"code": "missing_org_identity", "source_rows": missing_org_identity_rows[:20]}
        )
    if missing_user_identity_rows:
        errors.append(
            {"code": "missing_user_identity", "source_rows": missing_user_identity_rows[:20]}
        )
    if duplicate_logins:
        errors.append({"code": "duplicate_active_login", "values": duplicate_logins[:20]})
    if missing_org_references:
        errors.append({"code": "missing_user_org_reference", "values": missing_org_references[:20]})

    if baseline_user_rows:
        previous = {
            (row.domain_num, row.user_num)
            for row in baseline_user_rows
            if row.domain_num is not None and row.user_num is not None
        }
        current = {(row.domain_num, row.user_num) for row in users}
        missing_count = len(previous - current)
        missing_ratio = missing_count / len(previous) if previous else 0.0
        if (
            not allow_large_changes
            and missing_count >= _MASS_MISSING_MINIMUM
            and missing_ratio > _MASS_MISSING_RATIO
        ):
            errors.append(
                {
                    "code": "unsafe_retirement_volume",
                    "missing_count": missing_count,
                    "previous_count": len(previous),
                    "missing_ratio": round(missing_ratio, 4),
                }
            )

    if baseline_org_rows:
        previous_orgs = {
            (row.domain_num, row.org_code)
            for row in baseline_org_rows
            if row.domain_num is not None and row.org_code is not None
        }
        current_orgs = {(row.domain_num, _clean_text(row.org_code)) for row in departments}
        missing_org_count = len(previous_orgs - current_orgs)
        missing_org_ratio = missing_org_count / len(previous_orgs) if previous_orgs else 0.0
        if (
            not allow_large_changes
            and missing_org_count >= _MASS_MISSING_MINIMUM
            and missing_org_ratio > _MASS_MISSING_RATIO
        ):
            errors.append(
                {
                    "code": "unsafe_org_deactivation_volume",
                    "missing_count": missing_org_count,
                    "previous_count": len(previous_orgs),
                    "missing_ratio": round(missing_org_ratio, 4),
                }
            )

    rejection_reason = errors[0]["code"] if errors else None
    return errors, str(rejection_reason) if rejection_reason else None


def _changed_fields(
    before: HrSyncUserSnapshotRow | HrSyncOrgSnapshotRow | None,
    after: HrSyncUserSnapshotRow | HrSyncOrgSnapshotRow | None,
) -> list[str]:
    before_payload = before.raw_payload if before is not None else {}
    after_payload = after.raw_payload if after is not None else {}
    return sorted(
        key
        for key in set(before_payload) | set(after_payload)
        if before_payload.get(key) != after_payload.get(key)
    )


def _persist_user_changes(
    db: Session,
    *,
    run: HrSyncRun,
    baseline_rows: list[HrSyncUserSnapshotRow],
    current_rows: list[HrSyncUserSnapshotRow],
    applied_changes: list[dict[str, object]],
    applied_at: datetime,
) -> None:
    before_by_identity = {row.source_identity: row for row in baseline_rows}
    after_by_identity = {row.source_identity: row for row in current_rows}
    change_by_identity = {
        _user_identity(int(change["domain_num"]), int(change["user_num"])): change
        for change in applied_changes
        if change.get("entity_kind") == "user"
        and change.get("domain_num") is not None
        and change.get("user_num") is not None
    }
    raw_to_persisted_kind = {
        "hire": "hired",
        "rehire_same_employee_code": "rehired",
        "retire_missing": "retired",
        "retire_inactive": "retired",
        "identity_conflict": "conflict",
        "update": "updated",
    }
    action_by_kind = {
        "hired": "create_user",
        "rehired": "activate_user",
        "retired": "suspend_user",
        "conflict": "review_identity",
        "updated": "update_user",
        "unchanged": "none",
        "baseline": "upsert_user",
    }

    identities = set(before_by_identity) | set(after_by_identity) | set(change_by_identity)
    for identity in sorted(item for item in identities if item is not None):
        before = before_by_identity.get(identity)
        after = after_by_identity.get(identity)
        applied = change_by_identity.get(identity, {})
        raw_kind = str(applied.get("change_kind") or "update")
        if raw_kind == "identity_conflict":
            change_kind = "conflict"
        elif run.comparison_run_id is None:
            change_kind = "baseline"
        else:
            change_kind = raw_to_persisted_kind.get(raw_kind, "updated")
            if (
                change_kind == "updated"
                and before is not None
                and after is not None
                and before.row_hash == after.row_hash
            ):
                change_kind = "unchanged"
        source_row = after or before
        if source_row is None:
            continue
        outcome = str(applied.get("outcome") or "applied")
        if change_kind == "unchanged":
            outcome = "skipped"
        db.add(
            HrSyncChange(
                id=new_id(),
                run_id=run.id,
                entity_kind="user",
                source_identity=identity,
                domain_num=source_row.domain_num,
                user_num=source_row.user_num,
                employee_code=(after.employee_code if after is not None else before.employee_code),
                change_kind=change_kind,
                action=action_by_kind[change_kind],
                outcome=outcome,
                before_snapshot_row_id=before.id if before is not None else None,
                after_snapshot_row_id=after.id if after is not None else None,
                target_entity_id=(
                    str(applied["target_entity_id"])
                    if applied.get("target_entity_id") is not None
                    else None
                ),
                changed_fields=_changed_fields(before, after),
                reason=str(applied["reason"]) if applied.get("reason") else None,
                created_at=applied_at,
                applied_at=applied_at if outcome == "applied" else None,
            )
        )


def _persist_org_changes(
    db: Session,
    *,
    run: HrSyncRun,
    baseline_rows: list[HrSyncOrgSnapshotRow],
    current_rows: list[HrSyncOrgSnapshotRow],
    applied_at: datetime,
) -> None:
    before_by_identity = {row.source_identity: row for row in baseline_rows}
    after_by_identity = {row.source_identity: row for row in current_rows}
    identities = set(before_by_identity) | set(after_by_identity)
    for identity in sorted(item for item in identities if item is not None):
        before = before_by_identity.get(identity)
        after = after_by_identity.get(identity)
        source_row = after or before
        if source_row is None:
            continue
        if run.comparison_run_id is None:
            change_kind, action = "baseline", "upsert_org"
        elif before is None:
            change_kind, action = "created", "create_org"
        elif after is None:
            change_kind, action = "deactivated", "deactivate_org"
        elif before.row_hash != after.row_hash:
            change_kind, action = "updated", "update_org"
        else:
            change_kind, action = "unchanged", "none"
        outcome = "skipped" if change_kind == "unchanged" else "applied"
        db.add(
            HrSyncChange(
                id=new_id(),
                run_id=run.id,
                entity_kind="org_unit",
                source_identity=identity,
                domain_num=source_row.domain_num,
                org_code=source_row.org_code,
                change_kind=change_kind,
                action=action,
                outcome=outcome,
                before_snapshot_row_id=before.id if before is not None else None,
                after_snapshot_row_id=after.id if after is not None else None,
                changed_fields=_changed_fields(before, after),
                created_at=applied_at,
                applied_at=applied_at if outcome == "applied" else None,
            )
        )


def process_groupware_hr_sync_run(
    db: Session,
    *,
    run_id: str,
    departments: list[GroupwareOrgRow],
    users: list[GroupwareUserRow],
    synced_at: datetime | None = None,
    allow_large_changes: bool = False,
) -> HrSyncRun:
    now = synced_at or utcnow_naive()
    run = db.get(HrSyncRun, run_id)
    if run is None:
        raise ValueError(f"Unknown HR sync run: {run_id}")
    if run.status in HR_SYNC_TERMINAL_RUN_STATUSES:
        return run

    if run.captured_at is None:
        run.status = "capturing"
        run.updated_at = now
        db.commit()
        _capture_snapshot(
            db,
            run=run,
            departments=departments,
            users=users,
            captured_at=now,
        )
    else:
        departments = [
            GroupwareOrgRow(**row.raw_payload)
            for row in db.scalars(
                select(HrSyncOrgSnapshotRow)
                .where(HrSyncOrgSnapshotRow.run_id == run.id)
                .order_by(HrSyncOrgSnapshotRow.source_row_no)
            ).all()
        ]
        users = [
            GroupwareUserRow(**row.raw_payload)
            for row in db.scalars(
                select(HrSyncUserSnapshotRow)
                .where(HrSyncUserSnapshotRow.run_id == run.id)
                .order_by(HrSyncUserSnapshotRow.source_row_no)
            ).all()
        ]

    baseline = load_latest_applied_groupware_hr_sync_run(db, before_run_id=run.id)
    baseline_user_rows = (
        list(
            db.scalars(
                select(HrSyncUserSnapshotRow)
                .where(HrSyncUserSnapshotRow.run_id == baseline.id)
                .order_by(HrSyncUserSnapshotRow.source_row_no)
            ).all()
        )
        if baseline is not None
        else []
    )
    baseline_org_rows = (
        list(
            db.scalars(
                select(HrSyncOrgSnapshotRow)
                .where(HrSyncOrgSnapshotRow.run_id == baseline.id)
                .order_by(HrSyncOrgSnapshotRow.source_row_no)
            ).all()
        )
        if baseline is not None
        else []
    )
    errors, rejection_reason = _validate_snapshot(
        departments=departments,
        users=users,
        baseline_user_rows=baseline_user_rows,
        baseline_org_rows=baseline_org_rows,
        allow_large_changes=allow_large_changes,
    )
    run.comparison_run_id = baseline.id if baseline is not None else None
    run.validation_payload = {
        "valid": not errors,
        "errors": errors,
        "comparison_run_id": run.comparison_run_id,
        "large_change_override": allow_large_changes,
    }
    if errors:
        run.status = "rejected"
        run.result_payload = {
            "rejection_reason": rejection_reason,
            "users_seen": len(users),
            "departments_seen": len(departments),
        }
        run.completed_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        run.updated_at = now
        db.commit()
        return run

    current_user_rows = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == run.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    current_org_rows = list(
        db.scalars(
            select(HrSyncOrgSnapshotRow)
            .where(HrSyncOrgSnapshotRow.run_id == run.id)
            .order_by(HrSyncOrgSnapshotRow.source_row_no)
        ).all()
    )
    previous_user_identities = {
        (row.domain_num, row.user_num)
        for row in baseline_user_rows
        if row.domain_num is not None and row.user_num is not None
    }
    previous_org_identities = {
        (row.domain_num, row.org_code)
        for row in baseline_org_rows
        if row.domain_num is not None and row.org_code is not None
    }

    run.status = "applying"
    run.updated_at = now
    db.commit()
    applied_changes: list[dict[str, object]] = []
    result = sync_groupware_hr(
        db,
        departments=departments,
        users=users,
        synced_at=now,
        previous_user_identities=previous_user_identities,
        previous_org_identities=previous_org_identities,
        changes=applied_changes,
        add_audit_log=False,
    )
    _persist_user_changes(
        db,
        run=run,
        baseline_rows=baseline_user_rows,
        current_rows=current_user_rows,
        applied_changes=applied_changes,
        applied_at=now,
    )
    _persist_org_changes(
        db,
        run=run,
        baseline_rows=baseline_org_rows,
        current_rows=current_org_rows,
        applied_at=now,
    )
    run.status = "succeeded"
    run.result_payload = result.to_dict()
    run.applied_at = now
    run.completed_at = now
    run.lease_owner = None
    run.lease_expires_at = None
    run.updated_at = now
    db.add(
        AuditLog(
            id=new_id(),
            actor_user_id=run.requested_by_user_id,
            action="hr.groupware.sync",
            entity_kind="hr_sync",
            entity_id=run.id,
            summary="Groupware HR sync completed",
            payload={"run_id": run.id, "status": run.status, **result.to_dict()},
            created_at=now,
        )
    )
    db.commit()
    return run


def fail_hr_sync_run(
    db: Session,
    *,
    run_id: str,
    phase: str,
    error: Exception,
    failed_at: datetime | None = None,
) -> HrSyncRun:
    db.rollback()
    now = failed_at or utcnow_naive()
    run = db.get(HrSyncRun, run_id)
    if run is None:
        raise ValueError(f"Unknown HR sync run: {run_id}")
    if run.status == "succeeded":
        return run
    run.status = "failed"
    run.error_phase = phase[:80]
    run.error_code = type(error).__name__[:120]
    run.error_summary = _safe_error_summary(error)
    run.completed_at = now
    run.lease_owner = None
    run.lease_expires_at = None
    run.updated_at = now
    db.commit()
    return run


def fail_groupware_hr_sync_run(
    db: Session,
    *,
    run_id: str,
    phase: str,
    error: Exception,
    failed_at: datetime | None = None,
) -> HrSyncRun:
    return fail_hr_sync_run(
        db,
        run_id=run_id,
        phase=phase,
        error=error,
        failed_at=failed_at,
    )


def run_groupware_hr_sync(
    db: Session,
    *,
    departments: list[GroupwareOrgRow],
    users: list[GroupwareUserRow],
    idempotency_key: str,
    trigger_kind: str = "scheduled",
    requested_by_user_id: str | None = None,
    synced_at: datetime | None = None,
    allow_large_changes: bool = False,
) -> HrSyncRun:
    run = begin_groupware_hr_sync_run(
        db,
        idempotency_key=idempotency_key,
        trigger_kind=trigger_kind,
        requested_by_user_id=requested_by_user_id,
        synced_at=synced_at,
    )
    if run.status in HR_SYNC_TERMINAL_RUN_STATUSES:
        return run
    try:
        return process_groupware_hr_sync_run(
            db,
            run_id=run.id,
            departments=departments,
            users=users,
            synced_at=synced_at,
            allow_large_changes=allow_large_changes,
        )
    except Exception as error:
        fail_groupware_hr_sync_run(
            db,
            run_id=run.id,
            phase="apply",
            error=error,
            failed_at=synced_at,
        )
        raise


def prune_hr_history(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int = HR_SNAPSHOT_RETENTION_DAYS,
) -> dict[str, int]:
    cutoff = (now or utcnow_naive()) - timedelta(days=max(retention_days, 1))
    protected_run_ids: set[str] = set()
    source_scopes = db.execute(
        select(HrSyncRun.source_system, HrSyncRun.scope_key)
        .where(HrSyncRun.status == "succeeded")
        .distinct()
    ).all()
    for source_system, scope_key in source_scopes:
        baseline = load_latest_succeeded_hr_sync_run(
            db,
            source_system=source_system,
            scope_key=scope_key,
        )
        if baseline is not None:
            protected_run_ids.add(baseline.id)
    eligible_run_ids = list(
        db.scalars(
            select(HrSyncRun.id).where(
                HrSyncRun.completed_at < cutoff,
                HrSyncRun.id.not_in(protected_run_ids),
                HrSyncRun.snapshots_purged_at.is_(None),
            )
        ).all()
    )
    if not eligible_run_ids:
        return {
            "runs_deleted": 0,
            "user_snapshots_deleted": 0,
            "department_snapshots_deleted": 0,
            "changes_deleted": 0,
        }

    user_result = db.execute(
        delete(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id.in_(eligible_run_ids))
    )
    org_result = db.execute(
        delete(HrSyncOrgSnapshotRow).where(HrSyncOrgSnapshotRow.run_id.in_(eligible_run_ids))
    )
    change_result = db.execute(
        delete(HrSyncChange).where(HrSyncChange.run_id.in_(eligible_run_ids))
    )
    purged_at = now or utcnow_naive()
    for run in db.scalars(select(HrSyncRun).where(HrSyncRun.id.in_(eligible_run_ids))).all():
        run.snapshots_purged_at = purged_at
        run.updated_at = purged_at
    db.commit()
    return {
        "runs_deleted": 0,
        "user_snapshots_deleted": max(user_result.rowcount or 0, 0),
        "department_snapshots_deleted": max(org_result.rowcount or 0, 0),
        "changes_deleted": max(change_result.rowcount or 0, 0),
    }


def prune_groupware_hr_history(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int = HR_SNAPSHOT_RETENTION_DAYS,
) -> dict[str, int]:
    return prune_hr_history(db, now=now, retention_days=retention_days)


__all__ = [
    "HR_CANONICALIZATION_VERSION",
    "HR_SYNC_TERMINAL_RUN_STATUSES",
    "begin_hr_sync_run",
    "begin_groupware_hr_sync_run",
    "fail_hr_sync_run",
    "fail_groupware_hr_sync_run",
    "canonical_payload_hash",
    "list_hr_sync_runs",
    "list_groupware_hr_sync_runs",
    "load_latest_succeeded_hr_sync_run",
    "load_latest_applied_groupware_hr_sync_run",
    "process_groupware_hr_sync_run",
    "prune_hr_history",
    "prune_groupware_hr_history",
    "run_groupware_hr_sync",
]
