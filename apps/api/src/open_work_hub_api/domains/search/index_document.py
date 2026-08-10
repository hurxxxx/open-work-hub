from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from open_work_hub_api.domains.search.target_keys import search_target_document_keys


def document_id(document: dict[str, Any]) -> str:
    return f"{document['workspace_id']}:{document['entity_type']}:{document['entity_id']}"


def build_search_document(
    *,
    workspace_id: str,
    entity_type: object,
    entity_id: str,
    title: str,
    summary: str,
    body: str,
    keywords: str,
    status: str | None,
    status_label: str | None,
    visibility: str | None,
    people: list[dict[str, str]],
    targets: list[dict[str, str]],
    owner_user_id: str | None,
    team_ids: list[str],
    participant_user_ids: list[str],
    shared_user_ids: list[str],
    granted_user_ids: list[str],
    date_markers: dict[str, Any],
    deep_link: str,
    metadata: dict[str, Any],
    source_updated_at: datetime,
) -> dict[str, Any]:
    search_text = _weighted_search_text(title=title, keywords=keywords, summary=summary, body=body)
    return {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "dataset_id": _metadata_dataset_id(metadata),
        "entity_type": str(entity_type),
        "entity_id": entity_id,
        "title": title or "Untitled",
        "summary": summary or "",
        "body": body or "",
        "keywords": keywords or "",
        "search_text": search_text,
        "status": status,
        "status_label": status_label,
        "visibility": visibility,
        "owner_user_id": owner_user_id,
        "team_ids": _unique_nonempty(team_ids),
        "participant_user_ids": _unique_nonempty(participant_user_ids),
        "shared_user_ids": _unique_nonempty(shared_user_ids),
        "granted_user_ids": _unique_nonempty(granted_user_ids),
        "people": [person for person in people if person["user_id"]],
        "targets": targets,
        "target_keys": _target_keys(targets),
        "date_markers": {key: value for key, value in date_markers.items() if value is not None},
        "deep_link": deep_link,
        "preview_url": None,
        "metadata": metadata,
        "rank_boost": 0.0,
        "source_updated_at": source_updated_at.isoformat(),
        "created_at": source_updated_at.isoformat(),
    }


def search_person(role: str, user_id: str | None, label: str | None) -> dict[str, str]:
    return {"role": role, "user_id": user_id or "", "label": label or "Unknown"}


def trim_search_text(value: str | None, max_chars: int) -> str:
    normalized = " ".join((value or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        _collect_text_parts(block, parts)
    return " ".join(parts)


def _unique_nonempty(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _target_keys(targets: list[dict[str, str]]) -> list[str]:
    return list(
        dict.fromkeys(
            key
            for target in targets
            for key in search_target_document_keys(target)
        )
    )


def _metadata_dataset_id(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("dataset_id")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value.strip():
            parts.append(" ".join(text_value.split()))
        for key in ("content", "children"):
            if key in value:
                _collect_text_parts(value[key], parts)


def _weighted_search_text(*, title: str, keywords: str, summary: str, body: str) -> str:
    # Repeat higher-signal fields so ngram scoring still favors object titles.
    return " ".join(
        part
        for part in [
            title,
            title,
            title,
            title,
            title,
            keywords,
            keywords,
            keywords,
            summary,
            summary,
            body,
        ]
        if part
    )
