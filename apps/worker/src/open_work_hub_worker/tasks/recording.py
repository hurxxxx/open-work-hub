from __future__ import annotations

import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from open_work_hub_api.core.llm import LlmRuntimeError, LlmTaskContext  # noqa: E402
from open_work_hub_api.domains.ai.gateway import (  # noqa: E402
    LlmWorkloadContext,
    execute_llm,
)
from open_work_hub_api.domains.auth.workspace_app_gate import (  # noqa: E402
    is_app_enabled_for_user_context,
)
from open_work_hub_api.domains.recording.models import Recording, RecordingResult  # noqa: E402


logger = logging.getLogger(__name__)


class SupersededRecordingGeneration(Exception):
    """Terminal no-op for a task that no longer owns the recording attempt."""


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_recording(session: Session, recording_id: str) -> Recording | None:
    recording = session.scalar(
        select(Recording)
        .options(selectinload(Recording.targets), selectinload(Recording.result))
        .where(Recording.id == recording_id)
        .execution_options(populate_existing=True)
    )
    if recording is None:
        return None
    if recording.trashed_at is not None:
        return None
    if recording.audio_status != "saved" or not recording.storage_key:
        return None
    return recording


def _lock_current_recording_attempt(
    session: Session,
    recording_id: str,
    expected_attempt_id: str,
) -> Recording:
    if not expected_attempt_id:
        raise SupersededRecordingGeneration()
    recording = session.scalar(
        select(Recording)
        .options(selectinload(Recording.targets), selectinload(Recording.result))
        .where(
            Recording.id == recording_id,
            Recording.celery_task_id == expected_attempt_id,
            Recording.trashed_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if recording is None:
        raise SupersededRecordingGeneration()
    return recording


def _heartbeat(
    session: Session,
    recording: Recording,
    pct: int,
    *,
    expected_attempt_id: str,
    transcript_status: str | None = None,
    summary_status: str | None = None,
) -> None:
    recording = _lock_current_recording_attempt(
        session,
        recording.id,
        expected_attempt_id,
    )
    recording.progress_pct = max(0, min(100, pct))
    if transcript_status is not None:
        recording.transcript_status = transcript_status
    if summary_status is not None:
        recording.summary_status = summary_status
    recording.updated_at = _utcnow()
    session.add(recording)
    session.commit()


def _ensure_current_attempt(recording: Recording, expected_attempt_id: str) -> None:
    if not expected_attempt_id or recording.celery_task_id != expected_attempt_id:
        raise SupersededRecordingGeneration()


def _mark_failed(
    session: Session,
    recording_id: str,
    reason: str,
    *,
    stage: str,
    expected_attempt_id: str,
) -> bool:
    session.rollback()
    try:
        recording = _lock_current_recording_attempt(
            session,
            recording_id,
            expected_attempt_id,
        )
    except SupersededRecordingGeneration:
        return False
    if stage == "transcript":
        recording.transcript_status = "failed"
    else:
        recording.summary_status = "failed"
    recording.failure_reason = reason[:5000]
    recording.celery_task_id = None
    recording.updated_at = _utcnow()
    session.add(recording)
    session.commit()
    return True


def _ensure_recording_execution_allowed(
    session: Session,
    recording: Recording,
    *,
    stage: str,
    expected_attempt_id: str,
) -> None:
    _ensure_current_attempt(recording, expected_attempt_id)
    if is_app_enabled_for_user_context(
        session,
        app_id="recording",
        user_id=recording.owner_id,
        workspace_id=recording.workspace_id,
    ):
        return
    _mark_failed(
        session,
        recording.id,
        "Recording app execution disabled or requester membership revoked.",
        stage=stage,
        expected_attempt_id=expected_attempt_id,
    )
    raise Ignore()


def _download_recording_to_tmp(recording: Recording) -> str:
    settings = get_settings()
    suffix = Path(recording.storage_key or "").suffix or ".bin"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.close()
    _minio_client().fget_object(
        settings.minio_bucket,
        recording.storage_key,
        handle.name,
    )
    return handle.name


def _recording_title(recording: Recording) -> str:
    return recording.title.strip() or f"Recording {recording.started_at:%Y-%m-%d %H:%M:%S}"


def _analysis_messages(recording: Recording, transcript: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are meeting.transcript_summarizer, a local-only specialist agent. "
                "Use only the provided transcript. Return Korean markdown with these sections: "
                "핵심 요약, 결정사항, 액션 아이템, 리스크/이슈, 후속 확인 필요. "
                "If a section has no evidence, write '확인된 내용 없음'."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Recording title: {_recording_title(recording)}\n"
                f"Started at UTC: {recording.started_at:%Y-%m-%d %H:%M:%S}\n\n"
                "Transcript:\n"
                f"{transcript}"
            ),
        },
    ]


