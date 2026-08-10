from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import (
    is_platform_admin_user,
    resolve_workspace_role,
)
from ai_do_api.domains.auth.models import Team, TeamMember, User, Workspace, utcnow_naive
from ai_do_api.domains.auth.roles import workspace_role_allows
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.legacy_issues.dataset_records import (
    LEGACY_ISSUE_MODULE_FIELD_TYPES,
    LEGACY_ISSUE_MODULE_KEYS,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueModuleAccessRule,
    LegacyIssueModuleField,
)


MODULE_FIELD_KEY_PREFIX = "custom"
MODULE_ACCESS_ROLE_RANK = {"viewer": 10, "editor": 20, "manager": 30}


@dataclass(frozen=True)
class LegacyIssueModuleFieldDTO:
    id: str
    module_key: str
    field_key: str
    label_ko: str
    label_en: str
    field_type: str
    options: list[str]
    allow_multiple: bool
    required: bool
    sort_order: int
    active: bool
    created_at: Any
    updated_at: Any


def ensure_legacy_issue_module_manager(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    module_key: str | None = None,
) -> None:
    if module_key is None:
        if is_platform_admin_user(user, db) or workspace_role_allows(
            resolve_workspace_role(db, user, workspace.id),
            "admin",
        ):
            return
    elif legacy_issue_module_role_allows(
        resolve_legacy_issue_module_access(
            db,
            user=user,
            workspace=workspace,
            module_key=module_key,
        ),
        "manager",
    ):
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="legacy_issues.module_field_manage_required",
    )


def resolve_legacy_issue_module_access(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    module_key: str,
) -> str | None:
    normalized_module_key = normalize_module_key(module_key)
    if is_platform_admin_user(user, db) or workspace_role_allows(
        resolve_workspace_role(db, user, workspace.id),
        "admin",
    ):
        return "manager"

    candidates: list[tuple[str, str]] = [("user", user.id)]
    if user.primary_org_unit_id:
        candidates.append(("org_unit", user.primary_org_unit_id))
    team_ids = list(
        db.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.user_id == user.id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
    )
    candidates.extend(("team", team_id) for team_id in team_ids)
    if not candidates:
        return None
    rules = list(
        db.scalars(
            select(LegacyIssueModuleAccessRule).where(
                LegacyIssueModuleAccessRule.workspace_id == workspace.id,
                LegacyIssueModuleAccessRule.module_key == normalized_module_key,
                LegacyIssueModuleAccessRule.active.is_(True),
            )
        )
    )
    candidate_set = set(candidates)
    role: str | None = None
    for rule in rules:
        if (rule.subject_type, rule.subject_id) not in candidate_set:
            continue
        role = higher_module_role(role, rule.role)
    return role


def legacy_issue_module_role_allows(role: str | None, min_role: str) -> bool:
    if min_role not in MODULE_ACCESS_ROLE_RANK:
        raise ValueError(f"Unknown legacy issue module role: {min_role}")
    if role not in MODULE_ACCESS_ROLE_RANK:
        return False
    return MODULE_ACCESS_ROLE_RANK[role] >= MODULE_ACCESS_ROLE_RANK[min_role]


def higher_module_role(left: str | None, right: str | None) -> str | None:
    if right not in MODULE_ACCESS_ROLE_RANK:
        return left
    if left not in MODULE_ACCESS_ROLE_RANK:
        return right
    return right if MODULE_ACCESS_ROLE_RANK[right] > MODULE_ACCESS_ROLE_RANK[left] else left


def list_module_fields(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str | None = None,
    include_inactive: bool = True,
) -> list[LegacyIssueModuleFieldDTO]:
    statement = select(LegacyIssueModuleField).where(
        LegacyIssueModuleField.workspace_id == workspace.id
    )
    if module_key:
        statement = statement.where(
            LegacyIssueModuleField.module_key == normalize_module_key(module_key)
        )
    if not include_inactive:
        statement = statement.where(LegacyIssueModuleField.active.is_(True))
    rows = list(
        db.scalars(
            statement.order_by(
                LegacyIssueModuleField.module_key.asc(),
                LegacyIssueModuleField.sort_order.asc(),
                LegacyIssueModuleField.created_at.asc(),
            )
        )
    )
    return [module_field_dto(row) for row in rows]


