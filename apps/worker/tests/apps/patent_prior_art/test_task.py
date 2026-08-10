from __future__ import annotations

from types import SimpleNamespace

import pytest
from celery.exceptions import Ignore

from open_alm_worker.queue_contract import (
    PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_RECOVER_TASK_NAME,
    PATENT_PRIOR_ART_REPUBLISH_TASK_NAME,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
)
from open_alm_worker.tasks.apps.patent_prior_art import task as task_module


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id="job-1",
        workspace_id="workspace-1",
        owner_id="user-1",
        execution_id="execution-1",
    )


def _job_input() -> SimpleNamespace:
    return SimpleNamespace(
        title="Vehicle system",
        invention_text="A sufficiently detailed generic vehicle invention description.",
        technology_summary="Reviewed vehicle thermal-control summary.",
        jurisdictions=["KR"],
        search_plan=object(),
    )


def _install_happy_service(monkeypatch: pytest.MonkeyPatch):
    session = _Session()
    row = _job()
    stages: list[tuple[str, int]] = []
    persisted: list[object] = []
    monkeypatch.setattr(task_module, "_db_session", lambda: session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "claim_job",
        lambda _db, *, job_id, task_id: row if job_id == row.id else None,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "load_job_input",
        lambda _row: _job_input(),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "can_execute_job",
        lambda _db, _row, *, execution_id: True,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "update_stage",
        lambda _db, _row, *, execution_id, stage, progress_percent: (
            stages.append((stage, progress_percent)) or True
        ),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "is_cancelled",
        lambda _db, *, job_id, execution_id: False,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "persist_result",
        lambda _db, _row, *, execution_id, result: persisted.append(result),
    )
    return session, row, stages, persisted


def test_task_is_registered_with_platform_contract() -> None:
    assert task_module.run_patent_prior_art_job.name == PATENT_PRIOR_ART_RUN_JOB_TASK_NAME
    assert task_module.run_patent_prior_art_job.acks_late is True
    assert task_module.run_patent_prior_art_job.max_retries == 0
    assert (
        task_module.republish_pending_patent_prior_art_jobs.name
        == PATENT_PRIOR_ART_REPUBLISH_TASK_NAME
    )
    assert task_module.recover_patent_prior_art_jobs.name == PATENT_PRIOR_ART_RECOVER_TASK_NAME
    beat = task_module.celery_app.conf.beat_schedule["recover-patent-prior-art-jobs"]
    assert beat["task"] == PATENT_PRIOR_ART_RECOVER_TASK_NAME
    assert beat["schedule"] == 60.0
    assert beat["options"]["queue"] == PATENT_PRIOR_ART_QUEUE
    assert task_module._HEARTBEAT_INTERVAL_SECONDS == 30.0


def test_republisher_invokes_durable_service_and_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    calls: list[int] = []
    monkeypatch.setattr(task_module, "_db_session", lambda: session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "republish_pending_jobs",
        lambda _db, *, limit: calls.append(limit) or 3,
    )

    assert task_module.republish_pending_patent_prior_art_jobs.run(limit=17) == 3
    assert calls == [17]
    assert session.closed is True


def test_recovery_task_invokes_db_authoritative_service_and_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    calls: list[int] = []
    expected = {"restarted": 1, "failed": 1, "published": 1}
    monkeypatch.setattr(task_module, "_db_session", lambda: session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "recover_jobs",
        lambda _db, *, limit: calls.append(limit) or expected,
    )

    assert task_module.recover_patent_prior_art_jobs.run(limit=23) == expected
    assert calls == [23]
    assert session.closed is True


