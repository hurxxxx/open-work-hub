from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import resolve_workspace_role
from ai_do_api.domains.auth.models import User, Workspace, utcnow_naive
from ai_do_api.domains.legacy_issues.column_orders import (
    normalize_column_order_view_key,
)
from ai_do_api.domains.legacy_issues.models import LegacyIssueGridPreference
from ai_do_api.domains.legacy_issues.module_fields import normalize_module_key


LegacyIssueGridPreferenceKind = Literal[
    "dataset",
    "vehicle-module-checklist",
]

GRID_PREFERENCE_MAX_COLUMN_KEYS = 200
GRID_PREFERENCE_MAX_KEY_LENGTH = 160
GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT = 200


@dataclass(frozen=True)
class LegacyIssueGridPreferenceDTO:
    grid_kind: LegacyIssueGridPreferenceKind
    grid_key: str
    column_order: list[str]
    hidden_column_keys: list[str]
    frozen_column_count: int
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class LegacyIssueGridPreferenceStateDTO:
    preference: LegacyIssueGridPreferenceDTO | None
    revision: int


def normalize_grid_preference_scope_key(
    grid_kind: LegacyIssueGridPreferenceKind,
    grid_key: str,
) -> str:
    normalized = grid_key.strip()
    if not normalized or len(normalized) > GRID_PREFERENCE_MAX_KEY_LENGTH:
        raise ValueError(f"grid_key must contain 1-{GRID_PREFERENCE_MAX_KEY_LENGTH} characters")
    if grid_kind == "dataset":
        return normalize_column_order_view_key(normalized)
    if grid_kind == "vehicle-module-checklist":
        return normalize_module_key(normalized)
    raise ValueError(f"unsupported grid preference kind: {grid_kind}")