def create_module_field(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    module_key: str,
    label_ko: str,
    label_en: str | None,
    field_type: str,
    options: list[str] | None,
    required: bool,
    allow_multiple: bool = False,
    sort_order: int | None = None,
) -> LegacyIssueModuleFieldDTO:
    normalized_module_key = normalize_module_key(module_key)
    normalized_field_type = normalize_field_type(field_type)
    normalized_options = normalize_field_options(
        normalized_field_type,
        options,
    )
    normalized_allow_multiple = normalize_field_allow_multiple(
        normalized_field_type,
        allow_multiple,
    )
    next_order = (
        sort_order
        if sort_order is not None
        else next_module_field_sort_order(db, workspace=workspace, module_key=normalized_module_key)
    )
    now = utcnow_naive()
    row = LegacyIssueModuleField(
        id=new_id(),
        workspace_id=workspace.id,
        module_key=normalized_module_key,
        field_key=new_module_field_key(normalized_module_key),
        label_ko=normalize_label(label_ko),
        label_en=normalize_label(label_en or label_ko),
        field_type=normalized_field_type,
        options=normalized_options,
        allow_multiple=normalized_allow_multiple,
        required=required,
        sort_order=next_order,
        active=True,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return module_field_dto(row)


def update_module_field(
    db: Session,
    *,
    workspace: Workspace,
    field_id: str,
    label_ko: str | None = None,
    label_en: str | None = None,
    field_type: str | None = None,
    options: list[str] | None = None,
    allow_multiple: bool | None = None,
    required: bool | None = None,
    sort_order: int | None = None,
    active: bool | None = None,
) -> LegacyIssueModuleFieldDTO:
    row = get_module_field_row(db, workspace=workspace, field_id=field_id)
    next_field_type = normalize_field_type(field_type or row.field_type)
    if label_ko is not None:
        row.label_ko = normalize_label(label_ko)
    if label_en is not None:
        row.label_en = normalize_label(label_en or row.label_ko)
    if field_type is not None:
        row.field_type = next_field_type
    if options is not None or field_type is not None:
        row.options = normalize_field_options(
            next_field_type, options if options is not None else row.options
        )
    if allow_multiple is not None or field_type is not None:
        row.allow_multiple = normalize_field_allow_multiple(
            next_field_type,
            row.allow_multiple if allow_multiple is None else allow_multiple,
        )
    if required is not None:
        row.required = required
    if sort_order is not None:
        row.sort_order = sort_order
    if active is not None:
        row.active = active
    row.updated_at = utcnow_naive()
    db.add(row)
    db.flush()
    return module_field_dto(row)


def deactivate_module_field(
    db: Session,
    *,
    workspace: Workspace,
    field_id: str,
) -> LegacyIssueModuleFieldDTO:
    return update_module_field(db, workspace=workspace, field_id=field_id, active=False)


def reorder_module_fields(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
    field_ids: list[str],
) -> list[LegacyIssueModuleFieldDTO]:
    normalized_module_key = normalize_module_key(module_key)
    rows = {
        row.id: row
        for row in db.scalars(
            select(LegacyIssueModuleField).where(
                LegacyIssueModuleField.workspace_id == workspace.id,
                LegacyIssueModuleField.module_key == normalized_module_key,
            )
        )
    }
    missing_ids = [field_id for field_id in field_ids if field_id not in rows]
    if missing_ids:
        raise localized_http_exception(
            status_code=404,
            code="legacy_issues.module_field_not_found",
            detail=", ".join(missing_ids[:5]),
        )
    now = utcnow_naive()
    for index, field_id in enumerate(field_ids):
        row = rows[field_id]
        row.sort_order = index
        row.updated_at = now
        db.add(row)
    db.flush()
    return list_module_fields(db, workspace=workspace, module_key=normalized_module_key)


def get_module_field_row(
    db: Session,
    *,
    workspace: Workspace,
    field_id: str,
) -> LegacyIssueModuleField:
    row = db.scalar(
        select(LegacyIssueModuleField).where(
            LegacyIssueModuleField.id == field_id,
            LegacyIssueModuleField.workspace_id == workspace.id,
        )
    )
    if row is None:
        raise localized_http_exception(status_code=404, code="legacy_issues.module_field_not_found")
    return row


def module_field_dto(row: LegacyIssueModuleField) -> LegacyIssueModuleFieldDTO:
    return LegacyIssueModuleFieldDTO(
        id=row.id,
        module_key=row.module_key,
        field_key=row.field_key,
        label_ko=row.label_ko,
        label_en=row.label_en,
        field_type=row.field_type,
        options=list(row.options or []),
        allow_multiple=row.allow_multiple,
        required=row.required,
        sort_order=row.sort_order,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def normalize_module_key(module_key: str) -> str:
    normalized = module_key.strip()
    if normalized not in LEGACY_ISSUE_MODULE_KEYS:
        raise localized_http_exception(status_code=404, code="legacy_issues.module_not_found")
    return normalized


def normalize_field_type(field_type: str) -> str:
    normalized = field_type.strip()
    if normalized not in LEGACY_ISSUE_MODULE_FIELD_TYPES:
        raise localized_http_exception(status_code=400, code="legacy_issues.module_field_invalid")
    return normalized


def normalize_label(label: str) -> str:
    normalized = " ".join(label.strip().split())
    if not normalized or len(normalized) > 120:
        raise localized_http_exception(status_code=400, code="legacy_issues.module_field_invalid")
    return normalized


def normalize_field_options(field_type: str, options: list[str] | None) -> list[str] | None:
    if field_type != "select":
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for option in options or []:
        value = " ".join(str(option).strip().split())
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    if not normalized:
        raise localized_http_exception(status_code=400, code="legacy_issues.module_field_invalid")
    return normalized[:100]


def normalize_field_allow_multiple(field_type: str, allow_multiple: bool) -> bool:
    if field_type not in {"select", "user", "orgUnit"}:
        return False
    return bool(allow_multiple)


def next_module_field_sort_order(
    db: Session,
    *,
    workspace: Workspace,
    module_key: str,
) -> int:
    existing_orders = [
        value
        for value in db.scalars(
            select(LegacyIssueModuleField.sort_order).where(
                LegacyIssueModuleField.workspace_id == workspace.id,
                LegacyIssueModuleField.module_key == module_key,
            )
        )
    ]
    return (max(existing_orders) + 1) if existing_orders else 0


def new_module_field_key(module_key: str) -> str:
    token = new_id().replace("-", "")[:12]
    safe_module = module_key.replace("-", "_")
    return f"{MODULE_FIELD_KEY_PREFIX}__{safe_module}__{token}"
