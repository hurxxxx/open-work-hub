import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.domains.hermes import execution, maintenance
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import HermesRunProjection
from open_work_hub_api.domains.hermes.repository import HermesRunRepository, utcnow_naive
from test_hermes_runtime import seed, session_for, stage


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [404, 503])
async def test_auxiliary_poll_failure_keeps_sse_events_and_retry_interval(
    application_postgres_dsn, monkeypatch, status_code
):
    clock = [0.0]
    processed = [asyncio.Event(), asyncio.Event()]
    calls = []
    original_append = HermesRunRepository.append_event

    def append(self, run_id, payload, **kwargs):
        result = original_append(self, run_id, payload, **kwargs)
        if payload.get("tool") in {"first", "second"}:
            processed[int(payload["tool"] == "second")].set()
        return result

    class Native:
        def __init__(self, **kwargs):
            pass

        async def create_run(self, *args, **kwargs):
            return {"run_id": "native", "status": "running"}

        async def iter_run_events(self, *args):
            for index, timestamp in enumerate((5.0, 6.0)):
                clock[0] = timestamp
                yield {"event": "tool.completed", "tool": ("first", "second")[index]}
                await processed[index].wait()
            clock[0] = 10.0
            yield {"event": "run.completed", "output": "saved"}

        async def get_run(self, *args):
            calls.append(clock[0])
            raise HermesClientError(operation="get_run", status_code=status_code,
                                    code="hermes.unavailable", message="Unavailable")

    monkeypatch.setattr(execution, "HermesRuntimeClient", Native)
    monkeypatch.setattr(execution, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(execution, "hermes_run_access_allowed", lambda *args: True)
    monkeypatch.setattr(HermesRunRepository, "append_event", append)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            run = stage(db, binding, session_for(db, binding))
            db.commit()
            result = await asyncio.wait_for(execution.execute_hermes_run(
                db, run_id=run.id, runtime_base_url="http://fixture.invalid", api_key="fixture",
                request_timeout_seconds=1, lease_seconds=60,
            ), 3)
            assert result == "completed" and run.output_text == "saved"
            assert all(event.is_set() for event in processed)
            assert calls == [5.0, 10.0]
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("admitted_status", ["running", "completed"])
async def test_open_sse_cannot_hide_durable_completion(
    application_postgres_dsn, monkeypatch, admitted_status
):
    closed = asyncio.Event()

    class Native:
        def __init__(self, **kwargs):
            pass

        async def create_run(self, *args, **kwargs):
            return {"run_id": "run_fixture", "status": admitted_status}

        async def iter_run_events(self, *args):
            try:
                yield {"event": "tool.completed", "tool": "terminal"}
                await asyncio.Event().wait()
            finally:
                closed.set()

        async def get_run(self, *args):
            # A stale event label must not override the authoritative status.
            return {"status": "completed", "last_event": "tool.completed", "output": "saved"}

    monkeypatch.setattr(execution, "HermesRuntimeClient", Native)
    monkeypatch.setattr(execution, "STATUS_POLL_SECONDS", 0)
    monkeypatch.setattr(execution, "hermes_run_access_allowed", lambda *args: True)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            run = stage(db, binding, session_for(db, binding))
            db.commit()
            result = await asyncio.wait_for(
                execution.execute_hermes_run(
                    db,
                    run_id=run.id,
                    runtime_base_url="http://fixture.invalid",
                    api_key="fixture",
                    request_timeout_seconds=1,
                    lease_seconds=60,
                ),
                3,
            )
            assert result == "completed" and run.output_text == "saved"
            assert run.execution_claim_token is None
            assert closed.is_set() == (admitted_status == "running")
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [404, 503])
async def test_unreachable_old_runs_cannot_starve_a_later_completed_run(
    application_postgres_dsn, monkeypatch, status_code
):
    class Native:
        async def get_run(self, profile, run_id):
            if run_id != "native-completed":
                raise HermesClientError(
                    operation="get_run", status_code=status_code,
                    code="hermes.unavailable", message="Unavailable",
                )
            return {"status": "completed", "output": "recovered"}

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine)
    monkeypatch.setattr(maintenance, "get_session_factory", lambda: factory)
    monkeypatch.setattr(maintenance, "runtime_client", Native)
    try:
        with factory() as db:
            _, binding = seed(db)
            repo = HermesRunRepository(db)
            ids = []
            for index in range(6):
                run = stage(db, binding, session_for(db, binding))
                assert repo.claim_execution(run.id, claim_token="worker", lease_seconds=3600).acquired
                repo.attach_hermes_run(run.id, claim_token="worker", status="running", hermes_run_id=(
                    "native-completed" if index == 5 else f"unreachable-{index}"
                ))
                run.updated_at = utcnow_naive() - timedelta(minutes=10 - index)
                ids.append(run.id)
            db.commit()
        assert await maintenance._reconcile_finished_runs(limit=5) == (0, 5)
        assert await maintenance._reconcile_finished_runs(limit=5) == (1, 4)
        with factory() as db:
            for run_id in ids[:5]:
                run = db.get(HermesRunProjection, run_id)
                assert run.status == "running" and run.finished_at is None
                assert run.execution_claim_token == "worker"
            recovered = db.get(HermesRunProjection, ids[5])
            assert recovered.status == "completed" and recovered.output_text == "recovered"
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("native_status", ["completed", "failed", "running", "unavailable"])
async def test_recovery_reconciles_terminal_native_status_during_a_worker_lease(
    application_postgres_dsn,
    monkeypatch,
    native_status,
):
    class Native:
        async def get_run(self, *args):
            if native_status == "unavailable":
                raise HermesClientError(
                    operation="get_run",
                    status_code=503,
                    code="hermes.unavailable",
                    message="Unavailable",
                )
            return {"status": native_status, "last_event": "tool.completed", "output": "saved"}

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine)
    monkeypatch.setattr(maintenance, "get_session_factory", lambda: factory)
    monkeypatch.setattr(maintenance, "runtime_client", Native)
    try:
        with factory() as db:
            _, binding = seed(db)
            run = stage(db, binding, session_for(db, binding))
            repo = HermesRunRepository(db)
            assert repo.claim_execution(run.id, claim_token="worker", lease_seconds=3600).acquired
            repo.attach_hermes_run(run.id, claim_token="worker", hermes_run_id="run_fixture")
            run.updated_at = utcnow_naive() - timedelta(minutes=5)
            run_id = run.id
            db.commit()
        count, failures = await maintenance._reconcile_finished_runs(limit=5)
        terminal = native_status in {"completed", "failed"}
        assert count == int(terminal)
        assert failures == int(native_status == "unavailable")
        with factory() as db:
            run = db.get(HermesRunProjection, run_id)
            if terminal:
                assert run.status == native_status
                assert run.finished_at is not None and run.execution_claim_token is None
                HermesRunRepository(db).append_event(run_id, {"event": "tool.completed"})
                db.commit()
                assert run.status == native_status
            else:
                assert run.status not in {"completed", "failed"}
                assert run.execution_claim_token == "worker"
    finally:
        engine.dispose()
