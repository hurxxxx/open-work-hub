"""set legacy issue occurrence date field type

Revision ID: e2b8d0f4a6c9
Revises: d1a7c9e3f5b8
Create Date: 2026-07-24 16:30:00.000000
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import json
import re
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2b8d0f4a6c9"
down_revision: str | Sequence[str] | None = "d1a7c9e3f5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DATASET_KEY = "common-master"
REVISION_DATASET_PREFIX = "legacy_issue.common-master"
OCCURRENCE_DATE_FIELD_KEY = "occurrence_date"
DEFAULT_OCCURRENCE_DATE_LABELS = ("발생일", "Occurrence Date")
SNAPSHOT_TABLE_NAMES = (
    "legacy_issue_vehicle_checklist_revisions",
    "legacy_issue_vehicle_module_checklists",
)
CHECKLIST_RECORD_TABLE_NAMES = (
    "legacy_issue_vehicle_checklist_records",
    "legacy_issue_vehicle_module_checklist_records",
)
WRITE_LOCK_TABLE_NAMES = (
    "legacy_issue_data_revisions",
    "legacy_issue_records",
    "legacy_issue_ai_chunks",
    "legacy_issue_system_field_settings",
    "legacy_issue_vehicle_checklist_revisions",
    "legacy_issue_vehicle_checklist_records",
    "legacy_issue_vehicle_module_checklists",
    "legacy_issue_vehicle_module_checklist_records",
)
SUPPORTED_TWO_DIGIT_YEARS = {
    25: 2025,
    26: 2026,
}
_TWO_DIGIT_DATE = re.compile(r"^(?P<year>[0-9]{2})[.](?P<month>[0-9]{1,2})[.](?P<day>[0-9]{1,2})$")
_FOUR_DIGIT_DATE = re.compile(
    r"^(?P<year>[0-9]{4})[-./](?P<month>[0-9]{1,2})[-./](?P<day>[0-9]{1,2})$"
)
_SEARCH_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./+-]*|[가-힣]+")
_MAX_SEARCH_TERMS = 512


def _lock_migration_write_tables() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    bind.execute(
        sa.text("LOCK TABLE " + ", ".join(WRITE_LOCK_TABLE_NAMES) + " IN SHARE ROW EXCLUSIVE MODE")
    )


def _updated_definition_snapshot(
    snapshot: Any,
    *,
    field_type: str,
) -> tuple[Any, bool]:
    if not isinstance(snapshot, dict):
        return snapshot, False
    fields = snapshot.get("fields")
    if not isinstance(fields, list):
        return snapshot, False

    changed = False
    next_fields: list[Any] = []
    for field in fields:
        if not isinstance(field, dict) or field.get("key") != OCCURRENCE_DATE_FIELD_KEY:
            next_fields.append(field)
            continue
        next_field = dict(field)
        if next_field.get("field_type") != field_type:
            next_field["field_type"] = field_type
            changed = True
        next_fields.append(next_field)

    if not changed:
        return snapshot, False
    next_snapshot = dict(snapshot)
    next_snapshot["fields"] = next_fields
    return next_snapshot, True


def _rewrite_snapshot_tables(*, field_type: str) -> None:
    bind = op.get_bind()
    for table_name in SNAPSHOT_TABLE_NAMES:
        table = sa.table(
            table_name,
            sa.column("id", sa.String()),
            sa.column("definition_snapshot", postgresql.JSONB(astext_type=sa.Text())),
        )
        rows = bind.execute(sa.select(table.c.id, table.c.definition_snapshot)).mappings()
        for row in rows:
            next_snapshot, changed = _updated_definition_snapshot(
                row["definition_snapshot"],
                field_type=field_type,
            )
            if not changed:
                continue
            bind.execute(
                table.update()
                .where(table.c.id == row["id"])
                .values(definition_snapshot=next_snapshot)
            )


def _rewrite_system_field_settings(*, field_type: str) -> None:
    settings = sa.table(
        "legacy_issue_system_field_settings",
        sa.column("dataset_key", sa.String()),
        sa.column("field_key", sa.String()),
        sa.column("field_type", sa.String()),
    )
    op.get_bind().execute(
        settings.update()
        .where(
            settings.c.dataset_key == DATASET_KEY,
            settings.c.field_key == OCCURRENCE_DATE_FIELD_KEY,
        )
        .values(field_type=field_type)
    )


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _normalized_occurrence_date(value: Any, *, record_id: str) -> str | None:
    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value or raw_value == "-":
        return None

    if len(raw_value) == 8 and raw_value.isdigit():
        parts = (int(raw_value[0:4]), int(raw_value[4:6]), int(raw_value[6:8]))
    elif match := _TWO_DIGIT_DATE.fullmatch(raw_value):
        short_year = int(match.group("year"))
        if short_year not in SUPPORTED_TWO_DIGIT_YEARS:
            raise RuntimeError(
                "Unsupported two-digit occurrence_date year in a non-canceled "
                f"legacy-issue record (record_id={record_id}, value={raw_value!r})."
            )
        parts = (
            SUPPORTED_TWO_DIGIT_YEARS[short_year],
            int(match.group("month")),
            int(match.group("day")),
        )
    elif match := _FOUR_DIGIT_DATE.fullmatch(raw_value):
        parts = (
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    else:
        raise RuntimeError(
            "Unsupported occurrence_date in a non-canceled legacy-issue record "
            f"(record_id={record_id}, value={raw_value!r})."
        )

    try:
        return date(*parts).isoformat()
    except ValueError as error:
        raise RuntimeError(
            "Invalid occurrence_date in a non-canceled legacy-issue record "
            f"(record_id={record_id}, value={raw_value!r})."
        ) from error


def _non_canceled_revision_ids() -> set[str]:
    revisions = sa.table(
        "legacy_issue_data_revisions",
        sa.column("id", sa.String()),
        sa.column("dataset_key", sa.String()),
        sa.column("status", sa.String()),
    )
    rows = (
        op.get_bind()
        .execute(
            sa.select(revisions.c.id, revisions.c.dataset_key)
            .where(
                revisions.c.status.in_(("draft", "published")),
                sa.or_(
                    revisions.c.dataset_key == REVISION_DATASET_PREFIX,
                    revisions.c.dataset_key.like(f"{REVISION_DATASET_PREFIX}.%"),
                ),
            )
            .with_for_update()
        )
        .mappings()
    )
    return {
        str(row["id"])
        for row in rows
        if (
            str(row["dataset_key"] or "") == REVISION_DATASET_PREFIX
            or str(row["dataset_key"] or "").startswith(f"{REVISION_DATASET_PREFIX}.")
        )
    }


def _occurrence_date_labels_by_workspace() -> dict[str, set[str]]:
    settings = sa.table(
        "legacy_issue_system_field_settings",
        sa.column("workspace_id", sa.String()),
        sa.column("dataset_key", sa.String()),
        sa.column("field_key", sa.String()),
        sa.column("label_ko", sa.String()),
    )
    labels_by_workspace: dict[str, set[str]] = {}
    rows = (
        op.get_bind()
        .execute(
            sa.select(settings.c.workspace_id, settings.c.label_ko).where(
                settings.c.dataset_key == DATASET_KEY,
                settings.c.field_key == OCCURRENCE_DATE_FIELD_KEY,
            )
        )
        .mappings()
    )
    for row in rows:
        label = str(row["label_ko"] or "").strip()
        if label:
            labels_by_workspace.setdefault(str(row["workspace_id"]), set()).add(label)
    return labels_by_workspace


def _rewritten_record_search_text(
    search_text: Any,
    *,
    old_value: str | None,
    new_value: str | None,
    labels: set[str],
) -> str | None:
    if not search_text:
        return None
    text = str(search_text)
    if not old_value:
        return text

    rewritten: list[str] = []
    targets = {f"{label}: {old_value}" for label in labels if label}
    for line in text.splitlines():
        if line not in targets:
            rewritten.append(line)
            continue
        if new_value:
            rewritten.append(line[: -len(old_value)] + new_value)

    result = "\n".join(rewritten) or None
    return result


def _rewritten_chunk_search_text(
    search_text: Any,
    *,
    old_value: str | None,
    new_value: str | None,
    labels: set[str],
    chunk_id: str,
) -> str:
    if not search_text:
        return ""
    text = str(search_text)
    if not old_value:
        return text

    matches: set[tuple[int, int]] = set()
    for label in labels:
        normalized_label = " ".join(label.split())
        if not normalized_label:
            continue
        pattern = re.compile(
            rf"(?<!\S){re.escape(normalized_label)}:\s+"
            rf"{re.escape(old_value)}(?=\s|$)"
        )
        matches.update((match.start(), match.end()) for match in pattern.finditer(text))

    # A custom label may contain a default label (for example, "전체 발생일").
    # Prefer the widest match ending at the same value instead of treating the
    # overlapping label aliases as separate occurrence-date fields.
    maximal_matches = {
        candidate
        for candidate in matches
        if not any(
            other != candidate and other[0] <= candidate[0] and other[1] >= candidate[1]
            for other in matches
        )
    }
    if not maximal_matches:
        return text
    if len(maximal_matches) != 1:
        raise RuntimeError(
            "Ambiguous occurrence_date label in a legacy-issue AI chunk "
            f"(chunk_id={chunk_id}, value={old_value!r})."
        )

    start, end = maximal_matches.pop()
    if new_value is not None:
        value_start = end - len(old_value)
        return text[:value_start] + new_value + text[end:]
    return re.sub(r"\s+", " ", text[:start] + text[end:]).strip()


def _search_terms(search_text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        normalized = value.casefold().strip()
        if len(normalized) < 2 or len(normalized) > 80 or normalized in seen:
            return
        seen.add(normalized)
        terms.append(normalized)

    for match in _SEARCH_TOKEN.finditer(search_text):
        token = match.group(0).casefold()
        add(token)
        if any("가" <= char <= "힣" for char in token):
            compact = re.sub(r"\s+", "", token)
            for size in (2, 3):
                if len(compact) >= size:
                    for index in range(0, len(compact) - size + 1):
                        add(compact[index : index + size])
        elif len(token) > 4:
            for part in re.split(r"[./+-]+", token):
                add(part)
    return terms[:_MAX_SEARCH_TERMS]


def _patched_search_terms(
    existing_terms: Any,
    *,
    old_search_text: str,
    new_search_text: str,
) -> list[str]:
    if not isinstance(existing_terms, list):
        return _search_terms(new_search_text)

    existing = [str(term) for term in existing_terms if str(term)]
    if old_search_text == new_search_text:
        return existing

    old_visible_terms = _search_terms(old_search_text)
    old_visible_term_set = set(old_visible_terms)
    new_visible_terms = _search_terms(new_search_text)
    new_visible_term_set = set(new_visible_terms)
    removed = old_visible_term_set - new_visible_term_set
    added = [term for term in new_visible_terms if term not in old_visible_term_set]
    first_removed_index = next(
        (index for index, term in enumerate(existing) if term in removed),
        len(existing),
    )
    insertion_index = sum(1 for term in existing[:first_removed_index] if term not in removed)
    retained = [term for term in existing if term not in removed]
    candidates = [
        *retained[:insertion_index],
        *added,
        *retained[insertion_index:],
    ]

    patched: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        normalized = term.casefold().strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        patched.append(normalized)
        if len(patched) >= _MAX_SEARCH_TERMS:
            break
    return patched


def _normalize_record_ai_chunks(
    changes: dict[str, tuple[str | None, str | None, set[str]]],
) -> None:
    if not changes:
        return
    chunks = sa.table(
        "legacy_issue_ai_chunks",
        sa.column("id", sa.String()),
        sa.column("record_id", sa.String()),
        sa.column("attachment_id", sa.String()),
        sa.column("chunk_key", sa.String()),
        sa.column("field_key", sa.String()),
        sa.column("field_value", sa.Text()),
        sa.column("search_text", sa.Text()),
        sa.column("search_terms", postgresql.JSONB(astext_type=sa.Text())),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            chunks.c.id,
            chunks.c.record_id,
            chunks.c.chunk_key,
            chunks.c.field_key,
            chunks.c.field_value,
            chunks.c.search_text,
            chunks.c.search_terms,
        ).where(
            chunks.c.record_id.in_(changes),
            chunks.c.attachment_id.is_(None),
            sa.or_(
                chunks.c.chunk_key == "summary",
                chunks.c.field_key == OCCURRENCE_DATE_FIELD_KEY,
            ),
        )
    ).mappings()
    for row in rows:
        old_value, new_value, labels = changes[str(row["record_id"])]
        if row["field_key"] == OCCURRENCE_DATE_FIELD_KEY and new_value is None:
            bind.execute(chunks.delete().where(chunks.c.id == row["id"]))
            continue
        next_search_text = _rewritten_chunk_search_text(
            row["search_text"],
            old_value=old_value,
            new_value=new_value,
            labels=labels,
            chunk_id=str(row["id"]),
        )
        next_field_value = (
            new_value if row["field_key"] == OCCURRENCE_DATE_FIELD_KEY else row["field_value"]
        )
        # Runtime summaries store at most 8,000 characters in search_text but
        # build search_terms from the full untruncated record. Rebuild the
        # visible prefix and retain terms that only existed beyond that prefix.
        next_search_terms = _patched_search_terms(
            row["search_terms"],
            old_search_text=str(row["search_text"] or ""),
            new_search_text=next_search_text,
        )
        if (
            row["field_value"] == next_field_value
            and row["search_text"] == next_search_text
            and row["search_terms"] == next_search_terms
        ):
            continue
        bind.execute(
            chunks.update()
            .where(chunks.c.id == row["id"])
            .values(
                field_value=next_field_value,
                search_text=next_search_text or "",
                search_terms=next_search_terms,
            )
        )


def _normalize_non_canceled_master_records() -> None:
    revision_ids = _non_canceled_revision_ids()
    if not revision_ids:
        return

    records = sa.table(
        "legacy_issue_records",
        sa.column("id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("revision_id", sa.String()),
        sa.column("field_values", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("occurrence_date", sa.Text()),
        sa.column("search_text", sa.Text()),
    )
    labels_by_workspace = _occurrence_date_labels_by_workspace()
    rows = (
        op.get_bind()
        .execute(
            sa.select(
                records.c.id,
                records.c.workspace_id,
                records.c.revision_id,
                records.c.field_values,
                records.c.occurrence_date,
                records.c.search_text,
            )
            .where(records.c.revision_id.in_(revision_ids))
            .with_for_update()
        )
        .mappings()
    )
    changed_records: dict[str, tuple[str | None, str | None, set[str]]] = {}
    for row in rows:
        values = _json_mapping(row["field_values"])
        has_json_value = OCCURRENCE_DATE_FIELD_KEY in values
        old_raw_value = values.get(OCCURRENCE_DATE_FIELD_KEY)
        source_value = old_raw_value if has_json_value else row["occurrence_date"]
        old_value = (
            str(old_raw_value).strip()
            if old_raw_value is not None
            else str(row["occurrence_date"] or "").strip() or None
        )
        normalized = _normalized_occurrence_date(
            source_value,
            record_id=str(row["id"]),
        )
        next_values = dict(values)
        if normalized is None:
            next_values.pop(OCCURRENCE_DATE_FIELD_KEY, None)
        else:
            next_values[OCCURRENCE_DATE_FIELD_KEY] = normalized
        labels = {
            *DEFAULT_OCCURRENCE_DATE_LABELS,
            *labels_by_workspace.get(str(row["workspace_id"]), set()),
        }
        next_search_text = _rewritten_record_search_text(
            row["search_text"],
            old_value=old_value,
            new_value=normalized,
            labels=labels,
        )
        if (
            next_values == values
            and row["occurrence_date"] == normalized
            and row["search_text"] == next_search_text
        ):
            continue
        op.get_bind().execute(
            records.update()
            .where(records.c.id == row["id"])
            .values(
                field_values=next_values,
                occurrence_date=normalized,
                search_text=next_search_text,
            )
        )
        changed_records[str(row["id"])] = (old_value, normalized, labels)

    _normalize_record_ai_chunks(changed_records)


def _normalize_checklist_records() -> None:
    bind = op.get_bind()
    for table_name in CHECKLIST_RECORD_TABLE_NAMES:
        records = sa.table(
            table_name,
            sa.column("id", sa.String()),
            sa.column("field_values", postgresql.JSONB(astext_type=sa.Text())),
        )
        rows = bind.execute(
            sa.select(records.c.id, records.c.field_values).with_for_update()
        ).mappings()
        for row in rows:
            values = _json_mapping(row["field_values"])
            normalized = _normalized_occurrence_date(
                values.get(OCCURRENCE_DATE_FIELD_KEY),
                record_id=str(row["id"]),
            )
            next_values = dict(values)
            if normalized is None:
                next_values.pop(OCCURRENCE_DATE_FIELD_KEY, None)
            else:
                next_values[OCCURRENCE_DATE_FIELD_KEY] = normalized
            if next_values == values:
                continue
            bind.execute(
                records.update().where(records.c.id == row["id"]).values(field_values=next_values)
            )


def upgrade() -> None:
    _lock_migration_write_tables()
    _normalize_non_canceled_master_records()
    _normalize_checklist_records()
    _rewrite_system_field_settings(field_type="date")
    _rewrite_snapshot_tables(field_type="date")


def downgrade() -> None:
    _rewrite_system_field_settings(field_type="text")
    _rewrite_snapshot_tables(field_type="text")
