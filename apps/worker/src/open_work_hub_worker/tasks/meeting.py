from __future__ import annotations

import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from celery.exceptions import Ignore
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
    minio_client as _minio_client,
)
from open_work_hub_worker.settings import get_settings


_ensure_api_src_on_path()

from open_work_hub_api.core.asr import (  # noqa: E402
    PermanentError,
    TransientError,
    check_asr_health,
    get_asr_backend,
)
from open_work_hub_api.core.llm import (  # noqa: E402
    LlmRuntimeError,
    LlmTaskContext,
)
from open_work_hub_api.domains.ai.gateway import (  # noqa: E402
    LlmWorkloadContext,
    execute_llm,
)
from open_work_hub_api.domains.auth.models import Workspace  # noqa: E402
from open_work_hub_api.domains.auth.security import new_id  # noqa: E402
from open_work_hub_api.domains.meeting.models import (  # noqa: E402
    Meeting,
    MeetingAttendee,
    MeetingRecording,
)
from open_work_hub_api.domains.pms.models import TaskComment  # noqa: E402


logger = logging.getLogger(__name__)


def meeting_insights_module():
    from open_work_hub_api.domains.meeting import insights as meeting_insights

    return meeting_insights


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_recording(session: Session, recording_id: str) -> MeetingRecording | None:
    recording = session.scalar(
        select(MeetingRecording)
        .options(
            selectinload(MeetingRecording.meeting)
            .selectinload(Meeting.attendees)
            .selectinload(MeetingAttendee.user),
        )
        .where(MeetingRecording.id == recording_id)
    )
    if recording is None:
        return None
    if recording.transcription_status == "cancelled":
        return None
    if recording.meeting is None:
        return None
    return recording


def _heartbeat(
    session: Session, recording: MeetingRecording, pct: int, status_name: str | None = None
) -> None:
    recording.progress_pct = max(0, min(100, pct))
    if status_name is not None:
        recording.transcription_status = status_name
    session.add(recording)
    session.commit()


def _mark_failed(session: Session, recording_id: str, reason: str) -> None:
    session.rollback()
    recording = session.get(MeetingRecording, recording_id)
    if recording is None:
        return
    recording.transcription_status = "failed"
    recording.failure_reason = reason[:5000]
    session.add(recording)
    session.commit()


def _download_recording_to_tmp(recording: MeetingRecording) -> str:
    settings = get_settings()
    suffix = Path(recording.storage_key).suffix or ".bin"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.close()
    _minio_client().fget_object(
        settings.minio_bucket,
        recording.storage_key,
        handle.name,
    )
    return handle.name


def _recording_meeting_id(recording: object) -> str | None:
    meeting_id = getattr(recording, "meeting_id", None)
    if isinstance(meeting_id, str) and meeting_id:
        return meeting_id
    meeting = getattr(recording, "meeting", None)
    derived_id = getattr(meeting, "id", None)
    if isinstance(derived_id, str) and derived_id:
        return derived_id
    return None


def _summary_prompt(transcript_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "다음 회의 전사를 한국어로 정리하라. "
                "형식은 반드시 마크다운이며, 섹션은 다음 순서로 유지한다. "
                "1. 핵심 요약 2. 결정사항 3. 액션 아이템 4. 리스크"
            ),
        },
        {"role": "user", "content": transcript_text},
    ]


# TODO: Implement and publish the meeting-owned recording pipeline when its
# product flow is resumed. Until then, repository producers use the canonical
# recording.* chain; do not enqueue the reserved meeting.transcribe,
# meeting.summarize, meeting.extract_insights, or meeting.generate_doc tasks.
# Add an end-to-end producer/chain test before treating this block as active.
@celery_app.task(
    name="meeting.transcribe",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)
