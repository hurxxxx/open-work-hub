from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    LEGACY_ISSUE_MODULE_KEYS,
)
from open_alm_api.domains.legacy_issues.models import LegacyIssueColumnOrder


COLUMN_ORDER_ATTACHMENT_KEY = "primary_attachment"


@dataclass(frozen=True)
class LegacyIssueColumnOrderDTO:
    view_key: str
    column_order: list[str]
    hidden_column_keys: list[str]
    updated_at: Any | None = None


def normalize_column_order_view_key(view_key: str | None) -> str:
    normalized = (view_key or "").strip()
    if not normalized or normalized == COMMON_MASTER_DATASET_KEY:
        return COMMON_MASTER_DATASET_KEY
    if normalized not in LEGACY_ISSUE_MODULE_KEYS:
        raise localized_http_exception(status_code=404, code="legacy_issues.module_not_found")
    return normalized


def sanitize_column_order(
    column_order: list[str],
    *,
    available_keys: list[str],
) -> list[str]:
    available_set = set(available_keys)
    seen: set[str] = set()
    ordered: list[str] = []
    for key in column_order:
        if key not in available_set or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    for key in available_keys:
        if key in seen:
            continue
        ordered.insert(
            _missing_column_insert_index(
                key,
                ordered=ordered,
                available_keys=available_keys,
            ),
            key,
        )
        seen.add(key)
    return ordered


def sanitize_hidden_column_keys(
    hidden_column_keys: list[str],
    *,
    available_keys: list[str],
) -> list[str]:
    available_set = set(available_keys)
    hidden_set = {key for key in hidden_column_keys if key and key in available_set}
    if available_keys and len(hidden_set) == len(available_set):
        hidden_set.discard(available_keys[0])
    return [key for key in available_keys if key in hidden_set]


def _missing_column_insert_index(
    key: str,
    *,
    ordered: list[str],
    available_keys: list[str],
) -> int:
    try:
        default_index = available_keys.index(key)
    except ValueError:
        return len(ordered)
    for previous_key in reversed(available_keys[:default_index]):
        if previous_key in ordered:
            return ordered.index(previous_key) + 1
    for next_key in available_keys[default_index + 1 :]:
        if next_key in ordered:
            return ordered.index(next_key)
    return len(ordered)


def get_column_order(
    db: Session,
    *,
    workspace: Workspace,
    view_key: str,
    available_keys: list[str],
) -> LegacyIssueColumnOrderDTO:
    normalized_view_key = normalize_column_order_view_key(view_key)
    row = db.scalar(
        select(LegacyIssueColumnOrder).where(
            LegacyIssueColumnOrder.workspace_id == workspace.id,
            LegacyIssueColumnOrder.view_key == normalized_view_key,
        )
    )
    if row is None:
        return LegacyIssueColumnOrderDTO(
            view_key=normalized_view_key,
            column_order=list(available_keys),
            hidden_column_keys=[],
            updated_at=None,
        )
    return LegacyIssueColumnOrderDTO(
        view_key=normalized_view_key,
        column_order=sanitize_column_order(
            list(row.column_order or []),
            available_keys=available_keys,
        ),
        hidden_column_keys=sanitize_hidden_column_keys(
            list(row.hidden_column_keys or []),
            available_keys=available_keys,
        ),
        updated_at=row.updated_at,
    )


def upsert_column_order(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    view_key: str,
    column_order: list[str],
    hidden_column_keys: list[str] | None = None,
    available_keys: list[str],
) -> LegacyIssueColumnOrderDTO:
    normalized_view_key = normalize_column_order_view_key(view_key)
    sanitized_order = sanitize_column_order(column_order, available_keys=available_keys)
    sanitized_hidden_column_keys = (
        sanitize_hidden_column_keys(
            hidden_column_keys,
            available_keys=available_keys,
        )
        if hidden_column_keys is not None
        else None
    )
    row = db.scalar(
        select(LegacyIssueColumnOrder).where(
            LegacyIssueColumnOrder.workspace_id == workspace.id,
            LegacyIssueColumnOrder.view_key == normalized_view_key,
        )
    )
    now = utcnow_naive()
    if row is None:
        row = LegacyIssueColumnOrder(
            id=new_id(),
            workspace_id=workspace.id,
            view_key=normalized_view_key,
            column_order=sanitized_order,
            hidden_column_keys=sanitized_hidden_column_keys or [],
            updated_by_id=user.id,
            created_at=now,
            updated_at=now,
        )
    else:
        row.column_order = sanitized_order
        if sanitized_hidden_column_keys is not None:
            row.hidden_column_keys = sanitized_hidden_column_keys
        row.updated_by_id = user.id
        row.updated_at = now
    db.add(row)
    db.flush()
    return LegacyIssueColumnOrderDTO(
        view_key=normalized_view_key,
        column_order=sanitized_order,
        hidden_column_keys=sanitize_hidden_column_keys(
            list(row.hidden_column_keys or []),
            available_keys=available_keys,
        ),
        updated_at=row.updated_at,
    )
