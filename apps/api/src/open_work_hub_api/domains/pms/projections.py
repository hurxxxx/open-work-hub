from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.pms.workflow import priority_label, status_label, task_progress


def task_reference(task: Any) -> str:
    return f"{task.task_list.key}-{task.task_number}"


def task_assignee_ids(task: Any) -> list[str]:
    ids = [link.user_id for link in getattr(task, "assignee_links", [])]
    if not ids and getattr(task, "assignee_id", None):
        ids.append(task.assignee_id)
    return ids


def task_follower_ids(task: Any) -> list[str]:
    return [link.user_id for link in getattr(task, "follower_links", [])]


def serialize_task_labels(task: Any) -> list[dict[str, str]]:
    return [
        {
            "id": link.label.id,
            "name": link.label.name,
            "color": link.label.color,
        }
        for link in task.label_links
    ]


def serialize_task_summary(task: Any) -> dict[str, Any]:
    assignee_ids = task_assignee_ids(task)
    assignee_names = [
        getattr(link.user, "full_name", "") for link in getattr(task, "assignee_links", [])
    ]
    if not assignee_names and task.assignee_id:
        assignee_names = [getattr(task.assignee, "full_name", "") or task.assignee_id]
    follower_ids = task_follower_ids(task)
    return {
        "id": task.id,
        "list_id": task.list_id,
        "reference": task_reference(task),
        "title": task.title,
        "description": task.description,
        "description_blocks": task.description_blocks,
        "parent_id": task.parent_id,
        "subtask_count": len(task.subtasks) if task.subtasks else 0,
        "status": task.status,
        "status_label": status_label(task.status, task.task_list),
        "priority": task.priority,
        "priority_label": priority_label(task.priority),
        "assignee_id": task.assignee_id,
        "assignee_name": getattr(task.assignee, "full_name", None),
        "assignee_ids": assignee_ids,
        "assignee_names": assignee_names,
        "follower_ids": follower_ids,
        "follower_names": [
            getattr(link.user, "full_name", "") for link in getattr(task, "follower_links", [])
        ],
        "reporter_id": task.reporter_id,
        "reporter_name": task.reporter.full_name,
        "milestone_id": task.milestone_id,
        "milestone_title": getattr(task.milestone, "title", None),
        "start_date": task.start_date,
        "due_date": task.due_date,
        "completed_date": task.completed_date,
        "board_position": task.board_position,
        "archived": task.archived,
        "progress": task_progress(task.status, task.task_list),
        "comments_count": len(task.comments),
        "checklist_total": len(task.checklist_items) if task.checklist_items else 0,
        "checklist_done": sum(1 for item in task.checklist_items if item.completed)
        if task.checklist_items
        else 0,
        "recurrence_rule": task.recurrence_rule,
        "labels": serialize_task_labels(task),
        "updated_at": task.updated_at,
    }
