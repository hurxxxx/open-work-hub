from __future__ import annotations

from collections.abc import Iterable
from typing import Any


TASK_STATUS_LABELS = {
    "todo": "Todo",
    "in_progress": "In Progress",
    "review": "Review",
    "done": "Done",
    "canceled": "Canceled",
    "complete": "Complete",
}

TASK_STATUS_PROGRESS = {
    "todo": 0.0,
    "in_progress": 0.5,
    "review": 0.75,
    "done": 1.0,
    "canceled": None,
    "complete": None,
}

PRIORITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}

CATEGORY_PROGRESS = {
    "not_started": 0.0,
    "active": 0.5,
    "done": 1.0,
    "closed": None,
}


def normalize_task_status(status_value: str) -> str:
    return "todo" if status_value == "backlog" else status_value


def normalize_status_category(category: str) -> str:
    return "closed" if category == "canceled" else category


def status_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_")[:40]


def status_definitions(task_list: Any | None) -> list[Any]:
    if task_list is None:
        return []
    if task_list.status_mode == "inherit" and task_list.team_id:
        return list(getattr(task_list, "space_statuses", []) or [])
    return list(getattr(task_list, "statuses", []) or [])


def status_label(status_value: str, task_list: Any | None = None) -> str:
    for list_status in status_definitions(task_list):
        if list_status.slug == status_value:
            return list_status.name
    return TASK_STATUS_LABELS.get(status_value, status_value.replace("_", " ").title())


def status_category(status_value: str, task_list: Any | None = None) -> str | None:
    if status_value == "todo":
        return "not_started"
    if status_value == "in_progress":
        return "active"
    if status_value == "done":
        return "done"
    if status_value in {"canceled", "closed", "complete"}:
        return "closed"
    for list_status in status_definitions(task_list):
        if list_status.slug == status_value:
            return normalize_status_category(list_status.category)
    return None


def task_progress(status_value: str, task_list: Any | None = None) -> float | None:
    result = TASK_STATUS_PROGRESS.get(status_value)
    if result is not None or status_value in TASK_STATUS_PROGRESS:
        return result
    category = status_category(status_value, task_list)
    if category:
        return CATEGORY_PROGRESS.get(category, 0.5)
    return 0.5


def is_closed_status(status_value: str, task_list: Any | None = None) -> bool:
    return status_category(status_value, task_list) == "closed"


def closed_status_count(
    statuses: list[Any],
    *,
    exclude_id: str | None = None,
) -> int:
    return sum(
        1
        for item in statuses
        if item.id != exclude_id and normalize_status_category(item.category) == "closed"
    )


def violates_single_closed_status_rule(
    statuses: list[Any],
    *,
    next_category: str,
    exclude_id: str | None = None,
) -> bool:
    return (
        normalize_status_category(next_category) == "closed"
        and closed_status_count(statuses, exclude_id=exclude_id) > 0
    )


def incompatible_statuses_for_inherit(
    used_statuses: Iterable[str],
    allowed_status_slugs: Iterable[str],
) -> list[str]:
    allowed = set(allowed_status_slugs)
    return sorted({status for status in used_statuses if status not in allowed})


def is_done_status(status_value: str, task_list: Any | None = None) -> bool:
    return status_category(status_value, task_list) == "done"


def is_completion_status(status_value: str, task_list: Any | None = None) -> bool:
    return status_category(status_value, task_list) in {"done", "closed"}


def is_overdue_exempt_status(status_value: str, task_list: Any | None = None) -> bool:
    return is_completion_status(status_value, task_list)


def calculate_progress(tasks: list[Any], task_list: Any | None = None) -> float:
    progress_values = [
        progress
        for task in tasks
        if not task.archived
        for progress in [task_progress(task.status, task_list)]
        if progress is not None
    ]
    if not progress_values:
        return 0.0
    return round(sum(progress_values) / len(progress_values), 2)


def priority_label(priority: str) -> str:
    return PRIORITY_LABELS.get(priority, priority.replace("_", " ").title())