def test_worker_runs_pipeline_and_persists_result(monkeypatch: pytest.MonkeyPatch) -> None:
    session, row, stages, persisted = _install_happy_service(monkeypatch)
    result = object()

    def run_pipeline(_db, **kwargs):
        assert kwargs["workspace_id"] == row.workspace_id
        assert kwargs["actor_user_id"] == row.owner_id
        assert kwargs["title"] == "Vehicle system"
        assert kwargs["technology_summary"] == ("Reviewed vehicle thermal-control summary.")
        assert kwargs["jurisdictions"] == ["KR"]
        assert kwargs["cancel_callback"]() is False
        kwargs["progress_callback"](58, "ranking")
        kwargs["progress_callback"](100, "completed")
        return result

    monkeypatch.setattr(task_module, "run_patent_prior_art", run_pipeline)

    assert task_module.run_patent_prior_art_job.run(row.id) == row.id
    assert stages == [("ranking", 58), ("persisting", 100)]
    assert persisted == [result]
    assert session.closed is True


def test_worker_starts_and_stops_execution_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    lifecycle: list[tuple[str, str, str]] = []

    class _FakeHeartbeat:
        def __init__(self, *, job_id: str, execution_id: str) -> None:
            lifecycle.append(("created", job_id, execution_id))
            self.job_id = job_id
            self.execution_id = execution_id
            self.lost_event = SimpleNamespace(is_set=lambda: False)

        def start(self) -> None:
            lifecycle.append(("started", self.job_id, self.execution_id))

        def stop(self) -> None:
            lifecycle.append(("stopped", self.job_id, self.execution_id))

    monkeypatch.setattr(task_module, "_ExecutionLeaseHeartbeat", _FakeHeartbeat)
    monkeypatch.setattr(
        task_module,
        "run_patent_prior_art",
        lambda *_args, **_kwargs: object(),
    )

    assert task_module.run_patent_prior_art_job.run(row.id) == row.id
    assert lifecycle == [
        ("created", row.id, row.execution_id),
        ("started", row.id, row.execution_id),
        ("stopped", row.id, row.execution_id),
    ]
    assert session.closed is True


def test_heartbeat_retries_after_transient_db_error_without_losing_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[_Session] = []
    wait_results = iter((False, False, True))
    renew_calls = 0
    heartbeat = task_module._ExecutionLeaseHeartbeat(
        job_id="job-1",
        execution_id="execution-1",
    )
    heartbeat.stop_event = SimpleNamespace(
        wait=lambda interval: next(wait_results),
    )

    def new_session() -> _Session:
        session = _Session()
        sessions.append(session)
        return session

    def renew(_db, *, job_id: str, execution_id: str) -> bool:
        nonlocal renew_calls
        assert (job_id, execution_id) == ("job-1", "execution-1")
        renew_calls += 1
        if renew_calls == 1:
            raise RuntimeError("temporary database interruption")
        return True

    monkeypatch.setattr(task_module, "_db_session", new_session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "renew_execution_lease",
        renew,
    )

    heartbeat._run()

    assert renew_calls == 2
    assert heartbeat.lost_event.is_set() is False
    assert len(sessions) == 2
    assert all(session.closed for session in sessions)


def test_heartbeat_marks_execution_lost_when_fenced_renew_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    heartbeat = task_module._ExecutionLeaseHeartbeat(
        job_id="job-1",
        execution_id="execution-1",
    )
    heartbeat.stop_event = SimpleNamespace(wait=lambda interval: False)
    monkeypatch.setattr(task_module, "_db_session", lambda: session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "renew_execution_lease",
        lambda *_args, **_kwargs: False,
    )

    heartbeat._run()

    assert heartbeat.lost_event.is_set() is True
    assert session.closed is True


