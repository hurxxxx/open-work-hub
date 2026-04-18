from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from celery.exceptions import Ignore

from aidoo_worker.celery_app import celery_app
from aidoo_worker.settings import get_settings


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[5]


def _ensure_api_src_on_path() -> None:
    api_src = _workspace_root() / "apps" / "api" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_ensure_api_src_on_path()

from openai import OpenAIError  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, selectinload  # noqa: E402

from aidoo_api.core.asr import (  # noqa: E402
    PermanentError,
    TransientError,
    check_asr_health,
    get_asr_backend,
)
from aidoo_api.core.llm import (  # noqa: E402
    LlmTaskContext,
    complete_chat,
)
from aidoo_api.domains.auth.models import Workspace  # noqa: E402
from aidoo_api.domains.auth.security import new_id  # noqa: E402
from aidoo_api.domains.docs.minutes import create_meeting_minutes_doc  # noqa: E402
from aidoo_api.domains.meeting import recordings as recording_service  # noqa: E402
from aidoo_api.domains.meeting import service as meeting_service  # noqa: E402
from aidoo_api.domains.meeting.models import (  # noqa: E402
    Meeting,
    MeetingAttendee,
    MeetingRecording,
)
from aidoo_api.domains.pms.models import IssueComment  # noqa: E402


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _db_session() -> Session:
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return Session(engine)


def _minio_client():
    from urllib.parse import urlparse

    from minio import Minio

    settings = get_settings()
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    host = parsed.netloc or parsed.path
    return Minio(
        host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def _load_active_recording(session: Session, recording_id: str) -> MeetingRecording | None:
    recording = session.scalar(
        select(MeetingRecording)
        .options(
            selectinload(MeetingRecording.meeting).selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
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


def _heartbeat(session: Session, recording: MeetingRecording, pct: int, status_name: str | None = None) -> None:
    recording.progress_pct = max(0, min(100, pct))
    if status_name is not None:
        recording.transcription_status = status_name
    session.add(recording)
    session.commit()


def _mark_failed(session: Session, recording_id: str, reason: str) -> None:
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


@celery_app.task(
    name="meeting.transcribe",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)
def transcribe_recording(self, recording_id: str) -> str:
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

        health = check_asr_health()
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
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.summary_text:
            _heartbeat(session, recording, 90, "generating_doc")
            return recording.id
        if not recording.transcript_text:
            raise PermanentError("Transcript is missing.")

        _heartbeat(session, recording, max(recording.progress_pct, 60), "summarizing")

        # Build the LlmTaskContext for this system job. Routing is delegated to
        # ``complete_chat()`` so policy changes take effect without touching the
        # worker implementation.
        workspace_id = recording.meeting.workspace_id if recording.meeting else None
        if not workspace_id:
            raise PermanentError("Recording is not linked to a workspace.")

        context = LlmTaskContext(
            source="worker.meeting.summarize",
            actor_user_id=None,
            workspace_id=workspace_id,
            task_kind="meeting_summary",
        )
        try:
            response, _decision, _config = complete_chat(
                context,
                session,
                messages=_summary_prompt(recording.transcript_text),
                temperature=0.2,
                max_tokens=4000,
            )
        except OpenAIError as error:
            raise TransientError(str(error)) from error
        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            raise PermanentError("LLM returned an empty summary.")
        recording = session.get(MeetingRecording, recording_id)
        if recording is None or recording.transcription_status == "cancelled":
            raise Ignore()
        recording.summary_text = summary
        session.add(recording)
        session.commit()
        _heartbeat(session, recording, 90, "generating_doc")
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
    name="meeting.generate_doc",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=300,
)
def generate_meeting_doc(self, recording_id: str) -> str:
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

        meeting = meeting_service._load_meeting(session, recording.meeting_id)
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
                IssueComment(
                    id=new_id(),
                    issue_id=recording.linked_task_id,
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
    session = _db_session()
    try:
        return recording_service.cleanup_stale_staging_once(session)
    finally:
        session.close()
