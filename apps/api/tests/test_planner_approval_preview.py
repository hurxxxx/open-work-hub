from __future__ import annotations

from datetime import UTC, datetime, timedelta

from open_alm_api.domains.ai.registry import PreviewField, WorkspaceContext
from open_alm_api.domains.planner.approval_preview import (
    build_create_event_preview,
    build_delete_event_preview,
    build_update_event_preview,
)
from open_alm_api.domains.planner.tools import CreateEventArgs, UpdateEventArgs


def _workspace_context() -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id="workspace-1",
        workspace_slug="delivery-hub",
        display_name="Delivery Hub",
    )


def test_create_event_preview_is_personal_and_workspace_independent() -> None:
    start_at = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    parsed_args = CreateEventArgs(
        title="Planning sync",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        description="  Align the delivery timeline.  ",
    )

    preview = build_create_event_preview(object(), _workspace_context(), parsed_args)

    assert preview.title == "Create personal planner event"
    assert preview.summary == "Align the delivery timeline."
    assert preview.fields == (
        PreviewField(label="Title", value="Planning sync"),
        PreviewField(label="Start", value=str(start_at)),
        PreviewField(label="Scope", value="personal"),
    )


def test_update_event_preview_falls_back_summary_and_only_shows_provided_fields() -> None:
    parsed_args = UpdateEventArgs(
        event_id="event-123",
        description="   ",
        title="Updated title",
    )

    preview = build_update_event_preview(object(), _workspace_context(), parsed_args)

    assert preview.title == "Update personal planner event"
    assert preview.summary == "Update a planner event from AI."
    assert preview.fields == (
        PreviewField(label="Event ID", value="event-123"),
        PreviewField(label="Title", value="Updated title"),
    )


def test_delete_event_preview_accepts_mapping_args() -> None:
    preview = build_delete_event_preview(
        object(),
        _workspace_context(),
        {"event_id": "event-456"},
    )

    assert preview.title == "Delete personal planner event"
    assert preview.summary == "Delete a planner event from AI."
    assert preview.fields == (PreviewField(label="Event ID", value="event-456"),)