def _verification_messages(transcript: str, summary: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are verifier.grounding. Check whether the Korean summary is grounded "
                "in the transcript. Return Korean markdown. Start with '검증: 통과' or "
                "'검증: 수정 필요'. If correction is needed, include a corrected concise summary."
            ),
        },
        {
            "role": "user",
            "content": (f"Transcript:\n{transcript[:24000]}\n\nSummary:\n{summary}"),
        },
    ]


def _complete_local_agent(
    session: Session,
    *,
    source: str,
    workspace_id: str,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> str:
    context = LlmTaskContext(
        source=source,
        actor_user_id=None,
        workspace_id=workspace_id,
        task_kind="meeting_summary",
        app_id="recording",
    )
    try:
        completion = execute_llm(
            "meeting_summary",
            LlmWorkloadContext.from_task_context(context),
            session,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
            reasoning_effort="none",
        ).completion
    except LlmRuntimeError as error:
        raise TransientError(str(error)) from error
    result = completion.text.strip()
    if not result:
        raise PermanentError("Local transcript agent returned an empty result.")
    return result


@celery_app.task(
    name="recording.transcribe",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)
def transcribe_recording(
    self,
    recording_id: str,
    attempt_id: str,
) -> dict[str, str]:
    session = _db_session()
    tmp_path: str | None = None
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        _ensure_current_attempt(recording, attempt_id)
        if (
            recording.result is not None
            and recording.result.transcript_text
            and recording.transcript_status == "done"
        ):
            _heartbeat(
                session,
                recording,
                max(recording.progress_pct, 60),
                expected_attempt_id=attempt_id,
            )
            return {"recording_id": recording.id, "attempt_id": attempt_id}

        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="transcript",
            expected_attempt_id=attempt_id,
        )

        if recording.transcribe_started_at is None:
            recording.transcribe_started_at = _utcnow()
        _heartbeat(
            session,
            recording,
            max(recording.progress_pct, 10),
            expected_attempt_id=attempt_id,
            transcript_status="transcribing",
        )

        health = check_asr_health(deep=True)
        if not health.ready:
            raise TransientError(health.detail or "ASR backend is not ready.")

        tmp_path = _download_recording_to_tmp(recording)
        last_pct = {"value": recording.progress_pct}

        def on_progress(value: float) -> None:
            pct = int(10 + max(0.0, min(1.0, value)) * 45)
            if pct <= last_pct["value"]:
                return
            last_pct["value"] = pct
            rec = _load_active_recording(session, recording_id)
            if rec is None:
                raise Ignore()
            _ensure_recording_execution_allowed(
                session,
                rec,
                stage="transcript",
                expected_attempt_id=attempt_id,
            )
            _heartbeat(
                session,
                rec,
                pct,
                expected_attempt_id=attempt_id,
                transcript_status="transcribing",
            )

        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="transcript",
            expected_attempt_id=attempt_id,
        )
        result = get_asr_backend().transcribe(Path(tmp_path), on_progress=on_progress)
        text = result.text.strip()
        if not text:
            raise PermanentError("ASR backend returned an empty transcript.")

        recording = _lock_current_recording_attempt(
            session,
            recording_id,
            attempt_id,
        )
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="transcript",
            expected_attempt_id=attempt_id,
        )
        result_row = session.get(RecordingResult, recording.id)
        if result_row is None:
            result_row = RecordingResult(
                recording_id=recording.id,
                transcript_text=text,
                version=1,
            )
        elif result_row.transcript_text != text:
            result_row.transcript_text = text
            result_row.summary_text = None
            result_row.verifier_note = None
            result_row.generated_at = None
            result_row.version += 1
        result_row.updated_at = _utcnow()
        session.add(result_row)
        if recording.duration_sec is None and result.duration_sec:
            recording.duration_sec = int(result.duration_sec)
        recording.transcript_status = "done"
        recording.summary_status = "pending"
        recording.transcribe_completed_at = _utcnow()
        recording.progress_pct = max(recording.progress_pct, 60)
        recording.failure_reason = None
        recording.updated_at = _utcnow()
        session.add(recording)
        session.commit()
        return {"recording_id": recording.id, "attempt_id": attempt_id}
    except SupersededRecordingGeneration:
        session.rollback()
        raise Ignore()
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(
            session,
            recording_id,
            str(exc),
            stage="transcript",
            expected_attempt_id=attempt_id,
        )
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(
                session,
                recording_id,
                str(exc),
                stage="transcript",
                expected_attempt_id=attempt_id,
            )
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@celery_app.task(
    name="recording.analyze_transcript",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=900,
)
def analyze_transcript(self, payload: dict[str, Any]) -> dict[str, Any]:
    recording_id = str(payload.get("recording_id") or "")
    attempt_id = str(payload.get("attempt_id") or "")
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        _ensure_current_attempt(recording, attempt_id)
        result_row = recording.result
        if result_row is None or not result_row.transcript_text:
            raise PermanentError("Transcript is missing.")
        if result_row.summary_text and recording.summary_status in {"verifying", "done"}:
            return {
                "recording_id": recording.id,
                "attempt_id": attempt_id,
                "result_version": result_row.version,
                "summary": result_row.summary_text,
                "agent_flow": ["domain.meeting", "meeting.transcript_summarizer"],
            }

        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )

        _heartbeat(
            session,
            recording,
            max(recording.progress_pct, 72),
            expected_attempt_id=attempt_id,
            summary_status="analyzing",
        )
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        result_version = result_row.version
        summary = _complete_local_agent(
            session,
            source="worker.recording.agent.domain_meeting",
            workspace_id=recording.workspace_id,
            messages=_analysis_messages(recording, result_row.transcript_text),
            max_tokens=6000,
        )
        recording = _lock_current_recording_attempt(
            session,
            recording_id,
            attempt_id,
        )
        if recording is None or recording.result is None:
            raise Ignore()
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        if recording.result.version != result_version:
            raise SupersededRecordingGeneration()
        recording.result.summary_text = summary
        recording.result.verifier_note = None
        recording.result.updated_at = _utcnow()
        recording.summary_status = "verifying"
        recording.progress_pct = max(recording.progress_pct, 84)
        recording.updated_at = _utcnow()
        session.add(recording.result)
        session.add(recording)
        session.commit()
        return {
            "recording_id": recording.id,
            "attempt_id": attempt_id,
            "result_version": result_version,
            "summary": summary,
            "agent_flow": ["domain.meeting", "meeting.transcript_summarizer"],
        }
    except SupersededRecordingGeneration:
        session.rollback()
        raise Ignore()
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(
            session,
            recording_id,
            str(exc),
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(
                session,
                recording_id,
                str(exc),
                stage="summary",
                expected_attempt_id=attempt_id,
            )
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(
    name="recording.verify_transcript_summary",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=600,
)
def verify_transcript_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
    recording_id = str(payload.get("recording_id") or "")
    attempt_id = str(payload.get("attempt_id") or "")
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        _ensure_current_attempt(recording, attempt_id)
        result_row = recording.result
        transcript = (result_row.transcript_text if result_row is not None else "").strip()
        summary = str(payload.get("summary") or "").strip()
        result_version = int(payload.get("result_version") or 0)
        if not transcript or not summary:
            raise PermanentError("Transcript summary verification input is missing.")
        if result_row is None or result_row.version != result_version:
            raise SupersededRecordingGeneration()

        if (
            result_row is not None
            and result_row.verifier_note
            and recording.summary_status == "done"
        ):
            return {
                **payload,
                "verifier_note": result_row.verifier_note,
            }

        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )

        verifier_note = _complete_local_agent(
            session,
            source="worker.recording.agent.verifier_grounding",
            workspace_id=recording.workspace_id,
            messages=_verification_messages(transcript, summary),
            max_tokens=2500,
        )
        recording = _lock_current_recording_attempt(
            session,
            recording_id,
            attempt_id,
        )
        if recording is None or recording.result is None:
            raise Ignore()
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        if recording.result.version != result_version:
            raise SupersededRecordingGeneration()
        recording.result.verifier_note = verifier_note
        recording.result.updated_at = _utcnow()
        recording.summary_status = "verifying"
        recording.progress_pct = max(recording.progress_pct, 94)
        recording.updated_at = _utcnow()
        session.add(recording.result)
        session.add(recording)
        session.commit()
        return {
            "recording_id": recording.id,
            "attempt_id": attempt_id,
            "result_version": result_version,
            "summary": summary,
            "verifier_note": verifier_note,
            "agent_flow": [
                *list(payload.get("agent_flow") or []),
                "verifier.grounding",
            ],
        }
    except SupersededRecordingGeneration:
        session.rollback()
        raise Ignore()
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(
            session,
            recording_id,
            str(exc),
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(
                session,
                recording_id,
                str(exc),
                stage="summary",
                expected_attempt_id=attempt_id,
            )
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(
    name="recording.persist_result",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=300,
)
def persist_recording_result(self, payload: dict[str, Any]) -> str:
    recording_id = str(payload.get("recording_id") or "")
    attempt_id = str(payload.get("attempt_id") or "")
    summary = str(payload.get("summary") or "").strip()
    result_version = int(payload.get("result_version") or 0)
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if (
            recording.summary_status == "done"
            and recording.result is not None
            and recording.result.version == result_version
            and recording.result.summary_text == summary
        ):
            return recording.id
        recording = _lock_current_recording_attempt(
            session,
            recording_id,
            attempt_id,
        )
        _ensure_recording_execution_allowed(
            session,
            recording,
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        if not summary:
            raise PermanentError("Recording summary is missing.")
        verifier_note = str(payload.get("verifier_note") or "").strip()
        if recording.result is None:
            raise PermanentError("Recording transcript result is missing.")
        if recording.result.version != result_version:
            raise SupersededRecordingGeneration()
        if recording.result.summary_text != summary:
            raise SupersededRecordingGeneration()
        recording.result.verifier_note = verifier_note
        recording.result.generated_at = _utcnow()
        recording.result.updated_at = _utcnow()
        recording.summary_status = "done"
        recording.meeting_insight_status = "none"
        recording.progress_pct = 100
        recording.failure_reason = None
        recording.celery_task_id = None
        recording.updated_at = _utcnow()
        session.add(recording.result)
        session.add(recording)
        session.commit()
        return recording.id
    except SupersededRecordingGeneration:
        session.rollback()
        raise Ignore()
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(
            session,
            recording_id,
            str(exc),
            stage="summary",
            expected_attempt_id=attempt_id,
        )
        raise Ignore()
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(
                session,
                recording_id,
                str(exc),
                stage="summary",
                expected_attempt_id=attempt_id,
            )
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