def test_worker_ignores_unclaimable_job(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session()
    monkeypatch.setattr(task_module, "_db_session", lambda: session)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "claim_job",
        lambda _db, *, job_id, task_id: None,
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run("stale-job")
    assert session.closed is True


def test_worker_revalidates_access_before_loading_private_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    failures: list[tuple[str, str]] = []
    monkeypatch.setattr(
        task_module.prior_art_service,
        "can_execute_job",
        lambda _db, _row, *, execution_id: False,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "load_job_input",
        lambda _row: pytest.fail("revoked job input must not be loaded"),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda _db, _row, *, execution_id, failure_code: failures.append(
            (execution_id, failure_code)
        ),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert failures == [(row.execution_id, "access_revoked")]
    assert session.closed is True


def test_worker_terminalizes_access_revoked_inside_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, persisted = _install_happy_service(monkeypatch)
    access_results = iter((True, False))
    failures: list[str] = []
    monkeypatch.setattr(
        task_module.prior_art_service,
        "can_execute_job",
        lambda _db, _row, *, execution_id: next(access_results),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda _db, _row, *, execution_id, failure_code: failures.append(failure_code),
    )

    def run_pipeline(_db, **kwargs):
        kwargs["cancel_callback"]()
        return object()

    monkeypatch.setattr(task_module, "run_patent_prior_art", run_pipeline)

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert failures == ["access_revoked"]
    assert persisted == []
    assert session.closed is True


def test_worker_revalidates_access_immediately_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, persisted = _install_happy_service(monkeypatch)
    access_results = iter((True, False))
    failures: list[str] = []
    monkeypatch.setattr(
        task_module.prior_art_service,
        "can_execute_job",
        lambda _db, _row, *, execution_id: next(access_results),
    )
    monkeypatch.setattr(task_module, "run_patent_prior_art", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda _db, _row, *, execution_id, failure_code: failures.append(failure_code),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert failures == ["access_revoked"]
    assert persisted == []
    assert session.closed is True


def test_worker_does_not_mislabel_cancelled_execution_as_access_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    monkeypatch.setattr(
        task_module.prior_art_service,
        "can_execute_job",
        lambda _db, _row, *, execution_id: False,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "is_cancelled",
        lambda _db, *, job_id, execution_id: True,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda *_args, **_kwargs: pytest.fail("cancellation must not be marked failed"),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert session.closed is True


def test_worker_does_not_retry_arbitrary_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    failures: list[str] = []
    monkeypatch.setattr(
        task_module,
        "run_patent_prior_art",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private detail")),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda _db, _row, *, execution_id, failure_code: failures.append(failure_code),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert failures == ["pipeline_failed"]
    assert session.closed is True


def test_worker_schedules_transient_provider_timeout_in_db_without_celery_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    scheduled: list[str] = []

    monkeypatch.setattr(
        task_module,
        "run_patent_prior_art",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            task_module.PatentPriorArtTransientError("provider timeout")
        ),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "schedule_automatic_restart",
        lambda _db, _row, *, execution_id: scheduled.append(execution_id) or True,
    )
    monkeypatch.setattr(
        task_module.run_patent_prior_art_job,
        "retry",
        lambda **_kwargs: pytest.fail("durable retries must not use Celery retry state"),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda *_args, **_kwargs: pytest.fail("the first timeout must wait in DB"),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert scheduled == [row.execution_id]
    assert session.closed is True


def test_worker_marks_timeout_failed_when_db_restart_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    failures: list[str] = []
    monkeypatch.setattr(
        task_module,
        "run_patent_prior_art",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            task_module.PatentPriorArtTransientError("provider timeout")
        ),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "schedule_automatic_restart",
        lambda _db, _row, *, execution_id: False,
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda _db, _row, *, execution_id, failure_code: failures.append(failure_code),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert failures == ["provider_timeout"]
    assert session.closed is True


def test_cancelled_pipeline_does_not_mark_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session, row, _stages, _persisted = _install_happy_service(monkeypatch)
    monkeypatch.setattr(
        task_module,
        "run_patent_prior_art",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            task_module.PatentPriorArtPipelineCancelled()
        ),
    )
    monkeypatch.setattr(
        task_module.prior_art_service,
        "mark_failed",
        lambda *_args, **_kwargs: pytest.fail("cancelled job must not be failed"),
    )

    with pytest.raises(Ignore):
        task_module.run_patent_prior_art_job.run(row.id)
    assert session.closed is True
