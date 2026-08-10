from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.docs.models import NativeDoc
from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.pms.models import Task
from open_alm_api.domains.recording.models import Recording, RecordingTarget
from open_alm_api.domains.recording.schemas import RecordingOut


TargetTitleKey = tuple[str, str, str]


def target_title_key(target: Any) -> TargetTitleKey:
    return (target.target_app, target.target_type, target.target_id)


def load_target_title_map(
    db: Session,
    targets: Iterable[RecordingTarget],
) -> dict[TargetTitleKey, str]:
    meeting_ids = {
        item.target_id
        for item in targets
        if item.target_app == "meeting" and item.target_type == "meeting"
    }
    task_ids = {
        item.target_id
        for item in targets
        if item.target_app == "pms" and item.target_type == "task"
    }
    doc_ids = {
        item.target_id
        for item in targets
        if item.target_app == "docs" and item.target_type in {"native_doc", "doc"}
    }

    titles: dict[TargetTitleKey, str] = {}
    if meeting_ids:
        for meeting_id, title in db.execute(
            select(Meeting.id, Meeting.title).where(Meeting.id.in_(meeting_ids))
        ):
            titles[("meeting", "meeting", meeting_id)] = title
    if task_ids:
        for task_id, title in db.execute(select(Task.id, Task.title).where(Task.id.in_(task_ids))):
            titles[("pms", "task", task_id)] = title
    if doc_ids:
        for doc_id, title in db.execute(
            select(NativeDoc.id, NativeDoc.title).where(NativeDoc.id.in_(doc_ids))
        ):
            titles[("docs", "native_doc", doc_id)] = title
            titles[("docs", "doc", doc_id)] = title
    return titles


def serialize_recording(
    recording: Recording,
    *,
    title_map: dict[TargetTitleKey, str],
) -> RecordingOut:
    out = RecordingOut.model_validate(recording)
    out.targets = [
        target.model_copy(
            update={"target_title": title_map.get(target_title_key(target))}
        )
        for target in out.targets
    ]
    return out


def serialize_recording_with_target_titles(db: Session, recording: Recording) -> RecordingOut:
    return serialize_recording(
        recording,
        title_map=load_target_title_map(db, list(recording.targets)),
    )


def serialize_recordings_with_target_titles(
    db: Session,
    recordings: Iterable[Recording],
) -> list[RecordingOut]:
    recordings_list = list(recordings)
    title_map = load_target_title_map(
        db,
        [target for recording in recordings_list for target in recording.targets],
    )
    return [
        serialize_recording(recording, title_map=title_map) for recording in recordings_list
    ]
