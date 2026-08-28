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
        workspace_id="workspace-1",
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
            marked.append((status, last_error))
            if current_job is job
            else None
        ),
    )
    monkeypatch.setattr(
        rag_sync,
        "_process_sync_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled RAG job reached provider mutation")
        ),
    )

    assert rag_sync._execute_sync_job(
        object(),
        task=object(),
        job=job,
        span_name="test.rag",
        job_kind="resource_sync",
        rag_enabled=True,
    ) == "app-disabled"
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
        workspace_id="workspace-1",
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
            marked.append((status, last_error))
            if current_job is job
            else None
        ),
    )
    monkeypatch.setattr(
        rag_sync,
        "_process_visibility_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled visibility job enqueued resources")
        ),
    )

    assert rag_sync._execute_visibility_job(
        object(),
        task=object(),
        job=job,
        rag_enabled=True,
    ) == "app-disabled"
    assert job.attempts == 0
    assert marked == [("pending", "app_disabled:docs")]


def test_recording_worker_marks_stage_failed_before_provider_io(monkeypatch) -> None:
    current_recording = SimpleNamespace(
        id="recording-1",
        owner_id="user-1",
        workspace_id="workspace-1",
    )
    marked: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        recording,
        "is_app_enabled_for_user_context",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        recording,
        "_mark_failed",
        lambda _session, recording_id, reason, *, stage: marked.append(
            (recording_id, reason, stage)
        ),
    )

    with pytest.raises(Ignore):
        recording._ensure_recording_execution_allowed(
            object(),
            current_recording,
            stage="transcript",
        )

    assert marked == [
        (
            "recording-1",
            "Recording app execution disabled or requester membership revoked.",
            "transcript",
        )
    ]


def test_meeting_worker_marks_failed_before_provider_io(monkeypatch) -> None:
    current_recording = SimpleNamespace(
        id="meeting-recording-1",
        meeting=SimpleNamespace(workspace_id="workspace-1"),
        uploaded_by_id="user-1",
    )
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        meeting,
        "is_app_enabled_for_user_context",
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
