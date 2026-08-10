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
from open_work_hub_api.domains.auth.security import new_id  # noqa: E402
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocPage, NativeDocTarget  # noqa: E402
from open_work_hub_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync  # noqa: E402
from open_work_hub_api.domains.meeting.models import Meeting  # noqa: E402
from open_work_hub_api.domains.rag.contracts import RagSyncOperation  # noqa: E402
from open_work_hub_api.domains.recording.models import Recording  # noqa: E402


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_recording(session: Session, recording_id: str) -> Recording | None:
    recording = session.scalar(
        select(Recording)
        .options(selectinload(Recording.targets))
        .where(Recording.id == recording_id)
    )
    if recording is None:
        return None
    if recording.trashed_at is not None:
        return None
    if recording.audio_status != "saved" or not recording.storage_key:
        return None
    return recording


def _heartbeat(
    session: Session,
    recording: Recording,
    pct: int,
    *,
    transcript_status: str | None = None,
    raw_doc_status: str | None = None,
    minutes_status: str | None = None,
) -> None:
    recording.progress_pct = max(0, min(100, pct))
    if transcript_status is not None:
        recording.transcript_status = transcript_status
    if raw_doc_status is not None:
        recording.raw_transcript_doc_status = raw_doc_status
    if minutes_status is not None:
        recording.minutes_doc_status = minutes_status
    recording.updated_at = _utcnow()
    session.add(recording)
    session.commit()


def _mark_failed(session: Session, recording_id: str, reason: str, *, stage: str) -> None:
    session.rollback()
    recording = session.get(Recording, recording_id)
    if recording is None:
        return
    if stage == "transcript":
        recording.transcript_status = "failed"
    elif stage == "raw_doc":
        recording.raw_transcript_doc_status = "failed"
    else:
        recording.minutes_doc_status = "failed"
    recording.failure_reason = reason[:5000]
    recording.celery_task_id = None
    recording.updated_at = _utcnow()
    session.add(recording)
    session.commit()


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


def _primary_doc_target(recording: Recording) -> tuple[str, str, str, int] | None:
    if not recording.targets:
        return None
    primary = next((target for target in recording.targets if target.is_primary), None)
    target = primary or sorted(recording.targets, key=lambda item: item.created_at)[0]
    return (
        target.target_app,
        target.target_type,
        target.target_id,
        target.sort_order,
    )


