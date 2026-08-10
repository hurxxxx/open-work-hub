from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import SimpleNamespace

from open_alm_api.domains.pms.projections import serialize_task_summary
from open_alm_api.domains.pms.workflow import (
    calculate_progress,
    closed_status_count,
    incompatible_statuses_for_inherit,
    is_completion_status,
    is_done_status,
    is_overdue_exempt_status,
    normalize_task_status,
    priority_label,
    status_category,
    status_definitions,
    status_label,
    status_slug,
    task_progress,
    violates_single_closed_status_rule,
)


@dataclass
class StatusDefinition:
    slug: str
    name: str
    category: str
    id: str = "status-1"


@dataclass
class TaskListStub:
    status_mode: str = "custom"
    team_id: str | None = "space-1"
    statuses: list[StatusDefinition] = field(default_factory=list)
    space_statuses: list[StatusDefinition] = field(default_factory=list)


@dataclass
class TaskStub:
    status: str
    archived: bool = False


def test_pms_workflow_resolves_custom_and_inherited_statuses() -> None:
    task_list = TaskListStub(
        statuses=[StatusDefinition("qa", "QA Ready", "active")],
        space_statuses=[StatusDefinition("blocked", "Blocked", "canceled")],
    )
    inherited_list = TaskListStub(
        status_mode="inherit",
        space_statuses=[StatusDefinition("blocked", "Blocked", "canceled")],
    )

    assert status_definitions(task_list) == task_list.statuses
    assert status_definitions(inherited_list) == inherited_list.space_statuses
    assert status_label("qa", task_list) == "QA Ready"
    assert status_category("blocked", inherited_list) == "closed"
    assert is_completion_status("blocked", inherited_list) is True
    assert is_overdue_exempt_status("blocked", inherited_list) is True


def test_pms_workflow_progress_and_labels_cover_legacy_and_unknown_values() -> None:
    assert normalize_task_status("backlog") == "todo"
    assert task_progress("review") == 0.75
    assert task_progress("unknown") == 0.5
    assert is_done_status("done") is True
    assert priority_label("urgent_customer") == "Urgent Customer"


def test_pms_workflow_status_slug_and_single_closed_status_rule() -> None:
    statuses = [
        StatusDefinition("todo", "Todo", "not_started", id="open"),
        StatusDefinition("closed", "Closed", "closed", id="closed-1"),
        StatusDefinition("canceled", "Canceled", "canceled", id="legacy-canceled"),
    ]

    assert status_slug(" Ready For QA ") == "ready_for_qa"
    assert status_slug("x" * 80) == "x" * 40
    assert closed_status_count(statuses) == 2
    assert closed_status_count(statuses, exclude_id="closed-1") == 1
    assert violates_single_closed_status_rule(statuses, next_category="active") is False
    assert violates_single_closed_status_rule(statuses, next_category="closed") is True
    assert (
        violates_single_closed_status_rule(
            statuses,
            next_category="closed",
            exclude_id="closed-1",
        )
        is True
    )
    assert (
        violates_single_closed_status_rule(
            statuses,
            next_category="closed",
            exclude_id="legacy-canceled",
        )
        is True
    )
    assert (
        violates_single_closed_status_rule(
            [statuses[0], statuses[1]],
            next_category="closed",
            exclude_id="closed-1",
        )
        is False
    )


def test_pms_workflow_reports_incompatible_statuses_for_inherit_mode() -> None:
    assert incompatible_statuses_for_inherit(
        ["qa", "todo", "blocked", "qa"],
        ["todo", "done", "blocked"],
    ) == ["qa"]


def test_pms_workflow_calculates_progress_without_archived_or_closed_tasks() -> None:
    assert calculate_progress(
        [
            TaskStub("todo"),
            TaskStub("review"),
            TaskStub("done"),
            TaskStub("complete"),
            TaskStub("in_progress", archived=True),
        ],
    ) == 0.58


def test_pms_task_summary_projection_uses_workflow_and_people_links() -> None:
    task_list = SimpleNamespace(
        key="ENG",
        status_mode="custom",
        team_id="space-1",
        statuses=[StatusDefinition("qa", "QA Ready", "active")],
        space_statuses=[],
    )
    assignee = SimpleNamespace(full_name="Ada Lovelace")
    follower = SimpleNamespace(full_name="Grace Hopper")
    reporter = SimpleNamespace(full_name="Alan Turing")
    label = SimpleNamespace(id="label-1", name="blocked", color="#b45309")
    task = SimpleNamespace(
        id="task-1",
        list_id="list-1",
        task_list=task_list,
        task_number=42,
        title="Wire projection",
        description="",
        description_blocks=[],
        parent_id=None,
        subtasks=[SimpleNamespace(id="subtask-1")],
        status="qa",
        priority="urgent_customer",
        assignee_id="user-1",
        assignee=assignee,
        assignee_links=[SimpleNamespace(user_id="user-1", user=assignee)],
        follower_links=[SimpleNamespace(user_id="user-2", user=follower)],
        reporter_id="reporter-1",
        reporter=reporter,
        milestone_id=None,
        milestone=None,
        start_date=date(2026, 5, 1),
        due_date=date(2026, 5, 30),
        completed_date=None,
        board_position=7,
        archived=False,
        comments=[SimpleNamespace(id="comment-1")],
        checklist_items=[
            SimpleNamespace(completed=True),
            SimpleNamespace(completed=False),
        ],
        recurrence_rule=None,
        label_links=[SimpleNamespace(label=label)],
        updated_at=datetime(2026, 5, 30, tzinfo=UTC),
    )

    summary = serialize_task_summary(task)

    assert summary["reference"] == "ENG-42"
    assert summary["status_label"] == "QA Ready"
    assert summary["priority_label"] == "Urgent Customer"
    assert summary["assignee_ids"] == ["user-1"]
    assert summary["assignee_names"] == ["Ada Lovelace"]
    assert summary["follower_ids"] == ["user-2"]
    assert summary["follower_names"] == ["Grace Hopper"]
    assert summary["checklist_total"] == 2
    assert summary["checklist_done"] == 1
    assert summary["labels"] == [
        {"id": "label-1", "name": "blocked", "color": "#b45309"}
    ]
