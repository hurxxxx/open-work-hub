from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.meeting.models import MeetingTaskLink
from open_work_hub_api.domains.pms.access import _ensure_task_readable
from open_work_hub_api.domains.recording.target_access import can_attach_recording_target
from open_work_hub_api.domains.recording.target_plan import RecordingTargetRef


@dataclass(frozen=True)
class InitialRecordingTargetResolution:
    ref: RecordingTargetRef | None
    linked_task_id: str | None


def resolve_initial_recording_target(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    target_app: str | None,
    target_type: str | None,
    target_id: str | None,
    linked_task_id: str | None,
) -> InitialRecordingTargetResolution:
    ref = _normalize_initial_target(
        target_app=target_app,
        target_type=target_type,
        target_id=target_id,
    )
    normalized_linked_task_id = linked_task_id.strip() if linked_task_id else None
    if ref is None:
        return InitialRecordingTargetResolution(
            ref=None,
            linked_task_id=normalized_linked_task_id,
        )

    if not can_attach_recording_target(
        db,
        user=user,
        workspace=workspace,
        target_app=ref.target_app,
        target_type=ref.target_type,
        target_id=ref.target_id,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.target_attach_required",
        )
    if ref.target_app == "meeting" and ref.target_type == "meeting":
        _validate_meeting_linked_task(
            db,
            user=user,
            meeting_id=ref.target_id,
            linked_task_id=normalized_linked_task_id,
        )
    return InitialRecordingTargetResolution(
        ref=ref,
        linked_task_id=normalized_linked_task_id,
    )


def _normalize_initial_target(
    *,
    target_app: str | None,
    target_type: str | None,
    target_id: str | None,
) -> RecordingTargetRef | None:
    values = [target_app, target_type, target_id]
    if not any(values):
        return None
    if not all(values):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.target_attach_required",
        )
    return RecordingTargetRef(
        target_app=str(target_app),
        target_type=str(target_type),
        target_id=str(target_id),
    )


def _validate_meeting_linked_task(
    db: Session,
    *,
    user: User,
    meeting_id: str,
    linked_task_id: str | None,
) -> None:
    if linked_task_id is None:
        return
    _ensure_task_readable(db, user, linked_task_id)
    exists = db.scalar(
        select(MeetingTaskLink.id).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.task_id == linked_task_id,
        )
    )
    if exists is None:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.linked_task_attached_required",
        )
