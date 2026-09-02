from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.settings import (
    HERMES_FALLBACK_MODEL,
    HERMES_MODEL,
    HERMES_PROVIDER,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes import mcp_router
from open_work_hub_api.domains.hermes import maintenance as hermes_maintenance
from open_work_hub_api.domains.hermes import router as hermes_router
from open_work_hub_api.domains.hermes import service as hermes_service
from open_work_hub_api.domains.hermes.client import (
    HermesClientError,
    HermesManagementClient,
    HermesRuntimeClient,
)
from open_work_hub_api.domains.hermes.models import (
    HermesDispatchOutbox,
    HermesMaintenanceState,
    HermesProfileBinding,
    HermesRunEvent,
    HermesRunInput,
    HermesRunProjection,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.repository import (
    HermesDispatchRepository,
    HermesRunIdempotencyConflict,
    HermesRunRepository,
    sanitize_event_payload,
    utcnow_naive,
)
from open_work_hub_api.domains.hermes.research_sources import (
    DEFAULT_RESEARCH_SOURCE_POLICY,
)
from open_work_hub_api.domains.hermes.schemas import HermesApprovalDecision, HermesRunCreate
from open_work_hub_api.domains.hermes.service import (
    ensure_job_profile,
    internal_mcp_server_name,
    is_profile_scoped_mcp_server,
    job_profile_name,
    mcp_profile_bearer_secret,
    scoped_mcp_server_name,
)


pytestmark = pytest.mark.anyio


def test_stage_persists_run_before_foreign_key_children(
    application_postgres_dsn: str,
) -> None:
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            suffix = uuid4().hex
            workspace = Workspace(
                id=str(uuid4()),
                key=f"hermes-stage-{suffix[:16]}",
                name="Hermes stage test",
            )
            user = User(
                id=str(uuid4()),
                login_id=f"hermes-stage-{suffix[:16]}",
                email=f"hermes-stage-{suffix[:16]}@example.test",
                full_name="Hermes Stage Test",
                password_hash="not-used",
            )
            db.add_all([workspace, user])
            db.flush()

            binding = HermesProfileBinding(
                id=str(uuid4()),
                workspace_id=workspace.id,
                user_id=user.id,
                profile_name=f"owh-test-{suffix[:32]}",
                status="active",
                provider=HERMES_PROVIDER,
                model=HERMES_MODEL,
            )
            db.add(binding)
            db.flush()

            run = HermesRunRepository(db).stage(
                binding=binding,
                session=None,
                input_text="Verify atomic run staging",
                instructions=None,
                conversation_history=[],
                client_request_id="request-1",
                request_sha256="a" * 64,
            )

            assert db.get(HermesRunProjection, run.id) is run
            assert db.get(HermesRunInput, run.id) is not None
            assert (
                db.scalar(select(HermesDispatchOutbox).where(HermesDispatchOutbox.run_id == run.id))
                is not None
            )
            assert (
                db.scalar(select(HermesRunEvent).where(HermesRunEvent.run_id == run.id)) is not None
            )
            replay = HermesRunRepository(db).stage(
                binding=binding,
                session=None,
                input_text="Verify atomic run staging",
                instructions=None,
                conversation_history=[],
                client_request_id="request-1",
                request_sha256="a" * 64,
            )
            assert replay.id == run.id
            with pytest.raises(HermesRunIdempotencyConflict):
                HermesRunRepository(db).stage(
                    binding=binding,
                    session=None,
                    input_text="Different request",
                    instructions=None,
                    conversation_history=[],
                    client_request_id="request-1",
                    request_sha256="b" * 64,
                )

            outbox = db.scalar(
                select(HermesDispatchOutbox).where(HermesDispatchOutbox.run_id == run.id)
            )
            assert outbox is not None
            outbox.status = "dispatched"
            outbox.dispatched_at = utcnow_naive() - timedelta(minutes=5)
            db.add(outbox)
            db.flush()
            assert HermesDispatchRepository(db).requeue_stale_dispatched(limit=1) == 1
            assert outbox.status == "pending"
            assert outbox.celery_task_id is None
            db.rollback()
    finally:
        engine.dispose()


async def test_headless_maintenance_records_a_durable_heartbeat_without_work(
    application_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(hermes_maintenance, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        hermes_maintenance,
        "get_settings",
        lambda: SimpleNamespace(hermes_terminal_artifact_retention_days=30),
    )
    try:
        counters = await hermes_maintenance.maintain_headless_hermes_once(limit=1)

        assert counters == {
            "expired_approvals": 0,
            "revoked_runs_claimed": 0,
            "revoked_runs_stopped": 0,
            "revoked_jobs_paused": 0,
            "events_deleted": 0,
            "errors": 0,
        }
        with Session(engine) as db:
            state = db.get(HermesMaintenanceState, "headless")
            assert state is not None
            assert state.last_started_at is not None
            assert state.last_succeeded_at is not None
            assert state.last_error_code is None
            assert state.counters == counters
    finally:
        engine.dispose()


async def test_headless_maintenance_skips_while_another_lease_is_live(
    application_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(hermes_maintenance, "get_session_factory", lambda: factory)
    lease_started_at = utcnow_naive()
    try:
        with Session(engine) as db:
            db.add(
                HermesMaintenanceState(
                    component="headless",
                    counters={"previous": 1},
                    lease_token="active-maintenance-lease",
                    lease_expires_at=lease_started_at + timedelta(minutes=1),
                    last_started_at=lease_started_at,
                )
            )
            db.commit()

        assert await hermes_maintenance.maintain_headless_hermes_once(limit=1) == {
            "maintenance_skipped": 1,
            "errors": 0,
        }

        with Session(engine) as db:
            state = db.get(HermesMaintenanceState, "headless")
            assert state is not None
            assert state.lease_token == "active-maintenance-lease"
            assert state.counters == {"previous": 1}
            assert state.last_started_at == lease_started_at
    finally:
        engine.dispose()


def test_revoked_run_scan_advances_past_authorized_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(run_scan_cursor=None)
    authorized = [
        SimpleNamespace(
            id=f"00000000-0000-0000-0000-{index:012d}",
            user_id=f"allowed-{index}",
            workspace_id="workspace-1",
            status="running",
            execution_claim_token=None,
            execution_claim_expires_at=None,
            hermes_run_id=f"remote-{index}",
            profile_binding_id=f"profile-{index}",
        )
        for index in range(1, 6)
    ]
    revoked = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000006",
        user_id="revoked-user",
        workspace_id="workspace-1",
        status="running",
        execution_claim_token=None,
        execution_claim_expires_at=None,
        hermes_run_id="remote-revoked",
        profile_binding_id="profile-revoked",
    )
    pages = iter([authorized, [revoked]])
    appended: list[str] = []

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalars(self, _statement):
            return iter(next(pages))

        def get(self, _model, binding_id: str):
            return SimpleNamespace(profile_name=f"name-{binding_id}")

        def add(self, _value):
            return None

        def commit(self):
            return None

    class FakeRepository:
        def __init__(self, _db):
            pass

        def append_event(self, run_id: str, _payload):
            appended.append(run_id)

    monkeypatch.setattr(
        hermes_maintenance,
        "get_session_factory",
        lambda: lambda: FakeDb(),
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "_maintenance_state_for_update",
        lambda _db: state,
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "is_app_enabled_for_user_context",
        lambda _db, **kwargs: kwargs["user_id"] != "revoked-user",
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "HermesRunRepository",
        FakeRepository,
    )

    assert hermes_maintenance._claim_revoked_runs(limit=1) == []
    assert state.run_scan_cursor == authorized[-1].id
    assert hermes_maintenance._claim_revoked_runs(limit=1) == [
        (revoked.id, "name-profile-revoked", "remote-revoked")
    ]
    assert appended == [revoked.id]


async def test_revoked_job_scan_advances_past_authorized_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace(job_scan_cursor=None)
    authorized = [
        SimpleNamespace(
            id=f"10000000-0000-0000-0000-{index:012d}",
            user_id=f"allowed-{index}",
            workspace_id="workspace-1",
            status="active",
            profile_binding_id=f"profile-{index}",
            hermes_job_id=f"remote-job-{index}",
            updated_at=utcnow_naive(),
        )
        for index in range(1, 6)
    ]
    revoked = SimpleNamespace(
        id="10000000-0000-0000-0000-000000000006",
        user_id="revoked-user",
        workspace_id="workspace-1",
        status="active",
        profile_binding_id="profile-revoked",
        hermes_job_id="remote-job-revoked",
        updated_at=utcnow_naive(),
    )
    pages = iter([authorized, [revoked]])
    paused: list[tuple[str, str, str]] = []

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalars(self, _statement):
            return iter(next(pages))

        def scalar(self, _statement):
            return revoked

        def get(self, _model, binding_id: str):
            return SimpleNamespace(profile_name=f"name-{binding_id}")

        def add(self, _value):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeClient:
        async def job_action(self, profile_name: str, job_id: str, action: str):
            paused.append((profile_name, job_id, action))

    monkeypatch.setattr(
        hermes_maintenance,
        "get_session_factory",
        lambda: lambda: FakeDb(),
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "_maintenance_state_for_update",
        lambda _db: state,
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "is_app_enabled_for_user_context",
        lambda _db, **kwargs: kwargs["user_id"] != "revoked-user",
    )
    monkeypatch.setattr(
        hermes_maintenance,
        "runtime_client",
        lambda: FakeClient(),
    )

    assert await hermes_maintenance._pause_revoked_jobs(limit=1) == (0, 0)
    assert state.job_scan_cursor == authorized[-1].id
    assert await hermes_maintenance._pause_revoked_jobs(limit=1) == (1, 0)
    assert revoked.status == "paused"
    assert paused == [("name-profile-revoked-jobs", "remote-job-revoked", "pause")]


async def test_expired_approval_without_a_remote_run_fails_the_local_run(
    application_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(hermes_maintenance, "get_session_factory", lambda: factory)

    def unexpected_runtime_client():
        raise AssertionError("A local-only expiry must not initialize Hermes")

    monkeypatch.setattr(
        hermes_maintenance,
        "runtime_client",
        unexpected_runtime_client,
    )
    suffix = uuid4().hex
    workspace = Workspace(
        id=str(uuid4()),
        key=f"hermes-expired-{suffix[:16]}",
        name="Hermes expired approval",
    )
    user = User(
        id=str(uuid4()),
        login_id=f"hermes-expired-{suffix[:16]}",
        email=f"hermes-expired-{suffix[:16]}@example.test",
        full_name="Hermes Expired Approval",
        password_hash="not-used",
    )
    binding = HermesProfileBinding(
        id=str(uuid4()),
        workspace_id=workspace.id,
        user_id=user.id,
        profile_name=f"owh-expired-{suffix[:24]}",
        status="active",
        provider=HERMES_PROVIDER,
        model=HERMES_MODEL,
    )
    try:
        with Session(engine) as db:
            db.add_all([workspace, user, binding])
            db.flush()
            run = HermesRunRepository(db).stage(
                binding=binding,
                session=None,
                input_text="Wait for approval",
                instructions=None,
                conversation_history=[],
            )
            run.status = "awaiting_approval"
            run.pending_approval = {"request_id": "approval-1"}
            approval = HermesToolApproval(
                id=str(uuid4()),
                run_id=run.id,
                request_id="approval-1",
                status="pending",
                request_payload={"tool": "shell"},
                expires_at=utcnow_naive() - timedelta(seconds=1),
            )
            db.add_all([run, approval])
            db.commit()
            run_id = run.id
            approval_id = approval.id

        assert await hermes_maintenance._expire_approvals(limit=1) == (1, 0)

        with Session(engine) as db:
            stored_run = db.get(HermesRunProjection, run_id)
            stored_approval = db.get(HermesToolApproval, approval_id)
            assert stored_run is not None
            assert stored_run.status == "failed"
            assert stored_run.error_code == "hermes.remote_run_missing"
            assert stored_approval is not None
            assert stored_approval.status == "expired"
            assert stored_approval.choice == "deny"
    finally:
        engine.dispose()


async def test_runtime_client_uses_profile_route_auth_and_run_idempotency() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={"run_id": "run-1", "status": "queued"},
        )

    client = HermesRuntimeClient(
        base_url="http://hermes.test",
        api_key="runtime-secret-0000000000000001",
        transport=httpx.MockTransport(handler),
    )
    result = await client.create_run(
        "profile/with slash",
        input_text="Handle this task",
        session_id="session-1",
        idempotency_key="owh-run-1",
        instructions="Use the approved tools.",
        conversation_history=[{"role": "user", "content": "Earlier"}],
    )

    assert result == {"run_id": "run-1", "status": "queued"}
    request = requests[0]
    assert request.url.raw_path == b"/p/profile%2Fwith%20slash/v1/runs"
    assert request.headers["authorization"] == "Bearer runtime-secret-0000000000000001"
    assert request.headers["idempotency-key"] == "owh-run-1"
    assert request.headers["x-hermes-session-id"] == "session-1"
    assert json.loads(request.content) == {
        "input": "Handle this task",
        "session_id": "session-1",
        "instructions": "Use the approved tools.",
        "conversation_history": [{"role": "user", "content": "Earlier"}],
    }


async def test_runtime_client_parses_multiline_sse_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/p/profile-1/v1/runs/run-1/events"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b"event: content.delta\n"
                b'data: {"event":"content.delta",\n'
                b'data: "delta":"hello"}\n\n'
                b'data: {"event":"run.completed","status":"completed"}\n\n'
            ),
        )

    client = HermesRuntimeClient(
        base_url="http://hermes.test",
        api_key="runtime-secret-0000000000000001",
        transport=httpx.MockTransport(handler),
    )

    events = [event async for event in client.iter_run_events("profile-1", "run-1")]

    assert events == [
        {"event": "content.delta", "delta": "hello"},
        {"event": "run.completed", "status": "completed"},
    ]


async def test_management_client_pins_openrouter_model_and_dashboard_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"ok": True})

    client = HermesManagementClient(
        base_url="http://dashboard.test",
        session_token="dashboard-secret-00000000000001",
        transport=httpx.MockTransport(handler),
    )
    await client.create_profile(
        profile_name="owh-profile",
        clone_from="default",
        description="isolated profile",
        mcp_servers=[{"name": "open-work-hub", "url": "http://api/mcp"}],
    )

    request = requests[0]
    assert request.url.path == "/api/profiles"
    assert request.headers["x-hermes-session-token"] == ("dashboard-secret-00000000000001")
    assert json.loads(request.content) == {
        "name": "owh-profile",
        "clone_from": "default",
        "description": "isolated profile",
        "provider": HERMES_PROVIDER,
        "model": HERMES_MODEL,
        "mcp_servers": [{"name": "open-work-hub", "url": "http://api/mcp"}],
    }


