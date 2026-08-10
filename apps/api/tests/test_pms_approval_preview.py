from __future__ import annotations

from datetime import date

from ai_do_api.domains.ai.registry import PreviewField, WorkspaceContext
from ai_do_api.domains.pms.approval_preview import (
    build_add_comment_preview,
    build_create_task_preview,
    build_delete_task_preview,
    build_update_task_preview,
)
from ai_do_api.domains.pms.tools import PmsCreateTaskAiInput, PmsUpdateTaskAiInput


def _workspace_context() -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id="workspace-1",
        workspace_slug="delivery-hub",
        display_name="Delivery Hub",
    )


def test_create_task_preview_accepts_pydantic_args_and_compacts_lists() -> None:
    parsed_args = PmsCreateTaskAiInput(
        list_id="list-1",
        title="Prepare release checklist",
        body="  Confirm rollout tasks before launch.  ",
        assignee_ids=["user-1", "user-2", "user-3", "user-4"],
        labels=["release", "risk"],
        due_date=date(2026, 6, 1),
    )

    preview = build_create_task_preview(object(), _workspace_context(), parsed_args)

    assert preview.title == "[Delivery Hub] Create PMS task"
    assert preview.summary == "Confirm rollout tasks before launch."
    assert preview.fields == (
        PreviewField(label="List", value="list-1"),
        PreviewField(label="Title", value="Prepare release checklist"),
        PreviewField(label="Assignees", value="user-1, user-2, user-3 (+1)"),
        PreviewField(label="Labels", value="release, risk"),
        PreviewField(label="Due", value="2026-06-01"),
    )


def test_update_task_preview_falls_back_summary_and_only_shows_provided_fields() -> None:
    parsed_args = PmsUpdateTaskAiInput(
        task_id="task-1",
        body="   ",
        status="done",
        due_date=date(2026, 6, 2),
    )

    preview = build_update_task_preview(object(), _workspace_context(), parsed_args)

    assert preview.title == "[Delivery Hub] Update PMS task"
    assert preview.summary == "Update a PMS task from AI."
    assert preview.fields == (
        PreviewField(label="Task", value="task-1"),
        PreviewField(label="Status", value="done"),
        PreviewField(label="Due", value="2026-06-02"),
    )


def test_comment_preview_truncates_long_body() -> None:
    preview = build_add_comment_preview(
        object(),
        _workspace_context(),
        {"task_id": "task-2", "body": "x" * 220},
    )

    assert preview.title == "[Delivery Hub] Add PMS comment"
    assert preview.summary == f"{'x' * 179}…"
    assert preview.fields == (PreviewField(label="Task", value="task-2"),)


def test_delete_task_preview_accepts_mapping_args() -> None:
    preview = build_delete_task_preview(
        object(),
        _workspace_context(),
        {"task_id": "task-3"},
    )

    assert preview.title == "[Delivery Hub] Delete PMS task"
    assert preview.summary == "Delete one PMS task from AI."
    assert preview.fields == (PreviewField(label="Task", value="task-3"),)