def _primary_meeting_id(recording: Recording) -> str | None:
    primary = next(
        (
            target
            for target in recording.targets
            if target.is_primary
            and target.target_app == "meeting"
            and target.target_type == "meeting"
        ),
        None,
    )
    if primary is not None:
        return primary.target_id
    for target in recording.targets:
        if target.target_app == "meeting" and target.target_type == "meeting":
            return target.target_id
    return None


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _heading(text: str, level: int = 2) -> dict:
    return {
        "type": "heading",
        "props": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _blocks_from_text(title: str, text: str) -> list[dict]:
    blocks: list[dict] = [_heading(title, level=1)]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return [*blocks, _paragraph("내용이 없습니다.")]
    for line in lines:
        blocks.append(_paragraph(line))
    return blocks


def _raw_transcript_blocks(recording: Recording) -> list[dict]:
    transcript = (recording.transcript_text or "").strip()
    blocks = [
        _heading("전사 원문", level=1),
        _paragraph(f"녹음: {_recording_title(recording)}"),
        _paragraph(f"녹음 시작: {recording.started_at:%Y-%m-%d %H:%M:%S} UTC"),
    ]
    if transcript:
        blocks.extend(_blocks_from_text("원문", transcript)[1:])
    else:
        blocks.append(_paragraph("전사 원문이 없습니다."))
    return blocks


def _minutes_blocks(recording: Recording, minutes_text: str, verifier_note: str) -> list[dict]:
    blocks = [
        _heading("녹음 정리", level=1),
        _paragraph(f"녹음: {_recording_title(recording)}"),
        _paragraph(f"녹음 시작: {recording.started_at:%Y-%m-%d %H:%M:%S} UTC"),
    ]
    blocks.extend(_blocks_from_text("요약 및 후속 조치", minutes_text)[1:])
    if recording.raw_transcript_doc_id:
        blocks.append(_heading("전사 원문"))
        blocks.append(_paragraph(f"전사 원문 문서: {recording.raw_transcript_doc_id}"))
    if verifier_note:
        blocks.append(_heading("검증 메모"))
        blocks.append(_paragraph(verifier_note))
    return blocks


def _create_recording_doc(
    session: Session,
    *,
    recording: Recording,
    title: str,
    first_page_title: str,
    content_blocks: list[dict],
    source_kind: str,
) -> NativeDoc:
    doc = NativeDoc(
        id=new_id(),
        workspace_id=recording.workspace_id,
        owner_id=recording.owner_id,
        title=title,
        source_app="recording",
        source_kind=source_kind,
        source_ref=recording.id,
        generation_kind="system_ai",
    )
    session.add(doc)
    session.add(
        NativeDocPage(
            id=new_id(),
            doc_id=doc.id,
            parent_id=None,
            title=first_page_title,
            content_blocks=content_blocks,
            sort_order=0,
            created_by_id=recording.owner_id,
        )
    )
    primary_target = _primary_doc_target(recording)
    if primary_target is not None:
        target_app, target_type, target_id, sort_order = primary_target
        session.add(
            NativeDocTarget(
                id=new_id(),
                doc_id=doc.id,
                target_app=target_app,
                target_type=target_type,
                target_id=target_id,
                is_primary=True,
                sort_order=sort_order,
            )
        )
    enqueue_native_doc_rag_sync(
        session,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    session.flush()
    return doc


def _attach_minutes_doc_to_meeting(
    session: Session, *, recording: Recording, doc: NativeDoc
) -> None:
    meeting_id = _primary_meeting_id(recording)
    if meeting_id is None:
        return
    meeting = session.scalar(
        select(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.workspace_id == recording.workspace_id,
        )
    )
    if meeting is None:
        return
    from open_work_hub_api.domains.meeting import service as meeting_service

    meeting_service._attach_doc_link(
        session,
        meeting=meeting,
        doc=doc,
        added_by_id=recording.owner_id,
    )


def _analysis_messages(recording: Recording) -> list[dict[str, str]]:
    transcript = (recording.transcript_text or "").strip()
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
def transcribe_recording(self, recording_id: str) -> str:
    session = _db_session()
    tmp_path: str | None = None
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.transcript_text and recording.transcript_status == "done":
            _heartbeat(session, recording, max(recording.progress_pct, 60))
            return recording.id

        if recording.transcribe_started_at is None:
            recording.transcribe_started_at = _utcnow()
        _heartbeat(
            session, recording, max(recording.progress_pct, 10), transcript_status="transcribing"
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
            rec = session.get(Recording, recording_id)
            if rec is None or rec.trashed_at is not None:
                raise Ignore()
            _heartbeat(session, rec, pct, transcript_status="transcribing")

        result = get_asr_backend().transcribe(Path(tmp_path), on_progress=on_progress)
        text = result.text.strip()
        if not text:
            raise PermanentError("ASR backend returned an empty transcript.")

        recording = session.get(Recording, recording_id)
        if recording is None or recording.trashed_at is not None:
            raise Ignore()
        recording.transcript_text = text
        if recording.duration_sec is None and result.duration_sec:
            recording.duration_sec = int(result.duration_sec)
        recording.transcript_status = "done"
        recording.transcribe_completed_at = _utcnow()
        recording.progress_pct = max(recording.progress_pct, 60)
        recording.failure_reason = None
        recording.updated_at = _utcnow()
        session.add(recording)
        session.commit()
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc), stage="transcript")
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc), stage="transcript")
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@celery_app.task(
    name="recording.create_raw_transcript_doc",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=300,
)
def create_raw_transcript_doc(self, recording_id: str) -> str:
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.raw_transcript_doc_id and recording.raw_transcript_doc_status == "done":
            _heartbeat(session, recording, max(recording.progress_pct, 70))
            return recording.id
        if not recording.transcript_text:
            raise PermanentError("Transcript is missing.")

        _heartbeat(session, recording, max(recording.progress_pct, 65), raw_doc_status="creating")
        doc = _create_recording_doc(
            session,
            recording=recording,
            title=f"전사 원문: {_recording_title(recording)}",
            first_page_title="전사 원문",
            content_blocks=_raw_transcript_blocks(recording),
            source_kind="raw_transcript",
        )
        recording.raw_transcript_doc_id = doc.id
        recording.raw_transcript_doc_status = "done"
        recording.progress_pct = max(recording.progress_pct, 72)
        recording.failure_reason = None
        recording.updated_at = _utcnow()
        session.add(recording)
        session.commit()
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc), stage="raw_doc")
        raise Ignore()
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc), stage="raw_doc")
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(
    name="recording.analyze_transcript",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=900,
)
def analyze_transcript(self, recording_id: str) -> dict[str, Any]:
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if not recording.transcript_text:
            raise PermanentError("Transcript is missing.")

        _heartbeat(session, recording, max(recording.progress_pct, 78), minutes_status="creating")
        summary = _complete_local_agent(
            session,
            source="worker.recording.agent.domain_meeting",
            workspace_id=recording.workspace_id,
            messages=_analysis_messages(recording),
            max_tokens=6000,
        )
        return {
            "recording_id": recording.id,
            "summary": summary,
            "agent_flow": ["domain.meeting", "meeting.transcript_summarizer"],
        }
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc), stage="minutes")
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc), stage="minutes")
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
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        transcript = (recording.transcript_text or "").strip()
        summary = str(payload.get("summary") or "").strip()
        if not transcript or not summary:
            raise PermanentError("Transcript summary verification input is missing.")

        verifier_note = _complete_local_agent(
            session,
            source="worker.recording.agent.verifier_grounding",
            workspace_id=recording.workspace_id,
            messages=_verification_messages(transcript, summary),
            max_tokens=2500,
        )
        return {
            "recording_id": recording.id,
            "summary": summary,
            "verifier_note": verifier_note,
            "agent_flow": [
                *list(payload.get("agent_flow") or []),
                "verifier.grounding",
            ],
        }
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc), stage="minutes")
        raise Ignore()
    except TransientError as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc), stage="minutes")
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()


