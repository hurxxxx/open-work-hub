from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import re
import secrets

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.access import normalize_locale, normalize_time_zone
from ai_do_api.domains.auth.date_format_preferences import default_date_format_value
from ai_do_api.domains.auth.models import AuditLog, AuthSession, OrgUnit, User
from ai_do_api.domains.auth.security import (
    hash_password,
    is_valid_login_id,
    new_id,
    normalize_email,
    normalize_login_id,
)


GROUPWARE_SOURCE_SYSTEM = "groupware"
AUTH_PROVIDER_LOCAL = "local"
AUTH_PROVIDER_GROUPWARE = "groupware"
ACTIVE_COM_STATE = 1


@dataclass(frozen=True)
class GroupwareOrgRow:
    domain_num: int
    org_code: str
    org_depart: str
    p_org_code: str | None = None
    org_order: int | None = None
    org_level: int | None = None
    depart_num: int | None = None


@dataclass(frozen=True)
class GroupwareUserRow:
    domain_num: int
    user_num: int
    user_id: str
    kor_name: str
    com_state: int
    email: str | None = None
    com_num: str | None = None
    com_position: str | None = None
    org_code1: str | None = None
    org_code2: str | None = None
    org_code3: str | None = None
    org_code4: str | None = None
    org_code5: str | None = None
    org_code6: str | None = None
    org_level: int | None = None
    user_order: int | None = None


@dataclass(frozen=True)
class GroupwareHrSyncResult:
    departments_seen: int = 0
    departments_created: int = 0
    departments_updated: int = 0
    departments_suspended: int = 0
    users_seen: int = 0
    users_created: int = 0
    users_updated: int = 0
    users_suspended: int = 0
    users_reactivated: int = 0
    sessions_revoked: int = 0
    skipped_inactive_users: int = 0
    skipped_duplicate_login_users: int = 0
    skipped_invalid_users: int = 0
    skipped_conflict_users: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class _SyncCounters:
    departments_seen: int = 0
    departments_created: int = 0
    departments_updated: int = 0
    departments_suspended: int = 0
    users_seen: int = 0
    users_created: int = 0
    users_updated: int = 0
    users_suspended: int = 0
    users_reactivated: int = 0
    sessions_revoked: int = 0
    skipped_inactive_users: int = 0
    skipped_duplicate_login_users: int = 0
    skipped_invalid_users: int = 0
    skipped_conflict_users: int = 0

    def result(self) -> GroupwareHrSyncResult:
        return GroupwareHrSyncResult(**asdict(self))


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _org_identity(row: GroupwareOrgRow) -> tuple[int, str]:
    return (row.domain_num, _clean_text(row.org_code) or "")


def _user_identity(row: GroupwareUserRow) -> tuple[int, int]:
    return (row.domain_num, row.user_num)


def _groupware_slug(domain_num: int, org_code: str) -> str:
    clean_org_code = _clean_text(org_code) or "unknown"
    safe_org_code = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", clean_org_code).strip("-")
    return f"groupware-{domain_num}-{safe_org_code or 'unknown'}"[:80]


def _primary_org_code(row: GroupwareUserRow) -> str | None:
    org_codes = {
        1: row.org_code1,
        2: row.org_code2,
        3: row.org_code3,
        4: row.org_code4,
        5: row.org_code5,
        6: row.org_code6,
    }
    if row.org_level is not None and 1 <= row.org_level <= 6:
        code = _clean_text(org_codes.get(row.org_level))
        if code:
            return code
    for index in range(6, 0, -1):
        code = _clean_text(org_codes[index])
        if code:
            return code
    return None


def _normalized_login_id(row: GroupwareUserRow) -> str | None:
    login_id = normalize_login_id(row.user_id)
    return login_id if is_valid_login_id(login_id) else None


def _normalized_email(row: GroupwareUserRow, login_id: str) -> str:
    candidate = normalize_email(row.email or "")
    if "@" in candidate:
        return candidate
    return f"{login_id}@groupware.local"