async def test_management_client_applies_managed_resilience_policy() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = HermesManagementClient(
        base_url="http://dashboard.test",
        session_token="dashboard-secret-00000000000001",
        transport=httpx.MockTransport(handler),
    )
    await client.set_profile_model("owh/profile")

    assert [request.url.raw_path for request in requests] == [
        b"/api/profiles/owh%2Fprofile/model",
        b"/api/config",
    ]
    assert json.loads(requests[0].content) == {
        "provider": HERMES_PROVIDER,
        "model": HERMES_MODEL,
    }
    policy_request = json.loads(requests[1].content)
    assert policy_request["profile"] == "owh/profile"
    policy = policy_request["config"]
    assert policy == {
        "model": {
            "default_headers": {"X-OpenRouter-Metadata": "enabled"},
        },
        "fallback_providers": [{"provider": HERMES_PROVIDER, "model": HERMES_FALLBACK_MODEL}],
        "agent": {
            "api_max_retries": 1,
            "environment_hint": (
                "Academic research source policy: Semantic Scholar is disabled. "
                "Do not access or cite disabled sources, including through generic "
                "web search. Enabled sources: arXiv, OpenAlex, Crossref."
            ),
        },
        "compression": {
            "enabled": True,
            "threshold": 0.50,
            "threshold_tokens": 100_000,
            "target_ratio": 0.20,
            "protect_last_n": 20,
            "proactive_prune_tokens": 48_000,
            "proactive_prune_min_result_chars": 8_000,
            "proactive_prune_min_reclaim_tokens": 4_096,
        },
        "provider_routing": {
            "sort": "throughput",
            "require_parameters": True,
        },
        "auxiliary": {
            "free_only": False,
            "openrouter_model": HERMES_MODEL,
        },
    }


