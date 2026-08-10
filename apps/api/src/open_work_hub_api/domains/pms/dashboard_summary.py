from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from open_work_hub_api.domains.pms.projections import task_reference
from open_work_hub_api.domains.pms.workflow import (
    PRIORITY_LABELS,
    calculate_progress,
    is_overdue_exempt_status,
    priority_label,
    status_label,
)


def active_dashboard_tasks(task_lists: list[Any]) -> list[Any]:
    return [
        task
        for task_list in task_lists
        for task in task_list.tasks
        if not task.archived
        and not is_overdue_exempt_status(task.status, task.task_list)
    ]


def overdue_dashboard_tasks(tasks: list[Any], *, today: date) -> list[Any]:
    return [
        task
        for task in tasks
        if task.due_date is not None and task.due_date < today
    ]


def milestone_due_soon_count(task_lists: list[Any], *, today: date) -> int:
    due_by = today + timedelta(days=14)
    return sum(
        1
        for task_list in task_lists
        for milestone in task_list.milestones
        if milestone.due_date is not None and milestone.due_date <= due_by
    )


def status_count_payloads(task_lists: list[Any]) -> list[dict[str, Any]]:
    tasks = [
        task
        for task_list in task_lists
        for task in task_list.tasks
        if not task.archived
    ]
    status_labels = {task.status: status_label(task.status, task.task_list) for task in tasks}
    return [
        {
            "status": status_key,
            "label": status_labels[status_key],
            "count": sum(1 for task in tasks if task.status == status_key),
        }
        for status_key in sorted(status_labels)
    ]


def priority_count_payloads(task_lists: list[Any]) -> list[dict[str, Any]]:
    tasks = [
        task
        for task_list in task_lists
        for task in task_list.tasks
        if not task.archived
    ]
    return [
        {
            "priority": priority_key,
            "label": priority_label(priority_key),
            "count": sum(1 for task in tasks if task.priority == priority_key),
        }
        for priority_key in PRIORITY_LABELS
    ]


def dashboard_task_list_payload(task_list: Any, *, today: date) -> dict[str, Any]:
    task_progress_scope = [task for task in task_list.tasks if not task.archived]
    open_task_count = sum(
        1
        for task in task_progress_scope
        if not is_overdue_exempt_status(task.status, task_list)
    )
    overdue_task_count = sum(
        1
        for task in task_progress_scope
        if not is_overdue_exempt_status(task.status, task_list)
        and task.due_date is not None
        and task.due_date < today
    )
    due_dates = sorted(
        task.due_date
        for task in task_progress_scope
        if task.due_date is not None
        and not is_overdue_exempt_status(task.status, task_list)
    )
    return {
        "list_id": task_list.id,
        "key": task_list.key,
        "name": task_list.name,
        "progress": calculate_progress(task_progress_scope, task_list),
        "open_task_count": open_task_count,
        "overdue_task_count": overdue_task_count,
        "next_due_date": due_dates[0] if due_dates else None,
    }


def recent_activity_payload(log: Any) -> dict[str, Any]:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "task_reference": task_reference(log.task),
        "message": log.message,
        "actor_name": getattr(log.actor, "full_name", None),
        "created_at": log.created_at,
    }


def dashboard_summary_payload(
    *,
    task_lists: list[Any],
    recent_logs: list[Any],
    current_user_id: str,
    today: date,
) -> dict[str, Any]:
    active_tasks = active_dashboard_tasks(task_lists)
    overdue_tasks = overdue_dashboard_tasks(active_tasks, today=today)
    return {
        "list_count": len(task_lists),
        "active_task_count": len(active_tasks),
        "overdue_task_count": len(overdue_tasks),
        "my_task_count": sum(
            1 for task in active_tasks if task.assignee_id == current_user_id
        ),
        "milestone_due_soon_count": milestone_due_soon_count(
            task_lists,
            today=today,
        ),
        "status_counts": status_count_payloads(task_lists),
        "priority_counts": priority_count_payloads(task_lists),
        "lists": [
            dashboard_task_list_payload(task_list, today=today)
            for task_list in task_lists
        ],
        "recent_activity": [recent_activity_payload(log) for log in recent_logs],
    }