def _normalized_employee_code(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    return cleaned.casefold() if cleaned else None


def _revoke_active_sessions(
    db: Session,
    user: User,
    *,
    revoked_at: datetime,
    counters: _SyncCounters,
) -> None:
    result = db.execute(
        update(AuthSession)
        .where(
            or_(
                AuthSession.user_id == user.id,
                AuthSession.impersonator_user_id == user.id,
            ),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > revoked_at,
        )
        .values(revoked_at=revoked_at)
    )
    counters.sessions_revoked += max(result.rowcount or 0, 0)


def _load_same_employee_rehire_candidate(
    db: Session,
    row: GroupwareUserRow,
    *,
    current_employee_code_counts: Counter[str],
    current_source_identities: set[tuple[int, int]],
) -> tuple[User | None, str | None]:
    employee_code = _normalized_employee_code(row.com_num)
    if employee_code is None:
        return None, "missing_employee_code"
    if current_employee_code_counts[employee_code] != 1:
        return None, "duplicate_employee_code_in_snapshot"

    matches = [
        user
        for user in db.scalars(
            select(User).where(
                User.hr_source_system == GROUPWARE_SOURCE_SYSTEM,
            )
        ).all()
        if _normalized_employee_code(user.employee_code) == employee_code
    ]
    if len(matches) > 1:
        return None, "ambiguous_existing_employee_code"
    if matches:
        candidate = matches[0]
        candidate_identity = (candidate.hr_domain_num, candidate.hr_user_num)
        if candidate_identity in current_source_identities:
            return None, "employee_code_already_present_in_snapshot"
    return (matches[0], None) if matches else (None, None)


def _sync_org_units(
    db: Session,
    rows: list[GroupwareOrgRow],
    *,
    synced_at: datetime,
    counters: _SyncCounters,
    previous_identities: set[tuple[int, str]] | None = None,
) -> dict[tuple[int, str], OrgUnit]:
    existing_orgs = {
        (org.hr_domain_num, org.hr_org_code): org
        for org in db.scalars(
            select(OrgUnit).where(OrgUnit.hr_source_system == GROUPWARE_SOURCE_SYSTEM)
        ).all()
        if org.hr_domain_num is not None and org.hr_org_code
    }
    seen_identities = {_org_identity(row) for row in rows}
    orgs_by_identity: dict[tuple[int, str], OrgUnit] = {}

    for row in rows:
        counters.departments_seen += 1
        identity = _org_identity(row)
        org_code = identity[1]
        org = existing_orgs.get(identity)
        if org is None:
            org = OrgUnit(
                id=new_id(),
                slug=_groupware_slug(row.domain_num, org_code),
                name=_clean_text(row.org_depart) or org_code,
                unit_type="group",
                active=True,
                hr_source_system=GROUPWARE_SOURCE_SYSTEM,
                hr_domain_num=row.domain_num,
            )
            db.add(org)
            counters.departments_created += 1
        else:
            counters.departments_updated += 1

        parent_code = _clean_text(row.p_org_code)
        org.name = _clean_text(row.org_depart) or org_code or org.name
        org.unit_type = "division" if parent_code else "group"
        org.active = True
        org.hr_depart_num = row.depart_num
        org.hr_org_code = org_code
        org.hr_parent_org_code = parent_code
        org.hr_org_level = row.org_level
        org.hr_org_order = row.org_order
        org.hr_last_synced_at = synced_at
        orgs_by_identity[identity] = org

    db.flush()

    by_domain_code = {
        (org.hr_domain_num, org.hr_org_code): org
        for org in orgs_by_identity.values()
        if org.hr_domain_num is not None and org.hr_org_code
    }
    for org in orgs_by_identity.values():
        parent: OrgUnit | None = None
        if org.hr_parent_org_code:
            parent = by_domain_code.get((org.hr_domain_num, org.hr_parent_org_code))
        org.parent_id = parent.id if parent is not None and parent.id != org.id else None

    identities_to_suspend = previous_identities
    if identities_to_suspend is None:
        identities_to_suspend = set(existing_orgs)
    for identity, org in existing_orgs.items():
        if identity not in identities_to_suspend:
            continue
        if identity in seen_identities:
            continue
        if org.active:
            counters.departments_suspended += 1
        org.active = False
        org.hr_last_synced_at = synced_at

    db.flush()
    return by_domain_code


def _active_duplicate_login_ids(rows: list[GroupwareUserRow]) -> set[str]:
    login_ids: list[str] = []
    for row in rows:
        if row.com_state != ACTIVE_COM_STATE:
            continue
        login_id = _normalized_login_id(row)
        if login_id:
            login_ids.append(login_id)
    counts = Counter(login_ids)
    return {login_id for login_id, count in counts.items() if count > 1}


def _load_existing_user_by_source(
    db: Session,
    domain_num: int,
    user_num: int,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.hr_source_system == GROUPWARE_SOURCE_SYSTEM,
            User.hr_domain_num == domain_num,
            User.hr_user_num == user_num,
        )
    )


