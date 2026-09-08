from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from celery.exceptions import Ignore

from open_work_hub_worker.tasks import meeting, rag_sync, recording


def _rag_sync_job() -> SimpleNamespace:
    return SimpleNamespace(
        attempts=1,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        id="rag-job-1",
        lane="realtime",
        operation="upsert",
        resource_id="resource-1",
        resource_type="native_doc",
        trace_context=None,
    )


def test_rag_sync_rechecks_app_before_provider_mutation(monkeypatch) -> None:
    job = _rag_sync_job()
    marked: list[tuple[str, str | None]] = []
    monkeypatch.setattr(rag_sync, "record_sync_job_lag", lambda **_kwargs: None)
    monkeypatch.setattr(rag_sync, "record_sync_job_result", lambda **_kwargs: None)
    monkeypatch.setattr(rag_sync, "start_as_current_span", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        rag_sync,
        "_disabled_app_id_for_job",
        lambda _session, current_job: "docs" if current_job is job else None,
    )
    monkeypatch.setattr(
        rag_sync,
        "_mark_sync_job",
        lambda _session, current_job, *, status, last_error=None, **_kwargs: (
            marked.append((status, last_error)) if current_job is job else None
        ),
    )
    monkeypatch.setattr(
        rag_sync,
        "_process_sync_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled RAG job reached provider mutation")
        ),
    )

    assert (
        rag_sync._execute_sync_job(
            object(),
            task=object(),
            job=job,
            span_name="test.rag",
            job_kind="resource_sync",
            rag_enabled=True,
        )
        == "app-disabled"
    )
    assert job.attempts == 0
    assert marked == [("pending", "app_disabled:docs")]


def test_rag_visibility_rechecks_app_before_enqueuing_resources(monkeypatch) -> None:
    job = SimpleNamespace(
        attempts=1,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        id="visibility-job-1",
        scope_id="group-1",
        scope_type="group",
        trace_context=None,
    )
    marked: list[tuple[str, str | None]] = []
    monkeypatch.setattr(rag_sync, "record_sync_job_lag", lambda **_kwargs: None)
    monkeypatch.setattr(rag_sync, "record_sync_job_result", lambda **_kwargs: None)
    monkeypatch.setattr(rag_sync, "start_as_current_span", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        rag_sync,
        "_disabled_app_id_for_visibility_job",
        lambda _session, current_job: "docs" if current_job is job else None,
    )
    monkeypatch.setattr(
        rag_sync,
        "_mark_visibility_job",
        lambda _session, current_job, *, status, last_error=None, **_kwargs: (
            marked.append((status, last_error)) if current_job is job else None
        ),
    )
    monkeypatch.setattr(
        rag_sync,
        "_process_visibility_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled visibility job enqueued resources")
        ),
    )

    assert (
        rag_sync._execute_visibility_job(
            object(),
            task=object(),
            job=job,
            rag_enabled=True,
        )
        == "app-disabled"
    )
    assert job.attempts == 0
    assert marked == [("pending", "app_disabled:docs")]


def test_recording_worker_marks_stage_failed_before_provider_io(monkeypatch) -> None:
    current_recording = SimpleNamespace(
        celery_task_id="attempt-1",
        id="recording-1",
        owner_id="user-1",
    )
    marked: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        recording,
        "can_use_app",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        recording,
        "_mark_failed",
        lambda _session, recording_id, reason, *, stage, expected_attempt_id: marked.append(
            (recording_id, reason, stage)
        ),
    )

    with pytest.raises(Ignore):
        recording._ensure_recording_execution_allowed(
            object(),
            current_recording,
            stage="transcript",
            expected_attempt_id="attempt-1",
        )

    assert marked == [
        (
            "recording-1",
            "Recording app execution disabled or requester membership revoked.",
            "transcript",
        )
    ]


def test_recording_heartbeat_mutates_only_the_locked_current_attempt(monkeypatch) -> None:
    stale = SimpleNamespace(id="recording-1", progress_pct=10)
    current = SimpleNamespace(
        id="recording-1",
        progress_pct=20,
        summary_status="pending",
        transcript_status="pending",
        updated_at=None,
    )
    added: list[object] = []

    class FakeSession:
        def add(self, value: object) -> None:
            added.append(value)

        def commit(self) -> None:
            pass

    monkeypatch.setattr(
        recording,
        "_lock_current_recording_attempt",
        lambda _session, recording_id, attempt_id: (
            current
            if recording_id == "recording-1" and attempt_id == "attempt-current"
            else (_ for _ in ()).throw(recording.SupersededRecordingGeneration())
        ),
    )

    recording._heartbeat(
        FakeSession(),
        stale,
        45,
        expected_attempt_id="attempt-current",
        transcript_status="transcribing",
    )

    assert stale.progress_pct == 10
    assert current.progress_pct == 45
    assert current.transcript_status == "transcribing"
    assert current.updated_at is not None
    assert added == [current]