def normalize_grid_preference_column_keys(values: list[str]) -> list[str]:
    if len(values) > GRID_PREFERENCE_MAX_COLUMN_KEYS:
        raise ValueError(
            f"grid preference arrays may contain at most {GRID_PREFERENCE_MAX_COLUMN_KEYS} entries"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("grid preference column keys must be strings")
        key = value.strip()
        if not key:
            continue
        if len(key) > GRID_PREFERENCE_MAX_KEY_LENGTH:
            raise ValueError(
                f"grid preference column keys may contain at most "
                f"{GRID_PREFERENCE_MAX_KEY_LENGTH} characters"
            )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def normalize_grid_preference_frozen_column_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("frozen_column_count must be an integer")
    if value < 0 or value > GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT:
        raise ValueError(
            f"frozen_column_count must be between 0 and {GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT}"
        )
    return value


def get_grid_preference(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    grid_kind: LegacyIssueGridPreferenceKind,
    grid_key: str,
) -> LegacyIssueGridPreferenceStateDTO:
    _ensure_workspace_member(db, user=user, workspace=workspace)
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    row = db.get(
        LegacyIssueGridPreference,
        (workspace.id, user.id, grid_kind, normalized_grid_key),
    )
    if row is None:
        return LegacyIssueGridPreferenceStateDTO(preference=None, revision=0)
    return LegacyIssueGridPreferenceStateDTO(
        preference=None if row.is_deleted else _to_dto(row),
        revision=row.revision,
    )


def upsert_grid_preference(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    grid_kind: LegacyIssueGridPreferenceKind,
    grid_key: str,
    column_order: list[str],
    hidden_column_keys: list[str],
    frozen_column_count: int,
    expected_revision: int,
) -> LegacyIssueGridPreferenceDTO:
    _ensure_workspace_member(db, user=user, workspace=workspace)
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    normalized_column_order = normalize_grid_preference_column_keys(column_order)
    normalized_hidden_column_keys = normalize_grid_preference_column_keys(hidden_column_keys)
    normalized_frozen_column_count = normalize_grid_preference_frozen_column_count(
        frozen_column_count
    )
    normalized_expected_revision = _normalize_expected_revision(expected_revision)
    row = _write_grid_preference_revision(
        db,
        identity={
            "workspace_id": workspace.id,
            "user_id": user.id,
            "grid_kind": grid_kind,
            "grid_key": normalized_grid_key,
        },
        expected_revision=normalized_expected_revision,
        values={
            "column_order": normalized_column_order,
            "hidden_column_keys": normalized_hidden_column_keys,
            "frozen_column_count": normalized_frozen_column_count,
            "is_deleted": False,
        },
    )
    return _to_dto(row)


def delete_grid_preference(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    grid_kind: LegacyIssueGridPreferenceKind,
    grid_key: str,
    expected_revision: int,
) -> int:
    _ensure_workspace_member(db, user=user, workspace=workspace)
    normalized_grid_key = normalize_grid_preference_scope_key(
        grid_kind,
        grid_key,
    )
    normalized_expected_revision = _normalize_expected_revision(expected_revision)
    row = _write_grid_preference_revision(
        db,
        identity={
            "workspace_id": workspace.id,
            "user_id": user.id,
            "grid_kind": grid_kind,
            "grid_key": normalized_grid_key,
        },
        expected_revision=normalized_expected_revision,
        values={
            "column_order": [],
            "hidden_column_keys": [],
            "frozen_column_count": 0,
            "is_deleted": True,
        },
    )
    return row.revision


def _write_grid_preference_revision(
    db: Session,
    *,
    identity: dict[str, str],
    expected_revision: int,
    values: dict[str, object],
) -> LegacyIssueGridPreference:
    timestamp = utcnow_naive()
    next_revision = expected_revision + 1
    updated_revision = db.scalar(
        update(LegacyIssueGridPreference)
        .where(
            LegacyIssueGridPreference.workspace_id == identity["workspace_id"],
            LegacyIssueGridPreference.user_id == identity["user_id"],
            LegacyIssueGridPreference.grid_kind == identity["grid_kind"],
            LegacyIssueGridPreference.grid_key == identity["grid_key"],
            LegacyIssueGridPreference.revision == expected_revision,
        )
        .values(
            **values,
            revision=next_revision,
            updated_at=timestamp,
        )
        .returning(LegacyIssueGridPreference.revision)
    )
    if updated_revision != next_revision:
        if expected_revision != 0:
            _raise_revision_conflict()
        insert_values = {
            **identity,
            **values,
            "revision": next_revision,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        conflict_columns = [
            "workspace_id",
            "user_id",
            "grid_kind",
            "grid_key",
        ]
        dialect_name = db.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement = postgresql_insert(LegacyIssueGridPreference).values(
                **insert_values
            )
        elif dialect_name == "sqlite":
            statement = sqlite_insert(LegacyIssueGridPreference).values(**insert_values)
        else:
            raise RuntimeError(
                f"unsupported grid preference database dialect: {dialect_name}"
            )
        inserted_revision = db.scalar(
            statement.on_conflict_do_nothing(index_elements=conflict_columns).returning(
                LegacyIssueGridPreference.revision
            )
        )
        if inserted_revision != next_revision:
            _raise_revision_conflict()

    db.flush()
    row = db.scalar(
        select(LegacyIssueGridPreference)
        .where(
            LegacyIssueGridPreference.workspace_id == identity["workspace_id"],
            LegacyIssueGridPreference.user_id == identity["user_id"],
            LegacyIssueGridPreference.grid_kind == identity["grid_kind"],
            LegacyIssueGridPreference.grid_key == identity["grid_key"],
        )
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise RuntimeError("grid preference write did not return a row")
    return row


def _normalize_expected_revision(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    return value


def _raise_revision_conflict() -> None:
    raise localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="legacy_issues.grid_preference_revision_conflict",
    )


def _ensure_workspace_member(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> None:
    if resolve_workspace_role(db, user, workspace.id) is not None:
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="workspace.membership_required",
        workspace=workspace.key,
    )


def _to_dto(row: LegacyIssueGridPreference) -> LegacyIssueGridPreferenceDTO:
    return LegacyIssueGridPreferenceDTO(
        grid_kind=cast(LegacyIssueGridPreferenceKind, row.grid_kind),
        grid_key=row.grid_key,
        column_order=list(row.column_order),
        hidden_column_keys=list(row.hidden_column_keys),
        frozen_column_count=row.frozen_column_count,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


__all__ = [
    "GRID_PREFERENCE_MAX_COLUMN_KEYS",
    "GRID_PREFERENCE_MAX_FROZEN_COLUMN_COUNT",
    "GRID_PREFERENCE_MAX_KEY_LENGTH",
    "LegacyIssueGridPreferenceDTO",
    "LegacyIssueGridPreferenceKind",
    "LegacyIssueGridPreferenceStateDTO",
    "delete_grid_preference",
    "get_grid_preference",
    "normalize_grid_preference_column_keys",
    "normalize_grid_preference_frozen_column_count",
    "normalize_grid_preference_scope_key",
    "upsert_grid_preference",
]