def _source_identity_conflicts(user: User, row: GroupwareUserRow) -> bool:
    if user.hr_source_system is None:
        return False
    return not (
        user.hr_source_system == GROUPWARE_SOURCE_SYSTEM
        and user.hr_domain_num == row.domain_num
        and user.hr_user_num == row.user_num
    )


def _sync_active_user(
    db: Session,
    row: GroupwareUserRow,
    *,
    login_id: str,
    orgs_by_domain_code: dict[tuple[int, str], OrgUnit],
    synced_at: datetime,
    counters: _SyncCounters,
    current_employee_code_counts: Counter[str],
    current_source_identities: set[tuple[int, int]],
    previous_identities: set[tuple[int, int]] | None,
) -> tuple[User | None, str, str | None]:
    user = _load_existing_user_by_source(db, row.domain_num, row.user_num)
    was_reactivated = False
    is_returning_source_identity = (
        user is not None
        and user.status == "suspended"
        and previous_identities is not None
        and _user_identity(row) not in previous_identities
    )
    if is_returning_source_identity:
        previous_employee_code = _normalized_employee_code(user.employee_code)
        current_employee_code = _normalized_employee_code(row.com_num)
        if current_employee_code is None:
            counters.skipped_conflict_users += 1
            return None, "identity_conflict", "missing_employee_code"
        if previous_employee_code != current_employee_code:
            counters.skipped_conflict_users += 1
            return None, "identity_conflict", "employee_code_changed_on_return"

    if user is None:
        rehire_candidate, conflict_reason = _load_same_employee_rehire_candidate(
            db,
            row,
            current_employee_code_counts=current_employee_code_counts,
            current_source_identities=current_source_identities,
        )
        if conflict_reason is not None:
            counters.skipped_conflict_users += 1
            return None, "identity_conflict", conflict_reason
        if rehire_candidate is not None:
            login_owner = db.scalar(select(User).where(User.login_id == login_id))
            if login_owner is not None and login_owner.id != rehire_candidate.id:
                counters.skipped_conflict_users += 1
                return None, "identity_conflict", "login_id_owned_by_another_user"
            user = rehire_candidate
            was_reactivated = user.status == "suspended"

    if user is None:
        candidate = db.scalar(select(User).where(User.login_id == login_id))
        if candidate is not None and (
            candidate.hr_source_system is None or _source_identity_conflicts(candidate, row)
        ):
            counters.skipped_conflict_users += 1
            return None, "identity_conflict", "login_id_owned_by_another_identity"
        user = candidate

    if user is None:
        user = User(
            id=new_id(),
            login_id=login_id,
            email=_normalized_email(row, login_id),
            full_name=_clean_text(row.kor_name) or login_id,
            display_name=_clean_text(row.kor_name) or login_id,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            status="active",
            auth_provider=AUTH_PROVIDER_GROUPWARE,
            must_change_password=False,
            theme_preference="system",
            locale=normalize_locale(None),
            time_zone=normalize_time_zone(None),
            date_format=default_date_format_value(),
        )
        db.add(user)
        counters.users_created += 1
        change_kind = "hire"
    else:
        counters.users_updated += 1
        if user.status == "suspended":
            was_reactivated = True
        change_kind = "rehire_same_employee_code" if was_reactivated else "update"

    primary_org: OrgUnit | None = None
    primary_org_code = _primary_org_code(row)
    if primary_org_code:
        primary_org = orgs_by_domain_code.get((row.domain_num, primary_org_code))

    name = _clean_text(row.kor_name) or login_id
    user.login_id = login_id
    user.email = _normalized_email(row, login_id)
    user.full_name = name
    user.display_name = name
    user.employee_code = _clean_text(row.com_num)
    user.job_title = _clean_text(row.com_position)
    user.status = "active"
    user.auth_provider = AUTH_PROVIDER_GROUPWARE
    user.must_change_password = False
    user.primary_org_unit_id = primary_org.id if primary_org else None
    user.hr_source_system = GROUPWARE_SOURCE_SYSTEM
    user.hr_domain_num = row.domain_num
    user.hr_user_num = row.user_num
    user.hr_com_state = row.com_state
    user.hr_last_synced_at = synced_at
    if was_reactivated:
        counters.users_reactivated += 1
    return user, change_kind, None


