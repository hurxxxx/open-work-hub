from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.patent_automation.models import PatentRecordHistory


@dataclass(frozen=True)
class PatentHistoryChange:
    field_key: str
    field_label: str
    old_value: str | None
    new_value: str | None


def collect_value_changes(
    *,
    old_values: Mapping[str, Any],
    new_values: Mapping[str, Any],
    field_labels: Mapping[str, str],
) -> list[PatentHistoryChange]:
    changes: list[PatentHistoryChange] = []
    for field_key, new_value in new_values.items():
        old_text = normalize_history_value(old_values.get(field_key))
        new_text = normalize_history_value(new_value)
        if old_text == new_text:
            continue
        changes.append(
            PatentHistoryChange(
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
) -> list[PatentHistoryChange]:
    changes: list[PatentHistoryChange] = []
    for field_key, value in values.items():
        value_text = normalize_history_value(value)
        if value_text is None:
            continue
        changes.append(
            PatentHistoryChange(
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
    record_id: str,
    action: str,
    changes: Iterable[PatentHistoryChange],
    details: dict[str, Any] | None = None,
    revision_id: str | None = None,
) -> None:
    entry_details = _history_details(details=details, revision_id=revision_id)
    for change in changes:
        db.add(
            PatentRecordHistory(
                id=new_id(),
                workspace_id=workspace.id,
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


def list_record_history(
    db: Session,
    *,
    workspace: Workspace,
    record_id: str | None = None,
    record_ids: Iterable[str] | None = None,
) -> list[PatentRecordHistory]:
    normalized_ids = {item for item in (record_ids or []) if item}
    if record_id:
        normalized_ids.add(record_id)
    if not normalized_ids:
        return []
    statement = (
        select(PatentRecordHistory)
        .options(selectinload(PatentRecordHistory.actor))
        .where(
            PatentRecordHistory.workspace_id == workspace.id,
            PatentRecordHistory.record_id.in_(normalized_ids),
        )
        .order_by(PatentRecordHistory.created_at.desc())
    )
    return list(db.scalars(statement))


def normalize_history_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _history_details(
    *, details: dict[str, Any] | None, revision_id: str | None
) -> dict[str, Any] | None:
    if revision_id is None:
        return details
    merged = dict(details or {})
    merged["revision_id"] = revision_id
    return merged