def transcribe_recording(self, recording_id: str) -> str:
    from open_work_hub_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync_by_id
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    session = _db_session()
    tmp_path: str | None = None
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.transcript_text:
            _heartbeat(session, recording, 60, "summarizing")
            return recording.id

        if recording.transcribe_started_at is None:
            recording.transcribe_started_at = _utcnow()
        _heartbeat(session, recording, max(recording.progress_pct, 10), "transcribing")

        health = check_asr_health(deep=True)
        if not health.ready:
            raise TransientError(health.detail or "ASR backend is not ready.")

        tmp_path = _download_recording_to_tmp(recording)
        last_pct = {"value": recording.progress_pct}

        def on_progress(value: float) -> None:
            pct = int(10 + max(0.0, min(1.0, value)) * 50)
            if pct <= last_pct["value"]:
                return
            last_pct["value"] = pct
            rec = session.get(MeetingRecording, recording_id)
            if rec is None or rec.transcription_status == "cancelled":
                raise Ignore()
            _heartbeat(session, rec, pct, "transcribing")

        result = get_asr_backend().transcribe(Path(tmp_path), on_progress=on_progress)
        recording = session.get(MeetingRecording, recording_id)
        if recording is None or recording.transcription_status == "cancelled":
            raise Ignore()
        recording.transcript_text = result.text.strip()
        if recording.duration_sec is None and result.duration_sec:
            recording.duration_sec = int(result.duration_sec)
        meeting_id = _recording_meeting_id(recording)
        if meeting_id is not None:
            enqueue_meeting_rag_sync_by_id(
                session,
                meeting_id=meeting_id,
                operation=RagSyncOperation.UPSERT,
            )
        session.add(recording)
        session.commit()
        _heartbeat(session, recording, 60, "summarizing")
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc))
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc))
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@celery_app.task(
    name="meeting.summarize",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=900,
)
def summarize_recording(self, recording_id: str) -> str:
    from open_work_hub_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync_by_id
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.summary_text:
            _heartbeat(session, recording, 90, "extracting_insights")
            return recording.id
        if not recording.transcript_text:
            raise PermanentError("Transcript is missing.")

        _heartbeat(session, recording, max(recording.progress_pct, 60), "summarizing")

        # Build the LlmTaskContext for this system job. Routing is delegated to
        # the AI Gateway so policy changes take effect without touching the
        # worker implementation.
        workspace_id = recording.meeting.workspace_id if recording.meeting else None
        if not workspace_id:
            raise PermanentError("Recording is not linked to a workspace.")

        context = LlmTaskContext(
            source="worker.meeting.summarize",
            actor_user_id=None,
            workspace_id=workspace_id,
            task_kind="meeting_summary",
            app_id="meeting",
        )
        try:
            completion = execute_llm(
                "meeting_summary",
                LlmWorkloadContext.from_task_context(context),
                session,
                messages=_summary_prompt(recording.transcript_text),
                temperature=0.2,
                max_tokens=4000,
            ).completion
        except LlmRuntimeError as error:
            raise TransientError(str(error)) from error
        summary = completion.text.strip()
        if not summary:
            raise PermanentError("LLM returned an empty summary.")
        recording = session.get(MeetingRecording, recording_id)
        if recording is None or recording.transcription_status == "cancelled":
            raise Ignore()
        recording.summary_text = summary
        meeting_id = _recording_meeting_id(recording)
        if meeting_id is not None:
            enqueue_meeting_rag_sync_by_id(
                session,
                meeting_id=meeting_id,
                operation=RagSyncOperation.UPSERT,
            )
        session.add(recording)
        session.commit()
        _heartbeat(session, recording, 90, "extracting_insights")
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc))
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc))
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(
    name="meeting.extract_insights",
    bind=True,
    acks_late=True,
    task_time_limit=900,
)
def extract_meeting_insights(self, recording_id: str) -> str:
    del self
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if not recording.summary_text or not recording.transcript_text:
            _heartbeat(session, recording, max(recording.progress_pct, 90), "generating_doc")
            return recording.id

        _heartbeat(session, recording, max(recording.progress_pct, 90), "extracting_insights")
        try:
            meeting_insights_module().extract_and_persist_meeting_insights(
                session,
                recording_id=recording.id,
                source="worker.meeting.extract_insights",
                actor_user_id=None,
            )
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.warning(
                "Meeting insight extraction failed for recording %s",
                recording_id,
                exc_info=True,
            )

        recording = session.get(MeetingRecording, recording_id)
        if recording is None or recording.transcription_status == "cancelled":
            raise Ignore()
        _heartbeat(session, recording, max(recording.progress_pct, 92), "generating_doc")
        return recording.id
    finally:
        session.close()


@celery_app.task(
    name="meeting.generate_doc",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=300,
)
def generate_meeting_doc(self, recording_id: str) -> str:
    from open_work_hub_api.domains.docs.minutes import create_meeting_minutes_doc
    from open_work_hub_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync_by_id
    from open_work_hub_api.domains.meeting import service as meeting_service
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.linked_doc_id:
            _heartbeat(session, recording, 100, "done")
            return recording.id
        if not recording.summary_text:
            raise PermanentError("Summary is missing.")
        if not recording.transcript_text:
            raise PermanentError("Transcript is missing.")

        meeting = recording.meeting
        if meeting is None:
            raise PermanentError("Meeting is missing.")
        doc = create_meeting_minutes_doc(
            session,
            meeting=meeting,
            transcript_text=recording.transcript_text,
            summary_text=recording.summary_text,
            owner_id=meeting.organizer_id,
        )
        meeting_service._attach_doc_link(
            session,
            meeting=meeting,
            doc=doc,
            added_by_id=meeting.organizer_id,
        )
        if recording.linked_task_id:
            workspace = session.get(Workspace, meeting.workspace_id)
            slug = workspace.key if workspace is not None else ""
            session.add(
                TaskComment(
                    id=new_id(),
                    task_id=recording.linked_task_id,
                    author_id=meeting.organizer_id,
                    body=f"📄 회의록: /w/{slug}/docs/{doc.id}" if slug else f"📄 회의록: {doc.id}",
                    body_blocks=None,
                )
            )
        recording = session.get(MeetingRecording, recording_id)
        if recording is None or recording.transcription_status == "cancelled":
            raise Ignore()
        recording.linked_doc_id = doc.id
        recording.transcription_status = "done"
        recording.progress_pct = 100
        recording.transcribe_completed_at = _utcnow()
        enqueue_meeting_rag_sync_by_id(
            session,
            meeting_id=meeting.id,
            operation=RagSyncOperation.UPSERT,
        )
        session.add(recording)
        session.commit()
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc))
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc))
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(name="meeting.cleanup_stale_staging")
def cleanup_stale_staging() -> dict[str, int]:
    from open_work_hub_api.domains.meeting import recordings as recording_service

    session = _db_session()
    try:
        return recording_service.cleanup_stale_staging_once(session)
    finally:
        session.close()