def _sync_inactive_user(
    db: Session,
    row: GroupwareUserRow,
    *,
    synced_at: datetime,
    counters: _SyncCounters,
) -> User | None:
    user = _load_existing_user_by_source(db, row.domain_num, row.user_num)
    if user is None:
        counters.skipped_inactive_users += 1
        return None
    if user.status != "suspended":
        counters.users_suspended += 1
    user.status = "suspended"
    user.hr_com_state = row.com_state
    user.hr_last_synced_at = synced_at
    _revoke_active_sessions(db, user, revoked_at=synced_at, counters=counters)
    return user


def _sync_users(
    db: Session,
    rows: list[GroupwareUserRow],
    *,
    orgs_by_domain_code: dict[tuple[int, str], OrgUnit],
    synced_at: datetime,
    counters: _SyncCounters,
    previous_identities: set[tuple[int, int]] | None = None,
    changes: list[dict[str, object]] | None = None,
) -> None:
    counters.users_seen = len(rows)
    duplicate_login_ids = _active_duplicate_login_ids(rows)
    current_employee_code_counts: Counter[str] = Counter(
        employee_code
        for row in rows
        if row.com_state == ACTIVE_COM_STATE
        if (employee_code := _normalized_employee_code(row.com_num)) is not None
    )
    seen_identities: set[tuple[int, int]] = set()
    current_source_identities = {_user_identity(row) for row in rows}

    for row in rows:
        seen_identities.add(_user_identity(row))
        if row.com_state != ACTIVE_COM_STATE:
            user = _sync_inactive_user(db, row, synced_at=synced_at, counters=counters)
            if changes is not None:
                changes.append(
                    {
                        "entity_kind": "user",
                        "change_kind": "retire_inactive",
                        "domain_num": row.domain_num,
                        "user_num": row.user_num,
                        "employee_code": _clean_text(row.com_num),
                        "target_entity_id": user.id if user else None,
                        "outcome": "applied" if user else "skipped",
                        "reason": None if user else "source_user_not_found",
                    }
                )
            continue

        login_id = _normalized_login_id(row)
        if login_id is None:
            counters.skipped_invalid_users += 1
            if changes is not None:
                changes.append(
                    {
                        "entity_kind": "user",
                        "change_kind": "identity_conflict",
                        "domain_num": row.domain_num,
                        "user_num": row.user_num,
                        "employee_code": _clean_text(row.com_num),
                        "target_entity_id": None,
                        "outcome": "blocked",
                        "reason": "invalid_login_id",
                    }
                )
            continue
        if login_id in duplicate_login_ids:
            counters.skipped_duplicate_login_users += 1
            if changes is not None:
                changes.append(
                    {
                        "entity_kind": "user",
                        "change_kind": "identity_conflict",
                        "domain_num": row.domain_num,
                        "user_num": row.user_num,
                        "employee_code": _clean_text(row.com_num),
                        "target_entity_id": None,
                        "outcome": "blocked",
                        "reason": "duplicate_login_id",
                    }
                )
            continue

        user, change_kind, reason = _sync_active_user(
            db,
            row,
            login_id=login_id,
            orgs_by_domain_code=orgs_by_domain_code,
            synced_at=synced_at,
            counters=counters,
            current_employee_code_counts=current_employee_code_counts,
            current_source_identities=current_source_identities,
            previous_identities=previous_identities,
        )
        if changes is not None:
            changes.append(
                {
                    "entity_kind": "user",
                    "change_kind": change_kind,
                    "domain_num": row.domain_num,
                    "user_num": row.user_num,
                    "employee_code": _clean_text(row.com_num),
                    "target_entity_id": user.id if user else None,
                    "outcome": "applied" if user else "blocked",
                    "reason": reason,
                }
            )

    identities_to_suspend = previous_identities
    if identities_to_suspend is None:
        identities_to_suspend = {
            (user.hr_domain_num, user.hr_user_num)
            for user in db.scalars(
                select(User).where(User.hr_source_system == GROUPWARE_SOURCE_SYSTEM)
            ).all()
            if user.hr_domain_num is not None and user.hr_user_num is not None
        }
    for user in db.scalars(
        select(User).where(User.hr_source_system == GROUPWARE_SOURCE_SYSTEM)
    ).all():
        if user.hr_domain_num is None or user.hr_user_num is None:
            continue
        identity = (user.hr_domain_num, user.hr_user_num)
        if identity not in identities_to_suspend or identity in seen_identities:
            continue
        if user.status != "suspended":
            counters.users_suspended += 1
        user.status = "suspended"
        user.hr_last_synced_at = synced_at
        _revoke_active_sessions(db, user, revoked_at=synced_at, counters=counters)
        if changes is not None:
            changes.append(
                {
                    "entity_kind": "user",
                    "change_kind": "retire_missing",
                    "domain_num": user.hr_domain_num,
                    "user_num": user.hr_user_num,
                    "employee_code": user.employee_code,
                    "target_entity_id": user.id,
                    "outcome": "applied",
                    "reason": "missing_from_latest_complete_snapshot",
                }
            )


def sync_groupware_hr(
    db: Session,
    *,
    departments: list[GroupwareOrgRow],
    users: list[GroupwareUserRow],
    synced_at: datetime | None = None,
    previous_user_identities: set[tuple[int, int]] | None = None,
    previous_org_identities: set[tuple[int, str]] | None = None,
    changes: list[dict[str, object]] | None = None,
    add_audit_log: bool = True,
) -> GroupwareHrSyncResult:
    synced_at = synced_at or utcnow_naive()
    counters = _SyncCounters()

    orgs_by_domain_code = _sync_org_units(
        db,
        departments,
        synced_at=synced_at,
        counters=counters,
        previous_identities=previous_org_identities,
    )
    _sync_users(
        db,
        users,
        orgs_by_domain_code=orgs_by_domain_code,
        synced_at=synced_at,
        counters=counters,
        previous_identities=previous_user_identities,
        changes=changes,
    )
    result = counters.result()
    if add_audit_log:
        db.add(
            AuditLog(
                id=new_id(),
                actor_user_id=None,
                action="hr.groupware.sync",
                entity_kind="hr_sync",
                entity_id=None,
                summary="Groupware HR sync completed",
                payload=result.to_dict(),
                created_at=synced_at,
            )
        )
    db.flush()
    return result
