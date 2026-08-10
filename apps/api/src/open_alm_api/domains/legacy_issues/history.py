from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.models import LegacyIssueRecordHistory


LEGACY_ISSUE_RECORD_KIND = "legacy_issue"


@dataclass(frozen=True)
class LegacyIssueHistoryChange:
    field_key: str
    field_label: str
    old_value: str | None
    new_value: str | None


def collect_value_changes(
    *,
    old_values: Mapping[str, Any],
    new_values: Mapping[str, Any],
    field_labels: Mapping[str, str],
) -> list[LegacyIssueHistoryChange]:
    changes: list[LegacyIssueHistoryChange] = []
    for field_key, new_value in new_values.items():
        old_text = normalize_history_value(old_values.get(field_key))
        new_text = normalize_history_value(new_value)
        if old_text == new_text:
            continue
        changes.append(
            LegacyIssueHistoryChange(
                field_key=field_key,
                field_label=field_labels.get(field_key, field_key),
                old_value=old_text,
                new_value=new_text,
            )
        )
    return changes


def collect_create_changes(
    *,
    values: Mapping[str, Any],
    field_labels: Mapping[str, str],
) -> list[LegacyIssueHistoryChange]:
    changes: list[LegacyIssueHistoryChange] = []
    for field_key, value in values.items():
        value_text = normalize_history_value(value)
        if value_text is None:
            continue
        changes.append(
            LegacyIssueHistoryChange(
                field_key=field_key,
                field_label=field_labels.get(field_key, field_key),
                old_value=None,
                new_value=value_text,
            )
        )
    return changes


def add_record_history_entries(
    db: Session,
    *,
    workspace: Workspace,
    user: User | None,
    record_kind: str,
    record_id: str,
    action: str,
    changes: Iterable[LegacyIssueHistoryChange],
    dataset_key: str | None = None,
    details: dict[str, Any] | None = None,
    revision_id: str | None = None,
) -> None:
    entry_details = _history_details(details=details, revision_id=revision_id)
    for change in changes:
        db.add(
            LegacyIssueRecordHistory(
                id=new_id(),
                workspace_id=workspace.id,
                record_kind=record_kind,
                dataset_key=dataset_key,
                record_id=record_id,
                action=action,
                field_key=change.field_key,
                field_label=change.field_label,
                old_value=change.old_value,
                new_value=change.new_value,
                actor_user_id=user.id if user else None,
                details=entry_details,
            )
        )


def add_attachment_history_entry(
    db: Session,
    *,
    workspace: Workspace,
    user: User | None,
    record_kind: str,
    record_id: str,
    action: str,
    field_label: str,
    old_value: str | None,
    new_value: str | None,
    dataset_key: str | None = None,
    details: dict[str, Any] | None = None,
    revision_id: str | None = None,
) -> None:
    db.add(
        LegacyIssueRecordHistory(
            id=new_id(),
            workspace_id=workspace.id,
            record_kind=record_kind,
            dataset_key=dataset_key,
            record_id=record_id,
            action=action,
            field_key="attachment",
            field_label=field_label,
            old_value=normalize_history_value(old_value),
            new_value=normalize_history_value(new_value),
            actor_user_id=user.id if user else None,
            details=_history_details(details=details, revision_id=revision_id),
        )
    )


def list_record_history(
    db: Session,
    *,
    workspace: Workspace,
    record_kind: str,
    record_id: str | None = None,
    record_ids: Iterable[str] | None = None,
    dataset_key: str | None = None,
) -> list[LegacyIssueRecordHistory]:
    normalized_ids = {item for item in (record_ids or []) if item}
    if record_id:
        normalized_ids.add(record_id)
    if not normalized_ids:
        return []
    statement = (
        select(LegacyIssueRecordHistory)
        .options(selectinload(LegacyIssueRecordHistory.actor))
        .where(
            LegacyIssueRecordHistory.workspace_id == workspace.id,
            LegacyIssueRecordHistory.record_kind == record_kind,
            LegacyIssueRecordHistory.record_id.in_(normalized_ids),
        )
    )
    if dataset_key is not None:
        statement = statement.where(LegacyIssueRecordHistory.dataset_key == dataset_key)
    return list(db.scalars(statement.order_by(LegacyIssueRecordHistory.created_at.desc())))


def normalize_history_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [normalize_history_value(item) for item in value]
        text = "; ".join(part for part in parts if part)
        return text or None
    if isinstance(value, dict):
        for key in ("label", "name", "path", "email", "id"):
            text = normalize_history_value(value.get(key))
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _history_details(*, details: dict[str, Any] | None, revision_id: str | None) -> dict[str, Any] | None:
    if revision_id is None:
        return details
    merged = dict(details or {})
    merged["revision_id"] = revision_id
    return merged
