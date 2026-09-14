import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.domains.hermes import execution, maintenance
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import HermesRunProjection
from open_work_hub_api.domains.hermes.repository import HermesRunRepository, utcnow_naive
from test_hermes_runtime import seed, session_for, stage


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
