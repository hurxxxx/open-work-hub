from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.planner.event_access import (
    ensure_planner_principal_user,
    require_planner_user_write_principal,
)
from open_work_hub_api.domains.planner.event_application import (
    PlannerEventCreateCommand,
    PlannerEventUpdateCommand,
    apply_planner_event_update,
    new_planner_event,
)
from open_work_hub_api.domains.planner.models import PlannerEvent
from open_work_hub_api.domains.rag.contracts import RagSyncOperation


def test_new_planner_event_builds_model_from_command() -> None:
    event = new_planner_event(
        owner_id="user-1",
        command=PlannerEventCreateCommand(
            title="  Planning sync  ",
            description="  Align  ",
            location="  Seoul  ",
            all_day=False,
            start="2026-05-04T10:00:00+09:00",
            end="2026-05-04T11:00:00+09:00",
            time_zone="Asia/Seoul",
        ),
        id_factory=lambda: "event-1",
    )

    assert event.id == "event-1"
    assert event.title == "Planning sync"
    assert event.description == "Align"
    assert event.location == "Seoul"
    assert event.start_at == datetime(2026, 5, 4, 1, 0)
    assert event.end_at == datetime(2026, 5, 4, 2, 0)
    assert event.start_has_time is True
    assert event.end_has_time is True


def test_apply_planner_event_update_marks_content_for_projection_refresh() -> None:
    event = PlannerEvent(
        id="event-1",
        owner_id="user-1",
        title="Old",
        description="",
        location="",
        time_zone="Asia/Seoul",
        all_day=False,
        start_at=datetime(2026, 5, 4, 1, 0),
        end_at=datetime(2026, 5, 4, 2, 0),
    )

    operation = apply_planner_event_update(
        event,
        PlannerEventUpdateCommand(title="  New title  "),
    )

    assert operation == RagSyncOperation.UPSERT
    assert event.title == "New title"


def test_apply_planner_event_update_rejects_partial_bounds() -> None:
    event = PlannerEvent(
        id="event-1",
        owner_id="user-1",
        title="Old",
        description="",
        location="",
        time_zone="Asia/Seoul",
        all_day=False,
        start_at=datetime(2026, 5, 4, 1, 0),
        end_at=datetime(2026, 5, 4, 2, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        apply_planner_event_update(event, PlannerEventUpdateCommand(start="2026-05-04"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.code == "planner.update_start_end_required"


def test_planner_event_access_enforces_user_principal() -> None:
    with pytest.raises(HTTPException) as kind_error:
        require_planner_user_write_principal(
            CallerPrincipal(kind="system", source="test"),
        )
    assert kind_error.value.detail.code == "planner.write_user_principal_required"

    with pytest.raises(HTTPException) as user_error:
        ensure_planner_principal_user(
            principal=CallerPrincipal(kind="user", user_id="user-2", source="test"),
            user=SimpleNamespace(id="user-1"),
        )
    assert user_error.value.detail.code == "planner.principal_user_mismatch"