def test_recording_worker_persists_result_without_publication_side_effect(
    monkeypatch,
) -> None:
    result = SimpleNamespace(
        generated_at=None,
        summary_text="Grounded summary",
        updated_at=None,
        verifier_note=None,
        version=3,
    )
    current_recording = SimpleNamespace(
        celery_task_id="task-1",
        failure_reason="old failure",
        id="recording-1",
        meeting_insight_status="pending",
        progress_pct=94,
        result=result,
        summary_status="verifying",
        updated_at=None,
    )
    added: list[object] = []

    class FakeSession:
        def add(self, value: object) -> None:
            added.append(value)

        def close(self) -> None:
            pass

        def commit(self) -> None:
            pass

    session = FakeSession()
    monkeypatch.setattr(recording, "_db_session", lambda: session)
    monkeypatch.setattr(
        recording,
        "_load_active_recording",
        lambda _session, recording_id: (
            current_recording if recording_id == current_recording.id else None
        ),
    )
    monkeypatch.setattr(
        recording,
        "_lock_current_recording_attempt",
        lambda _session, recording_id, attempt_id: (
            current_recording
            if recording_id == current_recording.id and attempt_id == "task-1"
            else (_ for _ in ()).throw(recording.SupersededRecordingGeneration())
        ),
    )
    monkeypatch.setattr(
        recording,
        "_ensure_recording_execution_allowed",
        lambda *_args, **_kwargs: None,
    )

    assert (
        recording.persist_recording_result.run(
            {
                "recording_id": current_recording.id,
                "attempt_id": "task-1",
                "result_version": 3,
                "summary": "Grounded summary",
                "verifier_note": "Verified",
            }
        )
        == current_recording.id
    )

    assert added == [result, current_recording]
    assert result.verifier_note == "Verified"
    assert result.generated_at is not None
    assert current_recording.summary_status == "done"
    assert current_recording.meeting_insight_status == "none"
    assert current_recording.progress_pct == 100
    assert current_recording.failure_reason is None
    assert current_recording.celery_task_id is None


def test_recording_worker_rejects_stale_result_version(monkeypatch) -> None:
    current_recording = SimpleNamespace(
        celery_task_id="task-v4",
        failure_reason=None,
        id="recording-1",
        result=SimpleNamespace(summary_text="Current summary", version=4),
        summary_status="verifying",
    )
    marked: list[tuple[str, str, str]] = []

    class FakeSession:
        def close(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    session = FakeSession()
    monkeypatch.setattr(recording, "_db_session", lambda: session)
    monkeypatch.setattr(
        recording,
        "_load_active_recording",
        lambda *_args: current_recording,
    )
    monkeypatch.setattr(
        recording,
        "_lock_current_recording_attempt",
        lambda *_args: current_recording,
    )
    monkeypatch.setattr(
        recording,
        "_ensure_recording_execution_allowed",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        recording,
        "_mark_failed",
        lambda _session, recording_id, reason, *, stage, expected_attempt_id: marked.append(
            (recording_id, reason, stage)
        ),
    )

    with pytest.raises(Ignore):
        recording.persist_recording_result.run(
            {
                "recording_id": current_recording.id,
                "attempt_id": "task-v4",
                "result_version": 3,
                "summary": "Current summary",
            }
        )

    assert marked == []
    assert current_recording.summary_status == "verifying"
    assert current_recording.celery_task_id == "task-v4"
    assert current_recording.failure_reason is None


def test_meeting_worker_marks_failed_before_provider_io(monkeypatch) -> None:
    current_recording = SimpleNamespace(
        id="meeting-recording-1",
        meeting=SimpleNamespace(id="meeting-1"),
        uploaded_by_id="user-1",
    )
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        meeting,
        "can_use_app",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        meeting,
        "_mark_failed",
        lambda _session, recording_id, reason: marked.append((recording_id, reason)),
    )

    with pytest.raises(Ignore):
        meeting._ensure_meeting_execution_allowed(object(), current_recording)

    assert marked == [
        (
            "meeting-recording-1",
            "Meeting app execution disabled or requester membership revoked.",
        )
    ]
