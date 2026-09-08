from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.source_access import can_read_meeting
from open_work_hub_api.domains.docs.service import can_read_native_doc_for_rag
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.meeting.permissions import is_organizer, is_participant
from open_work_hub_api.domains.pms.access import _ensure_task_readable, ensure_task_attachable
from open_work_hub_api.domains.recording.models import Recording, RecordingTarget
from open_work_hub_api.domains.source_access.targets import (
    TargetRef,
    project_target_access,
)
from open_work_hub_api.domains.source_access.targets import (
    target_access_allowed as source_target_access_allowed,
)


def recording_target_ref(target: RecordingTarget) -> TargetRef:
    return TargetRef(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
    )


def can_view_recording_target(
    db: Session,
    *,
    user: User,
    target_app: str,
    target_type: str,
    target_id: str,
) -> bool:
    if target_app == "meeting":
        return _meeting_target_access_allowed(
            db,
            user=user,
            target_type=target_type,
            target_id=target_id,
        )
    if target_app == "pms":
        if _pms_target_access_allowed(
            db,
            user=user,
            target_type=target_type,
            target_id=target_id,
        ):
            return True
        return source_target_access_allowed(
            db=db,
            user=user,
            ref=TargetRef(app="pms", type=target_type, id=target_id),
        )
    if target_app == "docs":
        return _docs_target_access_allowed(
            db,
            user=user,
            target_type=target_type,
            target_id=target_id,
        )
    return False


def can_attach_recording_target(
    db: Session,
    *,
    user: User,
    target_app: str,
    target_type: str,
    target_id: str,
) -> bool:
    if target_app == "meeting":
        meeting = db.get(Meeting, target_id) if target_type == "meeting" else None
        return (
            meeting is not None
            and is_participant(user, meeting)
            and can_read_meeting(db, user=user, meeting_id=meeting.id)
        )
    if target_app == "pms" and target_type == "task":
        try:
            ensure_task_attachable(db, user, target_id)
        except HTTPException:
            return False
        return True
    return can_view_recording_target(
        db,
        user=user,
        target_app=target_app,
        target_type=target_type,
        target_id=target_id,
    )


def can_detach_recording_target(
    db: Session,
    *,
    user: User,
    target: RecordingTarget,
) -> bool:
    if target.added_by_id == user.id:
        return True
    if target.target_app == "meeting" and target.target_type == "meeting":
        meeting = db.scalar(
            select(Meeting).where(
                Meeting.id == target.target_id,
            )
        )
        return meeting is not None and is_organizer(user, meeting)
    if target.target_app in {"docs", "pms"}:
        projection = project_target_access(
            db=db,
            user=user,
            ref=recording_target_ref(target),
        )
        return projection.can_manage
    return False


def recording_access_allowed(
    db: Session,
    *,
    user: User,
    recording: Recording,
) -> bool:
    if recording.owner_id == user.id:
        return True
    return any(
        can_view_recording_target(
            db,
            user=user,
            target_app=target.target_app,
            target_type=target.target_type,
            target_id=target.target_id,
        )
        for target in recording.targets
    )


def _meeting_target_access_allowed(
    db: Session,
    *,
    user: User,
    target_type: str,
    target_id: str,
) -> bool:
    if target_type != "meeting":
        return False
    return can_read_meeting(db, user=user, meeting_id=target_id)


def _pms_target_access_allowed(
    db: Session,
    *,
    user: User,
    target_type: str,
    target_id: str,
) -> bool:
    if target_type != "task":
        return False
    try:
        _ensure_task_readable(db, user, target_id)
    except HTTPException:
        return False
    return True


def _docs_target_access_allowed(
    db: Session,
    *,
    user: User,
    target_type: str,
    target_id: str,
) -> bool:
    if target_type in {"native_doc", "doc"}:
        return can_read_native_doc_for_rag(db, user=user, doc_id=target_id)
    return source_target_access_allowed(
        db=db,
        user=user,
        ref=TargetRef(app="docs", type=target_type, id=target_id),
    )
