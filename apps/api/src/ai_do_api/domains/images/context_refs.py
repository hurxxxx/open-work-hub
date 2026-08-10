"""Pure snapshot helpers for image generation context references."""

from __future__ import annotations

from typing import Any


VALID_CONTEXT_REF_KINDS: tuple[str, ...] = ("meeting", "task", "doc")
DOC_CONTEXT_PAGE_LIMIT = 5
TASK_LIST_CONTEXT_TASK_LIMIT = 15
DOC_CONTEXT_TEXT_MAX_CHARS = 1500


def normalize_context_ref(raw_ref: Any) -> tuple[str, str] | None:
    if not isinstance(raw_ref, dict):
        return None
    kind = str(raw_ref.get("kind") or "").lower()
    ref_id = str(raw_ref.get("id") or "")
    if kind not in VALID_CONTEXT_REF_KINDS or not ref_id:
        return None
    return kind, ref_id


def flatten_doc_text(pages: list[Any], *, max_chars: int = DOC_CONTEXT_TEXT_MAX_CHARS) -> str:
    """Flatten block doc pages into plain text up to ``max_chars``."""

    parts: list[str] = []
    used = 0
    for page in pages:
        title = (getattr(page, "title", "") or "").strip()
        if title:
            parts.append(title)
            used += len(title) + 1
        for block in getattr(page, "content_blocks", None) or []:
            if not isinstance(block, dict):
                continue
            content = block.get("content")
            if not isinstance(content, list):
                continue
            for piece in content:
                if not isinstance(piece, dict):
                    continue
                text = piece.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                    used += len(text) + 1
                    if used >= max_chars:
                        return "\n".join(parts)[:max_chars]
    return "\n".join(parts)[:max_chars]


def meeting_snapshot(meeting: Any) -> dict[str, Any]:
    return {
        "title": meeting.title,
        "agenda": meeting.agenda,
        "summary": meeting.agenda,
    }


def doc_page_snapshot(doc: Any, pages: list[Any]) -> dict[str, Any]:
    return {
        "title": doc.title,
        "body": flatten_doc_text(pages),
    }


def task_list_snapshot(task_list: Any, tasks: list[Any]) -> dict[str, Any]:
    return {
        "title": task_list.name,
        "description": task_list.description,
        "status": task_list.status,
        "tasks": [f"[{task.status}] {task.title}" for task in tasks],
    }


def task_snapshot(task: Any) -> dict[str, Any]:
    return {
        "title": task.title,
        "status": task.status,
        "description": task.description,
    }


def merge_user_context_snapshot(
    snapshot: dict[str, Any],
    raw_ref: Any,
) -> dict[str, Any]:
    """Keep service-built snapshots, filling missing title/summary from user input."""

    if not isinstance(raw_ref, dict):
        return snapshot
    user_snapshot = raw_ref.get("snapshot") or {}
    if not isinstance(user_snapshot, dict):
        return snapshot
    for key in ("title", "summary"):
        value = user_snapshot.get(key)
        if isinstance(value, str) and value.strip() and not snapshot.get(key):
            snapshot[key] = value.strip()
    return snapshot


def hydrated_context_ref(
    *,
    kind: str,
    ref_id: str,
    snapshot: dict[str, Any],
    raw_ref: Any,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": ref_id,
        "snapshot": merge_user_context_snapshot(snapshot, raw_ref),
    }