@celery_app.task(
    name="recording.create_minutes_doc",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=300,
)
def create_minutes_doc(self, payload: dict[str, Any]) -> str:
    recording_id = str(payload.get("recording_id") or "")
    session = _db_session()
    try:
        recording = _load_active_recording(session, recording_id)
        if recording is None:
            raise Ignore()
        if recording.minutes_doc_id and recording.minutes_doc_status == "done":
            _heartbeat(session, recording, 100)
            return recording.id
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise PermanentError("Minutes summary is missing.")
        verifier_note = str(payload.get("verifier_note") or "").strip()

        doc = _create_recording_doc(
            session,
            recording=recording,
            title=f"녹음 정리: {_recording_title(recording)}",
            first_page_title="녹음 정리",
            content_blocks=_minutes_blocks(recording, summary, verifier_note),
            source_kind="minutes",
        )
        _attach_minutes_doc_to_meeting(session, recording=recording, doc=doc)
        recording.minutes_doc_id = doc.id
        recording.minutes_doc_status = "done"
        recording.meeting_insight_status = "none"
        recording.progress_pct = 100
        recording.failure_reason = None
        recording.celery_task_id = None
        recording.updated_at = _utcnow()
        session.add(recording)
        session.commit()
        return recording.id
    except Ignore:
        raise
    except PermanentError as exc:
        _mark_failed(session, recording_id, str(exc), stage="minutes")
        raise Ignore()
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            _mark_failed(session, recording_id, str(exc), stage="minutes")
            raise Ignore()
        raise self.retry(exc=exc, countdown=min(600, 2 ** (self.request.retries + 1)))
    finally:
        session.close()