def test_run_scope_normalizes_app_ids_and_mcp_filters_with_it(monkeypatch) -> None:
    body = HermesRunCreate(
        input="Do work",
        allowed_app_ids=[" Files ", "mail", "files", ""],
    )
    assert body.allowed_app_ids == ["files", "mail"]

    captured: dict[str, Any] = {}

    class FakeMcpClient:
        def list_tools(self, _db, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(mcp_router, "AiMcpClient", FakeMcpClient)
    db = SimpleNamespace(
        scalar=lambda _query: SimpleNamespace(allowed_app_ids=body.allowed_app_ids)
    )
    binding = SimpleNamespace(id="binding-1")
    workspace = SimpleNamespace(id="workspace-1")
    user = SimpleNamespace(id="user-1")

    _principal, tools, active_run = mcp_router._available_tools(
        db,
        binding=binding,
        workspace=workspace,
        user=user,
    )

    assert tools == []
    assert active_run.allowed_app_ids == ["files", "mail"]
    assert captured["app_ids"] == ["files", "mail"]
    assert captured["include_approval_required"] is True


def test_mcp_discovery_surface_is_stable_across_run_app_scopes(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeMcpClient:
        def list_tools(self, _db, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(mcp_router, "AiMcpClient", FakeMcpClient)
    active_run = SimpleNamespace(allowed_app_ids=["files"])
    db = SimpleNamespace(scalar=lambda _query: active_run)

    _mcp_router_principal, tools, resolved_run = mcp_router._available_tools(
        db,
        binding=SimpleNamespace(id="binding-1"),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        apply_run_scope=False,
    )

    assert tools == []
    assert resolved_run is active_run
    assert captured["app_ids"] is None


def test_mcp_tool_surface_requires_an_active_scoped_run(monkeypatch) -> None:
    class UnexpectedMcpClient:
        def list_tools(self, _db, **_kwargs):
            raise AssertionError("Tools must not be listed without an active run")

    monkeypatch.setattr(mcp_router, "AiMcpClient", UnexpectedMcpClient)
    db = SimpleNamespace(scalar=lambda _query: None)

    with pytest.raises(HTTPException) as error:
        mcp_router._available_tools(
            db,
            binding=SimpleNamespace(id="binding-1"),
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-1"),
        )

    assert error.value.status_code == 409
    assert error.value.detail == {"code": "hermes.active_run_required"}


def _mcp_approval_payload(profile_name: str, tool_name: str) -> dict[str, Any]:
    return {
        "command": (
            f"MCP tool '{tool_name}' on UNTRUSTED server "
            f"'{internal_mcp_server_name(profile_name)}' wants to run. This tool is "
            "write-capable (no readOnlyHint=true annotation) and may modify external "
            "state."
        ),
        "description": "Approve this tool once.",
        "pattern_key": "mcp_elicitation",
        "pattern_keys": ["mcp_elicitation"],
        "request_id": "approval-1",
    }


def test_mcp_write_approval_matches_the_exact_hermes_trust_prompt() -> None:
    profile_name = "owh-profile-a"
    approval = SimpleNamespace(request_payload=_mcp_approval_payload(profile_name, "tasks.create"))

    assert mcp_router._approval_matches_mcp_tool(
        approval,
        profile_name=profile_name,
        tool_name="tasks.create",
    )
    assert not mcp_router._approval_matches_mcp_tool(
        approval,
        profile_name=profile_name,
        tool_name="tasks.delete",
    )

    approval.request_payload = {
        **approval.request_payload,
        "command": approval.request_payload["command"].replace(
            f"server '{internal_mcp_server_name(profile_name)}'",
            "server 'other-server'",
        ),
    }
    assert not mcp_router._approval_matches_mcp_tool(
        approval,
        profile_name=profile_name,
        tool_name="tasks.create",
    )


def test_mcp_write_approval_is_consumed_once_and_bound_to_arguments() -> None:
    approval = SimpleNamespace(
        id="approval-row-1",
        request_payload=_mcp_approval_payload("owh-profile-a", "tasks.create"),
        consumed_at=None,
        consumed_tool_name=None,
        consumed_arguments_sha256=None,
        external_call_id=None,
    )

    class FakeDb:
        def __init__(self) -> None:
            self.commits = 0

        def scalars(self, _query):
            return [approval]

        def add(self, row):
            assert row is approval

        def commit(self):
            self.commits += 1

    db = FakeDb()
    arguments = {"title": "Ship Hermes", "priority": 2}

    external_call_id = mcp_router._consume_external_tool_approval(
        db,
        run_id="run-1",
        profile_name="owh-profile-a",
        tool_name="tasks.create",
        arguments=arguments,
    )

    assert external_call_id is not None
    assert approval.external_call_id == external_call_id
    assert approval.consumed_tool_name == "tasks.create"
    assert approval.consumed_arguments_sha256 == mcp_router._arguments_sha256(arguments)
    assert approval.consumed_at is not None
    assert db.commits == 1
    assert (
        mcp_router._consume_external_tool_approval(
            db,
            run_id="run-1",
            profile_name="owh-profile-a",
            tool_name="tasks.create",
            arguments=arguments,
        )
        is None
    )
    assert db.commits == 1


async def test_approval_is_committed_before_hermes_resumes(monkeypatch) -> None:
    run = SimpleNamespace(
        id="run-1",
        hermes_run_id="hermes-run-1",
    )
    approval = SimpleNamespace(
        id="approval-1",
        status="pending",
        choice=None,
        decided_by_user_id=None,
        decided_at=None,
        consumed_at=None,
    )
    commits: list[str] = []
    events: list[dict[str, Any]] = []

    class FakeDb:
        def scalar(self, _query):
            return approval

        def add(self, _row):
            return None

        def commit(self):
            commits.append(approval.status)

        def rollback(self):
            raise AssertionError("The successful approval path must not roll back")

    class FakeRepository:
        def get_owned(self, *_args, **_kwargs):
            return run

        def append_event(self, _run_id, payload):
            events.append(payload)

        def get(self, _run_id):
            return run

    class FakeRuntimeClient:
        async def resolve_approval(self, *_args, **_kwargs):
            assert commits == ["approved"]
            assert approval.choice == "once"
            assert approval.decided_by_user_id == "user-1"
            assert approval.decided_at is not None
            return {"status": "running", "request_id": "request-1"}

    class FakeResponse:
        @classmethod
        def model_validate(cls, value):
            return value

    async def fake_profile_for_request(*_args, **_kwargs):
        return SimpleNamespace(profile_name="profile-1")

    monkeypatch.setattr(hermes_router, "HermesRunRepository", lambda _db: FakeRepository())
    monkeypatch.setattr(hermes_router, "_profile_for_request", fake_profile_for_request)
    monkeypatch.setattr(hermes_router, "runtime_client", lambda: FakeRuntimeClient())
    monkeypatch.setattr(hermes_router, "HermesRunResponse", FakeResponse)

    result = await hermes_router.resolve_approval(
        "run-1",
        HermesApprovalDecision(request_id="request-1", choice="once"),
        db=FakeDb(),
        current_user=SimpleNamespace(id="user-1"),
        current_workspace=SimpleNamespace(id="workspace-1"),
    )

    assert result is run
    assert commits == ["approved", "approved"]
    assert events == [
        {
            "event": "approval.responded",
            "status": "running",
            "request_id": "request-1",
        }
    ]


async def test_failed_hermes_resume_restores_unconsumed_approval(monkeypatch) -> None:
    run = SimpleNamespace(id="run-1", hermes_run_id="hermes-run-1")
    approval = SimpleNamespace(
        id="approval-1",
        status="pending",
        choice=None,
        decided_by_user_id=None,
        decided_at=None,
        consumed_at=None,
    )
    commits: list[str] = []
    rollbacks = 0

    class FakeDb:
        def scalar(self, _query):
            return approval

        def add(self, _row):
            return None

        def commit(self):
            commits.append(approval.status)

        def rollback(self):
            nonlocal rollbacks
            rollbacks += 1

    class FakeRepository:
        def get_owned(self, *_args, **_kwargs):
            return run

    class FailingRuntimeClient:
        async def resolve_approval(self, *_args, **_kwargs):
            raise HermesClientError(
                operation="resolve approval",
                status_code=503,
                code="hermes.unavailable",
                message="Hermes unavailable",
            )

    async def fake_profile_for_request(*_args, **_kwargs):
        return SimpleNamespace(profile_name="profile-1")

    monkeypatch.setattr(hermes_router, "HermesRunRepository", lambda _db: FakeRepository())
    monkeypatch.setattr(hermes_router, "_profile_for_request", fake_profile_for_request)
    monkeypatch.setattr(hermes_router, "runtime_client", lambda: FailingRuntimeClient())

    with pytest.raises(HTTPException) as error:
        await hermes_router.resolve_approval(
            "run-1",
            HermesApprovalDecision(request_id="request-1", choice="once"),
            db=FakeDb(),
            current_user=SimpleNamespace(id="user-1"),
            current_workspace=SimpleNamespace(id="workspace-1"),
        )

    assert error.value.status_code == 502
    assert commits == ["approved", "pending"]
    assert rollbacks == 1
    assert approval.choice is None
    assert approval.decided_by_user_id is None
    assert approval.decided_at is None


def test_stop_request_survives_remote_attachment_and_in_flight_events(
    monkeypatch,
) -> None:
    run = SimpleNamespace(
        id="run-1",
        status="stopping",
        hermes_run_id=None,
        execution_claim_token="claim-1",
        stage="run.stopping",
        current_activity="Stopping Hermes.",
        updated_at=None,
    )
    db = SimpleNamespace(add=lambda _row: None, flush=lambda: None)
    repository = HermesRunRepository(db)
    monkeypatch.setattr(repository, "get", lambda _run_id, **_kwargs: run)

    repository.attach_hermes_run(
        "run-1",
        claim_token="claim-1",
        hermes_run_id="hermes-run-1",
    )
    repository._apply_event(
        run,
        "message.delta",
        {"event": "message.delta", "delta": "late output"},
        sequence=3,
    )

    assert run.hermes_run_id == "hermes-run-1"
    assert run.status == "stopping"
    assert run.stage == "run.stopping"
    assert run.current_activity == "Stopping Hermes."


async def test_scheduled_jobs_use_a_separate_profile_without_any_mcp() -> None:
    binding = SimpleNamespace(profile_name="owh-owner-profile")
    removed: list[tuple[str, str]] = []
    servers = {"open-work-hub", "third-party"}

    class FakeManagementClient:
        async def list_profiles(self):
            return {"profiles": [{"name": "owh-owner-profile-jobs"}]}

        async def set_profile_model(self, profile_name, **_kwargs):
            assert profile_name == "owh-owner-profile-jobs"
            return {"ok": True}

        async def list_mcp_servers(self, profile_name):
            assert profile_name == "owh-owner-profile-jobs"
            return {"servers": [{"name": name} for name in sorted(servers)]}

        async def remove_mcp_server(self, profile_name, server_name):
            removed.append((profile_name, server_name))
            servers.discard(server_name)
            return {"ok": True}

    settings = SimpleNamespace(hermes_enabled=True)
    profile_name = await ensure_job_profile(
        binding,
        settings=settings,
        client=FakeManagementClient(),
    )

    assert profile_name == job_profile_name(binding)
    assert removed == [
        ("owh-owner-profile-jobs", "open-work-hub"),
        ("owh-owner-profile-jobs", "third-party"),
    ]


async def test_scheduled_job_profile_clones_the_interactive_profile() -> None:
    binding = SimpleNamespace(profile_name="owh-owner-profile-create")
    profiles: set[str] = {"owh-owner-profile-create"}
    create_calls: list[dict[str, Any]] = []

    class FakeManagementClient:
        async def list_profiles(self):
            return {"profiles": [{"name": name} for name in sorted(profiles)]}

        async def create_profile(self, **kwargs):
            create_calls.append(kwargs)
            profiles.add(kwargs["profile_name"])
            return {"ok": True}

        async def set_profile_model(self, _profile_name, **_kwargs):
            return {"ok": True}

        async def list_mcp_servers(self, _profile_name):
            return {"servers": []}

    settings = SimpleNamespace(hermes_enabled=True)
    await ensure_job_profile(
        binding,
        settings=settings,
        client=FakeManagementClient(),
    )

    assert create_calls == [
        {
            "profile_name": "owh-owner-profile-create-jobs",
            "clone_from": "owh-owner-profile-create",
            "description": "Open Work Hub isolated scheduled-agent profile",
            "mcp_servers": [],
        }
    ]


async def test_profile_reconciliation_replaces_stale_internal_mcp_url(
    monkeypatch,
) -> None:
    profile_name = "owh-33333333333333333333333333333333"
    internal_name = internal_mcp_server_name(profile_name)
    external_name = scoped_mcp_server_name(profile_name, "project-tracker")
    binding = SimpleNamespace(
        profile_name=profile_name,
        status="pending",
        last_error_code=None,
        last_reconciled_at=None,
        provisioned_at=None,
    )
    monkeypatch.setattr(
        hermes_service,
        "get_or_create_profile_binding",
        lambda _db, **_kwargs: binding,
    )
    servers = {
        internal_name: {
            "name": internal_name,
            "url": f"http://127.0.0.1:8001/api/v1/internal/hermes/mcp?profile={profile_name}",
            "auth": "header",
            "enabled": True,
            "tools": None,
        },
        external_name: {
            "name": external_name,
            "url": "https://mcp.example.test",
            "auth": "none",
            "enabled": True,
            "tools": None,
        },
    }
    removed: list[str] = []
    added: list[dict[str, Any]] = []

    class FakeManagementClient:
        async def list_profiles(self):
            return {"profiles": [{"name": profile_name}]}

        async def set_profile_model(self, resolved_profile_name, **_kwargs):
            assert resolved_profile_name == profile_name
            return {"ok": True}

        async def list_mcp_servers(self, resolved_profile_name):
            assert resolved_profile_name == profile_name
            return {"servers": list(servers.values())}

        async def remove_mcp_server(self, resolved_profile_name, server_name):
            assert resolved_profile_name == profile_name
            removed.append(server_name)
            servers.pop(server_name, None)
            return {"ok": True}

        async def add_mcp_server(self, resolved_profile_name, payload):
            assert resolved_profile_name == profile_name
            added.append(payload)
            servers[payload["name"]] = {
                **payload,
                "enabled": True,
                "tools": None,
            }
            return {"ok": True}

        async def set_profile_mcp_trust(self, resolved_profile_name, server_name):
            assert (resolved_profile_name, server_name) == (
                profile_name,
                internal_name,
            )
            return {"ok": True}

    class FakeDb:
        def add(self, _row):
            return None

        def commit(self):
            return None

        def refresh(self, _row):
            return None

    settings = SimpleNamespace(
        hermes_enabled=True,
        hermes_profile_clone_source="default",
        hermes_mcp_server_url=("http://127.0.0.1:8002/api/v1/internal/hermes/mcp"),
        hermes_mcp_shared_secret=SimpleNamespace(
            get_secret_value=lambda: "mcp-root-secret-00000000000000000001"
        ),
    )

    reconciled = await hermes_service.ensure_profile_binding(
        FakeDb(),
        workspace=SimpleNamespace(),
        user=SimpleNamespace(),
        settings=settings,
        client=FakeManagementClient(),
        research_sources=dict(DEFAULT_RESEARCH_SOURCE_POLICY),
        research_policy_revision=1,
    )

    assert reconciled is binding
    assert removed == [internal_name]
    assert len(added) == 1
    assert added[0]["name"] == internal_name
    assert added[0]["url"] == (
        f"http://127.0.0.1:8002/api/v1/internal/hermes/mcp?profile={profile_name}"
    )
    assert external_name in servers


def test_mcp_server_names_are_unique_to_the_hermes_profile() -> None:
    first_profile = "owh-11111111111111111111111111111111"
    second_profile = "owh-22222222222222222222222222222222"

    first_internal = internal_mcp_server_name(first_profile)
    second_internal = internal_mcp_server_name(second_profile)
    first_external = scoped_mcp_server_name(first_profile, "Project Tracker")

    assert first_internal != second_internal
    assert first_external == scoped_mcp_server_name(first_profile, "Project Tracker")
    assert first_external != scoped_mcp_server_name(second_profile, "Project Tracker")
    assert is_profile_scoped_mcp_server(first_profile, first_internal)
    assert is_profile_scoped_mcp_server(first_profile, first_external)
    assert not is_profile_scoped_mcp_server(second_profile, first_external)
    assert len(first_internal) <= 63
    assert len(first_external) <= 63


def test_mcp_profile_secret_is_scoped_and_event_payloads_are_redacted() -> None:
    settings = SimpleNamespace(
        hermes_mcp_shared_secret=SimpleNamespace(
            get_secret_value=lambda: "mcp-root-secret-00000000000000000001"
        )
    )
    first = mcp_profile_bearer_secret(settings, "profile-a")
    second = mcp_profile_bearer_secret(settings, "profile-b")

    assert len(first) == 64
    assert first != second
    assert first == mcp_profile_bearer_secret(settings, "profile-a")
    assert sanitize_event_payload(
        {
            "event": "tool.result",
            "Authorization": "Bearer secret",
            "nested": {"api-key": "secret", "safe": "visible"},
        }
    ) == {
        "event": "tool.result",
        "Authorization": "[REDACTED]",
        "nested": {"api-key": "[REDACTED]", "safe": "visible"},
    }
