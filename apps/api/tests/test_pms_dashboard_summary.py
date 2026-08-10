from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from open_alm_api.domains.pms.dashboard_summary import dashboard_summary_payload


def task(
    title: str,
    *,
    status: str,
    priority: str = "medium",
    due_date: date | None = None,
    assignee_id: str | None = None,
    archived: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"task-{title}",
        title=title,
        task_number=1,
        status=status,
        priority=priority,
        due_date=due_date,
        assignee_id=assignee_id,
        archived=archived,
        task_list=None,
    )


def task_list(
    list_id: str,
    tasks: list[SimpleNamespace],
    *,
    milestones: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    item = SimpleNamespace(
        id=list_id,
        key=list_id.upper(),
        name=f"List {list_id}",
        status_mode="custom",
        team_id=None,
        statuses=[],
        space_statuses=[],
        tasks=tasks,
        milestones=milestones or [],
    )
    for task_item in tasks:
        task_item.task_list = item
    return item


def test_dashboard_summary_counts_active_overdue_owner_and_milestones() -> None:
    today = date(2026, 5, 30)
    todo = task(
        "todo",
        status="todo",
        priority="high",
        due_date=date(2026, 5, 29),
        assignee_id="user-1",
    )
    done = task(
        "done",
        status="done",
        priority="low",
        due_date=date(2026, 5, 1),
        assignee_id="user-1",
    )
    archived = task("archived", status="todo", archived=True)
    item = task_list(
        "alpha",
        [todo, done, archived],
        milestones=[
            SimpleNamespace(due_date=date(2026, 6, 10)),
            SimpleNamespace(due_date=date(2026, 7, 1)),
            SimpleNamespace(due_date=None),
        ],
    )

    payload = dashboard_summary_payload(
        task_lists=[item],
        recent_logs=[],
        current_user_id="user-1",
        today=today,
    )

    assert payload["list_count"] == 1
    assert payload["active_task_count"] == 1
    assert payload["overdue_task_count"] == 1
    assert payload["my_task_count"] == 1
    assert payload["milestone_due_soon_count"] == 1
    assert payload["status_counts"] == [
        {"status": "done", "label": "Done", "count": 1},
        {"status": "todo", "label": "Todo", "count": 1},
    ]
    assert payload["priority_counts"] == [
        {"priority": "low", "label": "Low", "count": 1},
        {"priority": "medium", "label": "Medium", "count": 0},
        {"priority": "high", "label": "High", "count": 1},
        {"priority": "critical", "label": "Critical", "count": 0},
    ]


def test_dashboard_summary_projects_list_cards_and_recent_activity() -> None:
    today = date(2026, 5, 30)
    next_task = task("next", status="in_progress", due_date=date(2026, 6, 1))
    overdue = task("late", status="todo", due_date=date(2026, 5, 29))
    completed = task("done", status="done", due_date=date(2026, 5, 20))
    item = task_list("beta", [next_task, overdue, completed])
    log = SimpleNamespace(
        id="log-1",
        task_id=next_task.id,
        task=next_task,
        message="Updated task",
        actor=SimpleNamespace(full_name="Ada"),
        created_at=datetime(2026, 5, 30, 9, 0, 0),
    )

    payload = dashboard_summary_payload(
        task_lists=[item],
        recent_logs=[log],
        current_user_id="user-1",
        today=today,
    )

    assert payload["lists"] == [
        {
            "list_id": "beta",
            "key": "BETA",
            "name": "List beta",
            "progress": 0.5,
            "open_task_count": 2,
            "overdue_task_count": 1,
            "next_due_date": date(2026, 5, 29),
        }
    ]
    assert payload["recent_activity"] == [
        {
            "id": "log-1",
            "task_id": "task-next",
            "task_reference": "BETA-1",
            "message": "Updated task",
            "actor_name": "Ada",
            "created_at": datetime(2026, 5, 30, 9, 0, 0),
        }
    ]
