from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.hermes import files
from open_work_hub_api.domains.hermes.file_router import download_file
from open_work_hub_api.domains.hermes.model_policy import (
    HermesModelPolicy,
    synchronize_model_policy,
)
from open_work_hub_api.domains.hermes.models import (
    HermesFileObject,
    HermesProfileBinding,
    HermesRunProjection,
    HermesSessionBinding,
)
from open_work_hub_api.domains.hermes.repository import HermesRunRepository, utcnow_naive
from open_work_hub_api.domains.hermes.workloads import _messages
from open_work_hub_api.core.llm_errors import LlmProviderError


def seed(db):
    user_id = str(uuid4())
    user = User(
        id=user_id,
        login_id=f"test-{user_id[:12]}",
        email=f"{user_id}@example.test",
        full_name="Runtime test",
        password_hash="not-used",
    )
    db.add(user)
    db.flush()
    binding = HermesProfileBinding(
        id=str(uuid4()),
        user_id=user_id,
        profile_name=f"owh-{uuid4().hex}",
        status="active",
        provider="openai",
        model="test",
    )
    db.add(binding)
    db.flush()
    return user, binding


def session_for(db, binding):
    row = HermesSessionBinding(
        id=str(uuid4()),
        user_id=binding.user_id,
        profile_binding_id=binding.id,
        hermes_session_id=f"session-{uuid4().hex}",
    )
    db.add(row)
    db.flush()
    return row


def stage(db, binding, session, **kwargs):
    return HermesRunRepository(db).stage(
        binding=binding,
        session=session,
        input_text="test",
        instructions=None,
        conversation_history=[],
        **kwargs,
    )


def test_database_capacity_is_atomic_across_independent_connections(application_postgres_dsn):
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            ids = [stage(db, binding, session_for(db, binding)).id for _ in range(4)]
            db.commit()
        barrier = Barrier(4)

        def claim(run_id):
            with Session(engine) as db:
                barrier.wait(timeout=5)
                result = HermesRunRepository(db).claim_execution(
                    run_id, claim_token=uuid4().hex, lease_seconds=60, max_concurrent_runs=2
                )
                db.commit()
                return result

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(claim, ids))
        assert sum(result.acquired for result in results) == 2
        assert sum(result.reason == "capacity" for result in results) == 2
    finally:
        engine.dispose()


def test_same_conversation_orders_runs_but_another_session_can_start(application_postgres_dsn):
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            session = session_for(db, binding)
            first = stage(db, binding, session)
            second = stage(db, binding, session)
            other = stage(db, binding, session_for(db, binding))
            repo = HermesRunRepository(db)
            assert (
                repo.claim_execution(second.id, claim_token="second", lease_seconds=60).reason
                == "session_busy"
            )
            assert repo.claim_execution(first.id, claim_token="first", lease_seconds=60).acquired
            assert repo.claim_execution(other.id, claim_token="other", lease_seconds=60).acquired
            db.rollback()
    finally:
        engine.dispose()


def test_completion_reloads_structured_submission_from_another_transaction(
    application_postgres_dsn,
):
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine, expire_on_commit=False) as dispatcher:
            _, binding = seed(dispatcher)
            run = stage(dispatcher, binding, None, output_schema={"type": "object"})
            dispatcher.commit()
            assert run.output_payload is None
            with Session(engine) as transport:
                remote = transport.get(HermesRunProjection, run.id)
                remote.output_payload = {"answer": 42}
                transport.commit()
            HermesRunRepository(dispatcher).append_event(
                run.id, {"event": "run.completed", "output": "done"}
            )
            assert run.status == "completed"
            assert run.output_payload == {"answer": 42}
            missing = stage(dispatcher, binding, None, output_schema={"type": "object"})
            HermesRunRepository(dispatcher).append_event(
                missing.id, {"event": "run.completed", "output": "{}"}
            )
            assert missing.status == "invalid_output"
            dispatcher.rollback()
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("temperature", [None, 0, 0.7])
async def test_model_snapshot_has_no_secret_and_auxiliary_follows_main(temperature):
    from dataclasses import replace

    policy = HermesModelPolicy(
        "local",
        "openai",
        "local-test",
        "http://model:8000/v1",
        "",
        8192,
        temperature=temperature,
    )
    configs = []

    class Client:
        async def update_profile_config(self, profile, config):
            configs.append(config)

        async def update_profile_env(self, profile, key, value):
            pass

    await synchronize_model_policy(Client(), profile_name="owh-test-local", policy=policy)
    config = configs[0]
    assert config["fallback_providers"] == []
    assert all(
        task["provider"] == "main" and task["fallback_chain"] == []
        for task in config["auxiliary"].values()
    )
    assert config["providers"][policy.key]["max_output_tokens"] == 8192
    provider = config["providers"][policy.key]
    if temperature is None:
        assert "extra_body" not in provider
        assert "temperature" not in policy.run_options()["owh_policy"]
    else:
        assert provider["extra_body"] == {"temperature": temperature}
        assert policy.run_options()["owh_policy"]["temperature"] == temperature
        assert policy.key != replace(policy, temperature=None).key
        assert policy.key != replace(policy, temperature=temperature + 0.1).key
    assert config["delegation"]["provider"] == "auto"
    assert "session_search" not in config["platform_toolsets"]["api_server"]
    assert policy.run_options()["provider"] == f"custom:{policy.key}"
    assert "api_key" not in policy.run_options()
    rotated = HermesModelPolicy(
        "local", "openai", "local-test", "http://model:8000/v1", "rotated-test-key", 8192
    )
    assert rotated.key != policy.key
    assert "rotated-test-key" not in repr(rotated)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../secret",
        "/etc/passwd",
        "nested/../../secret",
        "nested//file",
        ".owh-runtime/file",
        "nul\x00name",
    ],
)
def test_workspace_paths_reject_escape_and_control_characters(path):
    with pytest.raises(ValueError):
        files.normalize_path(path)


@pytest.mark.anyio
@pytest.mark.parametrize("temperature", [0, 0.7])
async def test_anthropic_temperature_fails_before_provisioning(monkeypatch, temperature):
    from open_work_hub_api.core.llm import (
        LlmPoolConfig,
        LlmTaskContext,
        PolicyDecision,
        ResolvedLlmExecution,
    )
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.hermes import workloads

    config = LlmPoolConfig(
        "external",
        "anthropic",
        "https://api.anthropic.com",
        "synthetic",
        "test-model",
        "test-model",
        1,
        30,
    )
    monkeypatch.setattr(
        workloads,
        "get_settings",
        lambda: get_settings().model_copy(update={"hermes_enabled": True}),
    )
    monkeypatch.setattr(
        workloads,
        "get_session_factory",
        lambda: pytest.fail(
            "Unsupported sampling must fail before staging or profile provisioning"
        ),
    )
    with pytest.raises(LlmProviderError, match="explicit temperature") as error:
        await workloads.run_workload(
            LlmTaskContext(
                source="test",
                task_kind="chatbot",
                app_id="chatbot",
                workload_id="chatbot",
                actor_user_id="synthetic-owner",
            ),
            ResolvedLlmExecution(
                "external",
                PolicyDecision("external_allowed", "external"),
                config,
                "test-model",
                4096,
                "none",
            ),
            {"messages": [{"role": "user", "content": "test"}], "temperature": temperature},
            timeout_seconds=10,
        )
    assert error.value.pool == "external" and error.value.provider == "anthropic"
    default_policy = HermesModelPolicy.from_pool(config, model="test-model", max_tokens=4096)
    assert default_policy.api_mode == "anthropic_messages"
    assert "temperature" not in default_policy.run_options()["owh_policy"]


@pytest.mark.anyio
@pytest.mark.parametrize("remote_accepted", [False, True])
@pytest.mark.parametrize("termination", ["cancel", "timeout"])
async def test_cancel_during_admission_recovers_without_starting_another_run(
    application_postgres_dsn, monkeypatch, remote_accepted, termination
):
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.core.llm import (
        LlmPoolConfig,
        LlmTaskContext,
        PolicyDecision,
        ResolvedLlmExecution,
    )
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.hermes import execution, workloads
    from open_work_hub_api.domains.hermes.client import HermesClientError
    from open_work_hub_api.domains.hermes.models import HermesDispatchOutbox, HermesRunInput
    from open_work_hub_api.domains.hermes.repository import HermesDispatchRepository

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(workloads, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        workloads,
        "get_settings",
        lambda: get_settings().model_copy(update={"hermes_enabled": True}),
    )
    entered = asyncio.Event()
    admissions, stops = [], []
    control_available = False

    class Runtime:
        def __init__(self, **kwargs):
            pass

        async def create_run(self, profile, **kwargs):
            admissions.append(kwargs)
            if kwargs.get("cancel_admission"):
                if not control_available:
                    raise HermesClientError(
                        operation="cancel_run_admission",
                        status_code=503,
                        code="synthetic.unavailable",
                        message="Synthetic control outage",
                    )
                return {
                    "run_id": "run_accepted" if remote_accepted else "run_cancelled_reservation",
                    "status": "running" if remote_accepted else "cancelled",
                }
            assert len(admissions) == 1, "Recovery must never invoke native creation again"
            entered.set()
            await asyncio.Event().wait()  # Acceptance response never reaches the caller.

        async def stop_run(self, profile, native_id):
            stops.append(native_id)
            return {"status": "cancelled"}

    monkeypatch.setattr(execution, "HermesRuntimeClient", Runtime)
    monkeypatch.setattr(workloads, "runtime_client", Runtime)
    try:
        with factory() as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            owner_id, binding_id = user.id, binding.id
            db.commit()

        async def ensure(db, **kwargs):
            return db.get(HermesProfileBinding, binding_id)

        monkeypatch.setattr(workloads, "ensure_profile_binding", ensure)
        config = LlmPoolConfig(
            "local",
            "openai",
            "http://model.test/v1",
            "",
            "test-model",
            "test-model",
            1,
            30,
            requires_credentials=False,
        )
        task = asyncio.create_task(
            workloads.run_workload(
                LlmTaskContext(
                    source="test",
                    task_kind="chatbot",
                    app_id="chatbot",
                    workload_id="chatbot",
                    actor_user_id=owner_id,
                ),
                ResolvedLlmExecution(
                    "local",
                    PolicyDecision("local_only", "local"),
                    config,
                    "test-model",
                    4096,
                    "none",
                ),
                {"messages": [{"role": "user", "content": "test"}]},
                timeout_seconds=0.2 if termination == "timeout" else 30,
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        if termination == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if termination == "cancel" else LlmProviderError):
            await asyncio.wait_for(task, 5)
        assert stops == []
        run_id = admissions[0]["idempotency_key"]
        with factory() as db:
            run = db.get(HermesRunProjection, run_id)
            assert run.status == "stopping" and run.hermes_run_id is None
            assert run.execution_claim_token is None
            assert db.get(HermesRunInput, run_id) is not None
            other = stage(db, db.get(HermesProfileBinding, binding_id), None)
            other_id = other.id
            assert (
                HermesRunRepository(db)
                .claim_execution(
                    other_id, claim_token="other", lease_seconds=60, max_concurrent_runs=1
                )
                .reason
                == "capacity"
            )
            db.commit()
            # Retry exhaustion cannot turn an unconfirmed stop into success/failure.
            execution.mark_hermes_run_terminal_failure(
                db, run_id=run_id, error_code="synthetic.exhausted", error_message="test"
            )
            outbox = db.scalar(
                select(HermesDispatchOutbox).where(HermesDispatchOutbox.run_id == run_id)
            )
            outbox.attempts, outbox.claim_token, outbox.status = 20, "publish", "claimed"
            db.flush()
            HermesDispatchRepository(db).mark_retry(
                outbox.id,
                claim_token="publish",
                error_code="synthetic.exhausted",
                retry_at=utcnow_naive(),
            )
            db.commit()
            assert outbox.status == "pending" and run.status == "stopping"
            # Cleanup remains possible after the execution profile is disabled.
            db.get(HermesProfileBinding, binding_id).status = "disabled"
            db.commit()

        async def recover():
            with factory() as db:
                return await execution.execute_hermes_run(
                    db,
                    run_id=run_id,
                    runtime_base_url="http://hermes.test",
                    api_key="synthetic",
                    request_timeout_seconds=1,
                    lease_seconds=60,
                    max_concurrent_runs=1,
                )

        with pytest.raises(HermesClientError):
            await recover()
        with factory() as db:
            run = db.get(HermesRunProjection, run_id)
            assert run.status == "stopping" and run.execution_claim_token is None
            assert db.get(HermesRunInput, run_id) is not None
        control_available = True
        assert await recover() == "cancelled"
        assert stops == (["run_accepted"] if remote_accepted else [])
        assert len(admissions) == 3
        assert all(
            {k: v for k, v in attempt.items() if k != "cancel_admission"} == admissions[0]
            for attempt in admissions[1:]
        )
        with factory() as db:
            assert db.get(HermesRunProjection, run_id).status == "cancelled"
            assert db.get(HermesRunInput, run_id) is None
            assert (
                HermesRunRepository(db)
                .claim_execution(
                    other_id, claim_token="other", lease_seconds=60, max_concurrent_runs=1
                )
                .acquired
            )
            db.rollback()
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("claimed", [False, True])
async def test_public_stop_keeps_a_lost_acceptance_recoverable(application_postgres_dsn, claimed):
    from open_work_hub_api.domains.hermes.router import stop_run

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            run = stage(db, binding, session_for(db, binding))
            repository = HermesRunRepository(db)
            if claimed:
                assert repository.claim_execution(
                    run.id, claim_token="lost-response", lease_seconds=60
                ).acquired
                repository.release_execution_claim(run.id, claim_token="lost-response")
            db.commit()
            response = await stop_run(run.id, db=db, current_user=user)
            assert response.status == ("stopping" if claimed else "cancelled")
            recovery = repository.claim_execution(run.id, claim_token="recover", lease_seconds=60)
            assert recovery.acquired is claimed
            db.rollback()
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("temperature", [None, 0, 0.7])
@pytest.mark.parametrize("mode", ["sync", "stream"])
@pytest.mark.parametrize(
    "contract",
    [
        "structured",
        "tool_request",
        "tool_result",
        "forced_final",
        "provision_failure",
        "execution_failure",
    ],
)
async def test_workload_uses_durable_dispatch_and_validated_native_submission(
    application_postgres_dsn, monkeypatch, temperature, mode, contract
):
    import asyncio
    import json
    from pydantic import SecretStr
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from starlette.requests import Request
    from open_work_hub_api.core.llm import (
        LlmPoolConfig,
        LlmTaskContext,
        PolicyDecision,
        ResolvedLlmExecution,
    )
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
    from open_work_hub_api.domains.hermes import workloads, execution, mcp_router
    from open_work_hub_api.domains.hermes.service import mcp_profile_bearer_secret
    from open_work_hub_api.domains.hermes.client import HermesClientError

    def unavailable():
        raise HermesClientError(
            operation="fixture",
            status_code=503,
            code="fixture.unavailable",
            message="Synthetic control API outage",
        )

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = get_settings().model_copy(
        update={
            "hermes_enabled": True,
            "hermes_mcp_shared_secret": SecretStr("synthetic-workload-mcp-secret"),
        }
    )
    monkeypatch.setattr(workloads, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    monkeypatch.setattr(workloads, "get_session_factory", lambda: factory)
    expected_result = (
        {"value": 42}
        if contract == "structured"
        else {"content": "Application result received"}
        if contract in {"tool_result", "forced_final"}
        else {"tool_calls": [{"name": "fixture.lookup", "arguments": {"value": 42}}]}
    )
    try:
        with factory() as db:
            user, binding = seed(db)
            owner_id, binding_id, profile_name = user.id, binding.id, binding.profile_name
            db.merge(CompanyAppControl(app_id="chatbot", enabled=True))
            db.flush()
            db.merge(AppAccessPolicy(app_id="chatbot", audience="all"))
            db.commit()

        async def ensure(db, **kwargs):
            if contract == "provision_failure":
                unavailable()
            assert kwargs["user"].id == owner_id
            assert kwargs["model_policy"].route == "local"
            assert kwargs["model_policy"].temperature == temperature
            return db.get(HermesProfileBinding, binding_id)

        monkeypatch.setattr(workloads, "ensure_profile_binding", ensure)
        attempts = []
        submissions = []

        class NativeRuntime:
            def __init__(self, **kwargs):
                pass

            async def create_run(self, profile, **kwargs):
                assert profile == profile_name
                assert kwargs["runtime_options"]["owh_policy"]["model"] == "test-model"
                assert kwargs["runtime_options"]["owh_policy"].get("temperature") == temperature
                assert "owh_submit_result" in kwargs["instructions"]
                if contract in {"tool_result", "forced_final"}:
                    assert '"role": "tool"' in kwargs["input_text"]
                    assert "Application evidence" in kwargs["input_text"]
                attempts.append(kwargs["idempotency_key"])
                if contract == "execution_failure":
                    unavailable()
                return {"run_id": "run_native_fixture", "status": "running"}

            async def iter_run_events(self, profile, run_id):
                for result in ({"value": "wrong type"}, expected_result):
                    body = json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "owh/submit",
                            "params": {"result": result},
                        }
                    ).encode()

                    async def receive():
                        return {"type": "http.request", "body": body, "more_body": False}

                    request = Request(
                        {"type": "http", "method": "POST", "path": "/", "headers": []}, receive
                    )
                    with factory() as db:
                        response = await mcp_router.handle_mcp_request(
                            request,
                            profile=profile,
                            authorization=f"Bearer {mcp_profile_bearer_secret(settings, profile)}",
                            mcp_session_id=None,
                            hermes_run_id=run_id,
                            db=db,
                        )
                        submissions.append(json.loads(response.body)["result"])
                yield {
                    "event": "run.completed",
                    "output": "done",
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                }

        monkeypatch.setattr(execution, "HermesRuntimeClient", NativeRuntime)
        config = LlmPoolConfig(
            "local",
            "openai",
            "http://model.test/v1",
            "",
            "test-model",
            "test-model",
            1,
            30,
            requires_credentials=False,
        )
        context = LlmTaskContext(
            source="test",
            task_kind="chatbot",
            app_id="chatbot",
            workload_id="chatbot",
            actor_user_id=None,
            execution_user_id=owner_id,
            principal_kind="system",
        )
        resolved = ResolvedLlmExecution(
            "local", PolicyDecision("local_only", "local"), config, "test-model", 4096, "none"
        )
        payload = {"messages": [{"role": "user", "content": "Return a validated value"}]}
        if temperature is not None:
            payload["temperature"] = temperature
        options = dict(
            timeout_seconds=10,
            output_schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        if contract != "structured":
            options.pop("output_schema")
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "fixture.lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                    },
                }
            ]
            if contract in {"tool_result", "forced_final"}:
                payload["messages"].extend(
                    [
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "prior-call",
                                    "type": "function",
                                    "function": {
                                        "name": "fixture.lookup",
                                        "arguments": '{"value":42}',
                                    },
                                }
                            ],
                        },
                        {
                            "role": "tool",
                            "tool_call_id": "prior-call",
                            "content": "Application evidence",
                        },
                    ]
                )
            if contract == "forced_final":
                payload.pop("tools")
        if contract.endswith("_failure"):
            with pytest.raises(LlmProviderError) as error:
                if mode == "sync":
                    await asyncio.to_thread(
                        workloads.complete_workload, context, resolved, payload, **options
                    )
                else:
                    async for _ in workloads.stream_workload(context, resolved, payload, **options):
                        pytest.fail("An unavailable provider cannot return successful output")
            assert isinstance(error.value.__cause__, HermesClientError)
            assert error.value.pool == "local" and error.value.provider == "openai"
            assert "Synthetic" not in str(error.value)
            with factory() as db:
                runs = list(
                    db.scalars(
                        select(HermesRunProjection).where(HermesRunProjection.user_id == owner_id)
                    )
                )
                assert len(runs) == (1 if contract == "execution_failure" else 0)
                assert all(run.execution_claim_token is None for run in runs)
            return
        if mode == "sync":
            result = await asyncio.to_thread(
                workloads.complete_workload, context, resolved, payload, **options
            )
        else:
            chunks = [
                chunk
                async for chunk in workloads.stream_workload(context, resolved, payload, **options)
            ]
            result = {"structured_output": chunks[-1].structured_output, "usage": chunks[-2].usage}
            if contract == "tool_request":
                assert chunks[0].kind == "tool_call_start"
                assert chunks[0].tool_name == "fixture.lookup"
                assert chunks[1].tool_call_id == chunks[0].tool_call_id
                assert json.loads(chunks[1].args_delta) == {"value": 42}
                assert chunks[-1].finish_reason == "tool_calls"
            elif contract in {"tool_result", "forced_final"}:
                assert chunks[0].text == "Application result received"
                assert chunks[-1].finish_reason == "stop"
        if mode == "sync" and contract == "tool_request":
            assert result["choices"][0]["finish_reason"] == "tool_calls"
            assert (
                result["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
                == "fixture.lookup"
            )
        assert result["structured_output"] == expected_result
        assert result["usage"]["total_tokens"] == 10
        assert len(attempts) == 1
        assert [item["accepted"] for item in submissions] == [False, True]
        assert context.actor_user_id is None
        with factory() as db:
            run = db.scalar(
                select(HermesRunProjection).where(HermesRunProjection.id == attempts[0])
            )
            assert run.user_id == owner_id and run.owner_app_id == "chatbot"
            assert run.status == "completed" and run.allowed_app_ids == []
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("capacity, occupied", [(1, 1), (3, 3), (3, 2)])
@pytest.mark.parametrize("mode", ["sync", "stream"])
async def test_nested_generation_respects_capacity_without_waiting_for_its_parent(
    application_postgres_dsn, monkeypatch, capacity, occupied, mode
):
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.core.llm import (
        LlmPoolConfig,
        LlmTaskContext,
        PolicyDecision,
        ResolvedLlmExecution,
    )
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.ai.tool_context import (
        ToolExecutionContext,
        bind_tool_execution_context,
    )
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
    from open_work_hub_api.domains.hermes import workloads, execution

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = get_settings().model_copy(
        update={
            "hermes_enabled": True,
            "hermes_max_concurrent_runs": capacity,
        }
    )
    monkeypatch.setattr(workloads, "get_settings", lambda: settings)
    monkeypatch.setattr(workloads, "get_session_factory", lambda: factory)
    attempts = []
    try:
        with factory() as db:
            user, binding = seed(db)
            owner_id, binding_id = user.id, binding.id
            db.merge(CompanyAppControl(app_id="chatbot", enabled=True))
            db.flush()
            db.merge(AppAccessPolicy(app_id="chatbot", audience="all"))
            parents = [stage(db, binding, session_for(db, binding)) for _ in range(occupied)]
            for parent in parents:
                assert (
                    HermesRunRepository(db)
                    .claim_execution(
                        parent.id,
                        claim_token=parent.id,
                        lease_seconds=60,
                        max_concurrent_runs=capacity,
                    )
                    .acquired
                )
            parent_ids = [parent.id for parent in parents]
            db.commit()

        async def ensure(db, **kwargs):
            return db.get(HermesProfileBinding, binding_id)

        class NativeRuntime:
            def __init__(self, **kwargs):
                pass

            async def create_run(self, profile, **kwargs):
                attempts.append(kwargs["idempotency_key"])
                return {"run_id": "native_nested", "status": "running"}

            async def iter_run_events(self, profile, run_id):
                yield {"event": "run.completed", "output": "nested result"}

        monkeypatch.setattr(workloads, "ensure_profile_binding", ensure)
        monkeypatch.setattr(execution, "HermesRuntimeClient", NativeRuntime)
        context = LlmTaskContext(
            source="test",
            task_kind="chatbot",
            app_id="chatbot",
            workload_id="chatbot",
            actor_user_id=owner_id,
        )
        config = LlmPoolConfig(
            "local",
            "openai",
            "http://model.test/v1",
            "",
            "test-model",
            "test-model",
            1,
            30,
            requires_credentials=False,
        )
        resolved = ResolvedLlmExecution(
            "local",
            PolicyDecision("local_only", "local"),
            config,
            "test-model",
            4096,
            "none",
        )

        async def invoke():
            payload = {"messages": [{"role": "user", "content": "Nested generation"}]}
            if mode == "sync":
                return await asyncio.to_thread(
                    workloads.complete_workload,
                    context,
                    resolved,
                    payload,
                    timeout_seconds=10,
                )
            return [
                chunk
                async for chunk in workloads.stream_workload(
                    context,
                    resolved,
                    payload,
                    timeout_seconds=10,
                )
            ]

        with bind_tool_execution_context(
            ToolExecutionContext(
                source="hermes-mcp",
                tool_name="meeting.extract_actions",
                agent_run_id=parent_ids[0],
            )
        ):
            if occupied == capacity:
                with pytest.raises(LlmProviderError, match="ended with failed"):
                    await asyncio.wait_for(invoke(), timeout=3)
            else:
                await asyncio.wait_for(invoke(), timeout=3)
        with factory() as db:
            child = db.scalar(
                select(HermesRunProjection).where(
                    HermesRunProjection.user_id == owner_id,
                    HermesRunProjection.kind == "workload",
                )
            )
            assert child.runtime_options["parent_run_id"] == parent_ids[0]
            assert child.execution_claim_token is None
            if occupied == capacity:
                assert child.status == "failed" and child.error_code == "hermes.nested_capacity"
                assert attempts == []
                for parent_id in parent_ids:
                    parent = db.get(HermesRunProjection, parent_id)
                    assert (
                        parent.status == "dispatching" and parent.execution_claim_token == parent_id
                    )
                    HermesRunRepository(db).append_event(parent_id, {"event": "run.completed"})
                db.commit()
                claim = HermesRunRepository(db).claim_execution(
                    child.id,
                    claim_token="late-outbox",
                    lease_seconds=60,
                    max_concurrent_runs=capacity,
                )
                assert not claim.acquired and claim.reason == "terminal"
            else:
                assert child.status == "completed" and len(attempts) == 1
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("stop_unavailable", [False, True])
async def test_cancelled_workload_returns_lease_and_recovers_durable_stop(
    application_postgres_dsn, monkeypatch, stop_unavailable
):
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.core.llm import (
        LlmPoolConfig,
        LlmTaskContext,
        PolicyDecision,
        ResolvedLlmExecution,
    )
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
    from open_work_hub_api.domains.hermes import execution, workloads
    from open_work_hub_api.domains.hermes.client import HermesClientError

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = get_settings().model_copy(update={"hermes_enabled": True})
    monkeypatch.setattr(workloads, "get_settings", lambda: settings)
    monkeypatch.setattr(workloads, "get_session_factory", lambda: factory)
    started = asyncio.Event()
    stopped = []
    try:
        with factory() as db:
            user, binding = seed(db)
            owner_id, binding_id = user.id, binding.id
            db.merge(CompanyAppControl(app_id="chatbot", enabled=True))
            db.flush()
            db.merge(AppAccessPolicy(app_id="chatbot", audience="all"))
            db.commit()

        async def ensure(db, **kwargs):
            return db.get(HermesProfileBinding, binding_id)

        class Runtime:
            def __init__(self, **kwargs):
                pass

            async def create_run(self, profile, **kwargs):
                return {"run_id": "cancel-native", "status": "running"}

            async def iter_run_events(self, *args):
                started.set()
                await asyncio.Event().wait()
                yield {}

            async def stop_run(self, profile, native_id):
                stopped.append(native_id)
                if stop_unavailable:
                    raise HermesClientError(
                        operation="stop_run",
                        status_code=503,
                        code="test.unavailable",
                        message="Synthetic outage",
                    )
                return {"status": "cancelled"}

        monkeypatch.setattr(workloads, "ensure_profile_binding", ensure)
        monkeypatch.setattr(workloads, "runtime_client", Runtime)
        monkeypatch.setattr(execution, "HermesRuntimeClient", Runtime)
        config = LlmPoolConfig(
            "local",
            "openai",
            "http://model.test/v1",
            "",
            "test-model",
            "test-model",
            1,
            30,
            requires_credentials=False,
        )
        context = LlmTaskContext(
            source="test",
            task_kind="chatbot",
            app_id="chatbot",
            workload_id="chatbot",
            actor_user_id=owner_id,
        )
        resolved = ResolvedLlmExecution(
            "local", PolicyDecision("local_only", "local"), config, "test-model", 4096, "none"
        )
        task = asyncio.create_task(
            workloads.run_workload(
                context,
                resolved,
                {"messages": [{"role": "user", "content": "Wait"}]},
                timeout_seconds=30,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=10)
        assert stopped == ["cancel-native"]
        with factory() as db:
            run = db.scalar(
                select(HermesRunProjection).where(HermesRunProjection.user_id == owner_id)
            )
            assert run.execution_claim_token is None and run.execution_claim_expires_at is None
            repo = HermesRunRepository(db)
            if stop_unavailable:
                assert run.status == "stopping"
                # Recovery may reclaim immediately, without waiting 3,900s.
                assert repo.claim_execution(
                    run.id, claim_token="recover", lease_seconds=60, max_concurrent_runs=1
                ).acquired
                repo.append_event(run.id, {"event": "run.cancelled"}, claim_token="recover")
            else:
                assert run.status == "cancelled"
            next_run = stage(db, db.get(HermesProfileBinding, binding_id), None)
            assert repo.claim_execution(
                next_run.id, claim_token="next", lease_seconds=60, max_concurrent_runs=1
            ).acquired
            db.rollback()
    finally:
        engine.dispose()


def test_files_preserve_cleanup_intent_and_owner_acl(application_postgres_dsn, monkeypatch):
    objects = {}

    class Body(BytesIO):
        def release_conn(self):
            pass

    class Storage:
        fail_delete = False

        def put_object(self, bucket, key, stream, size, **kwargs):
            objects[key] = stream.read()

        def get_object(self, bucket, key):
            return Body(objects[key])

        def remove_object(self, bucket, key):
            if self.fail_delete:
                raise OSError("test storage outage")
            objects.pop(key, None)

    storage = Storage()
    monkeypatch.setattr(files, "get_minio_client", lambda: storage)
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            session = session_for(db, binding)
            original = files.save_file(db, session=session, path="report.txt", data=b"first")
            old_key = original.object_key
            current = files.save_file(db, session=session, path="report.txt", data=b"second")
            assert files.read_file(current) == b"second"
            assert db.get(HermesFileObject, old_key).expires_at <= utcnow_naive()
            with pytest.raises(HTTPException) as error:
                download_file(current.id, db=db, user=SimpleNamespace(id="another-user"))
            assert error.value.status_code == 404
            storage.fail_delete = True
            with pytest.raises(OSError):
                files.cleanup_files(db)
            db.rollback()
            assert db.get(HermesFileObject, old_key) is not None
            storage.fail_delete = False
            assert files.cleanup_files(db) == 1
            assert old_key not in objects
            reservation = db.get(HermesFileObject, current.object_key)
            reservation.expires_at = utcnow_naive() - timedelta(seconds=1)
            db.commit()
            assert files.cleanup_files(db) == 1
            assert not objects
    finally:
        engine.dispose()


@pytest.mark.parametrize("root", ["reports", "r_%"])
@pytest.mark.parametrize("reverse", [False, True])
def test_saved_file_paths_reject_prefix_conflicts_and_remain_restorable(
    application_postgres_dsn, monkeypatch, tmp_path, root, reverse
):
    objects = {}

    def put_object(bucket, key, stream, size, **kwargs):
        objects[key] = stream.read()

    monkeypatch.setattr(files, "get_minio_client", lambda: SimpleNamespace(put_object=put_object))
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            session = session_for(db, binding)
            paths = [root, root + "/nested/result.txt"]
            if reverse:
                paths.reverse()
            files.save_file(db, session=session, path=paths[0], data=b"retained")
            with pytest.raises(ValueError, match="path conflicts"):
                files.save_file(db, session=session, path=paths[1], data=b"conflicting")
            db.rollback()
            assert len(objects) == 1
            # Similar names, including SQL wildcard characters, are separate
            # paths; rejecting an ancestor must not reject these neighbours.
            files.save_file(db, session=session, path=root + "-other/result.txt", data=b"neighbour")
            files.save_file(db, session=session, path=paths[0], data=b"replacement")
            session_id = session.id
        # Reopen the catalog and restore every retained path to a fresh
        # filesystem, as a replacement sandbox does after restart.
        with Session(engine) as db:
            rows = files.list_files(db, session_id=session_id)
            assert {row.relative_path for row in rows} == {paths[0], root + "-other/result.txt"}
            for row in rows:
                target = tmp_path / row.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(objects[row.object_key])
            assert (tmp_path / paths[0]).read_bytes() == b"replacement"
    finally:
        engine.dispose()


@pytest.mark.parametrize("root", ["reports", "r_%"])
def test_concurrent_prefix_uploads_keep_a_restorable_catalog(
    application_postgres_dsn, monkeypatch, tmp_path, root
):
    objects = {}

    def put_object(bucket, key, stream, size, **kwargs):
        objects[key] = stream.read()

    monkeypatch.setattr(files, "get_minio_client", lambda: SimpleNamespace(put_object=put_object))
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            session_id = session_for(db, binding).id
            db.commit()
        barrier = Barrier(2)

        def upload(path):
            with Session(engine) as db:
                session = db.get(HermesSessionBinding, session_id)
                barrier.wait(timeout=5)
                try:
                    files.save_file(db, session=session, path=path, data=b"concurrent")
                except ValueError as error:
                    assert "path conflicts" in str(error)
                    db.rollback()
                    return False
                return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted = list(pool.map(upload, [root, root + "/result.txt"]))
        assert sum(accepted) == 1 and len(objects) == 1
        with Session(engine) as db:
            rows = files.list_files(db, session_id=session_id)
            assert len(rows) == 1
            target = tmp_path / rows[0].relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(objects[rows[0].object_key])
            assert target.read_bytes() == b"concurrent"
    finally:
        engine.dispose()


def test_workloads_preserve_messages_and_reject_application_tool_loops():
    assert _messages(
        {
            "messages": [
                {"role": "system", "content": "policy"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "next"},
            ]
        }
    ) == (
        "next",
        "policy",
        [{"role": "user", "content": "first"}, {"role": "assistant", "content": "reply"}],
    )
    with pytest.raises(LlmProviderError):
        _messages({"messages": [{"role": "tool", "content": "raw SDK tool result"}]})


def test_application_action_schema_enforces_tool_choice_arguments_and_parallel_limit():
    from jsonschema import Draft202012Validator, ValidationError
    from open_work_hub_api.domains.hermes.tool_decisions import (
        decision_message,
        prepare_tool_decision,
    )

    payload = {
        "messages": [{"role": "user", "content": "Choose an action"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "parameters": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                        "additionalProperties": False,
                    },
                },
            }
            for name in ("first", "second")
        ],
        "tool_choice": {"type": "function", "function": {"name": "second"}},
        "parallel_tool_calls": False,
    }
    _, schema = prepare_tool_decision(payload)
    call = {"name": "second", "arguments": {"id": 1}}
    Draft202012Validator(schema).validate({"tool_calls": [call]})
    for invalid in (
        None,
        {"content": "bypass required tool"},
        {"tool_calls": [{"name": "first", "arguments": {"id": 1}}]},
        {"tool_calls": [{"name": "second", "arguments": {"id": "wrong"}}]},
        {"tool_calls": [call, call]},
    ):
        with pytest.raises(ValidationError):
            decision_message(invalid, schema)
    payload["tool_choice"] = "none"
    _, schema = prepare_tool_decision(payload)
    assert decision_message({"content": "final"}, schema) == ({"content": "final"}, "stop")
    with pytest.raises(ValidationError):
        decision_message({"tool_calls": [call]}, schema)
    payload["tool_choice"] = "auto"
    payload["tools"][0]["function"]["parameters"] = {
        "$defs": {"arg": {"type": "integer"}},
        "type": "object",
        "properties": {"id": {"$ref": "#/$defs/arg"}},
        "required": ["id"],
    }
    _, schema = prepare_tool_decision(payload)
    message, finish = decision_message(
        {"tool_calls": [{"name": "first", "arguments": {"id": 1}}]}, schema
    )
    assert finish == "tool_calls" and message["tool_calls"][0]["function"]["name"] == "first"
    with pytest.raises(ValidationError):
        decision_message({"tool_calls": [{"name": "first", "arguments": {"id": "wrong"}}]}, schema)
    payload["tool_choice"] = {"type": "function", "function": {"name": "unavailable"}}
    with pytest.raises(LlmProviderError, match="unavailable"):
        prepare_tool_decision(payload)


@pytest.mark.anyio
async def test_session_activity_moves_across_pagination_without_read_or_replay_bumps(
    application_postgres_dsn, monkeypatch
):
    from open_work_hub_api.domains.hermes import router

    class Runtime:
        async def get_session(self, *args):
            return {}

    monkeypatch.setattr(router, "runtime_client", Runtime)
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            old = session_for(db, binding)
            old.updated_at = utcnow_naive() - timedelta(days=2)
            recent = session_for(db, binding)
            recent.updated_at = utcnow_naive() - timedelta(days=1)
            _, other_binding = seed(db)
            other = session_for(db, other_binding)
            db.commit()

            async def page(offset=0):
                return await router.list_sessions(
                    limit=1,
                    offset=offset,
                    scope_ref=None,
                    scope_resource_id=None,
                    db=db,
                    current_user=user,
                )

            assert (await page()).data[0].id == recent.id
            run = stage(db, binding, old, client_request_id="activity", request_sha256="same")
            db.commit()
            accepted_at = old.updated_at
            first = await page()
            assert first.data[0].id == old.id and first.has_more
            assert (await page(1)).data[0].id == recent.id
            assert all(row.id != other.id for row in first.data)
            replay = stage(db, binding, old, client_request_id="activity", request_sha256="same")
            assert replay.id == run.id
            db.commit()
            db.refresh(old)
            assert old.updated_at == accepted_at
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_sync_workload_cannot_block_the_callback_event_loop():
    from open_work_hub_api.domains.hermes.workloads import complete_workload

    with pytest.raises(LlmProviderError, match="worker thread"):
        complete_workload(None, None, {}, timeout_seconds=1)


def test_rag_tool_returns_evidence_without_starting_a_nested_generative_run(monkeypatch):
    from pydantic import ValidationError
    from open_work_hub_api.domains.rag.tools import RagQueryToolArgs, _query
    from open_work_hub_api.domains.rag.contracts import RagAnswerMode
    from open_work_hub_api.domains.retrieval import application

    request = RagQueryToolArgs(query="authorized evidence")
    assert request.answer_mode == RagAnswerMode.SEARCH_ONLY
    with pytest.raises(ValidationError):
        RagQueryToolArgs(query="evidence", answer_mode=RagAnswerMode.GROUNDED_ANSWER)

    def retrieve(db, **kwargs):
        assert kwargs["answer_mode"] == RagAnswerMode.SEARCH_ONLY
        return SimpleNamespace(model_dump=lambda **_: {"hits": [{"id": "authorized-hit"}]})

    monkeypatch.setattr(application, "query_rag_response", retrieve)
    result = _query(
        None, SimpleNamespace(kind="user", principal_id="user"), None, request.model_dump()
    )
    assert result == {"hits": [{"id": "authorized-hit"}]}


def test_completed_result_preserves_long_text_and_usage_without_secret_event_fields(
    application_postgres_dsn,
):
    from open_work_hub_api.domains.hermes.repository import MAX_RESULT_BYTES

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            _, binding = seed(db)
            run = stage(db, binding, None)
            result = "결과" * 20_000
            event = HermesRunRepository(db).append_event(
                run.id,
                {
                    "event": "run.completed",
                    "output": result,
                    "usage": {
                        "input_tokens": 123,
                        "output_tokens": 456,
                        "api_token": "fixture-secret",
                    },
                    "authorization": "fixture-secret",
                },
            )
            assert run.status == "completed" and run.output_text == result
            assert run.usage["input_tokens"] == 123 and run.usage["output_tokens"] == 456
            assert "fixture-secret" not in str(event.payload)
            assert event.payload["truncated"] is True and "output" not in event.payload
            too_large = stage(db, binding, None)
            HermesRunRepository(db).append_event(
                too_large.id, {"event": "run.completed", "output": "x" * (MAX_RESULT_BYTES + 1)}
            )
            assert too_large.status == "failed" and not too_large.output_text
            assert too_large.error_code == "hermes.output_too_large"
            db.rollback()
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_upload_bounds_stream_and_rejects_cross_owner_before_reading(
    application_postgres_dsn,
    monkeypatch,
):
    from starlette.requests import Request
    from open_work_hub_api.domains.hermes import file_router

    monkeypatch.setattr(file_router, "MAX_FILE_BYTES", 4)
    monkeypatch.setattr(
        file_router,
        "save_file",
        lambda *a, **kw: pytest.fail("Invalid input must not reach storage"),
    )
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            session = session_for(db, binding)
            reads = []

            def request(headers, chunks):
                iterator = iter(chunks)

                async def receive():
                    reads.append(True)
                    body, more = next(iterator)
                    return {"type": "http.request", "body": body, "more_body": more}

                return Request({"type": "http", "headers": headers}, receive)

            for headers, chunks in [
                ([(b"content-type", b"application/octet-stream"), (b"content-length", b"5")], []),
                (
                    [(b"content-type", b"application/octet-stream")],
                    [(b"123", True), (b"45", False)],
                ),
                ([(b"content-type", b"multipart/form-data")], []),
            ]:
                with pytest.raises(HTTPException) as error:
                    await file_router.upload_file(
                        session.id, request(headers, chunks), "test.txt", db, user
                    )
                assert error.value.status_code == 422
            before = len(reads)
            with pytest.raises(HTTPException) as error:
                await file_router.upload_file(
                    session.id, request([], []), "test.txt", db, SimpleNamespace(id="another-user")
                )
            assert error.value.status_code == 404 and len(reads) == before
            stage(db, binding, session)
            with pytest.raises(HTTPException) as error:
                await file_router.upload_file(
                    session.id,
                    request([(b"content-type", b"application/octet-stream")], [(b"123", False)]),
                    "test.txt",
                    db,
                    user,
                )
            assert error.value.status_code == 409
            db.rollback()
    finally:
        engine.dispose()


def test_native_tool_budget_is_durable_and_atomic_per_run(application_postgres_dsn, monkeypatch):
    import asyncio
    import json
    from starlette.requests import Request
    from open_work_hub_api.domains.hermes import mcp_router

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            owner_id, binding_id = user.id, binding.id
            run = stage(
                db,
                binding,
                None,
                kind="workload",
                workload_id="web_search.answer",
                runtime_options={
                    "native_tools": ["web_search", "terminal"],
                    "native_tool_limit": 1,
                },
            )
            run.status = "running"
            run_id = run.id
            db.commit()

        def identity(db, **kwargs):
            return db.get(HermesProfileBinding, binding_id), db.get(User, owner_id)

        def available(db, **kwargs):
            return None, [], db.get(HermesRunProjection, run_id)

        monkeypatch.setattr(mcp_router, "_resolve_mcp_identity", identity)
        monkeypatch.setattr(mcp_router, "_available_tools", available)
        barrier = Barrier(2)

        def admit(tool, concurrent=False):
            async def call():
                body = json.dumps(
                    {"id": 1, "method": "owh/native_admit", "params": {"tool": tool}}
                ).encode()

                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                with Session(engine) as db:
                    if concurrent:
                        barrier.wait(timeout=5)
                    response = await mcp_router.handle_mcp_request(
                        Request({"type": "http", "headers": []}, receive), profile="fixture", db=db
                    )
                    return json.loads(response.body)

            return asyncio.run(call())

        # Even a persisted tool name cannot grant a tool absent from the registry.
        assert "error" in admit("terminal")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: admit("web_search", True), range(2)))
        assert sorted(r["result"]["accepted"] for r in results) == [False, True]
        assert admit("web_search")["result"]["accepted"] is False
    finally:
        engine.dispose()


def admit_runtime_apps(db, user_id):
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
    from open_work_hub_api.domains.auth.models import CompanyAppControl

    for app_id in ("chatbot", "mail"):
        db.merge(CompanyAppControl(app_id=app_id, enabled=True))
        db.flush()
        db.merge(AppAccessPolicy(app_id=app_id, audience="selected"))
        db.flush()
        db.merge(AppUserGrant(app_id=app_id, user_id=user_id))
    db.flush()


@pytest.mark.anyio
@pytest.mark.parametrize("revocation", ["grant", "company", "user"])
async def test_run_reads_and_controls_recheck_current_owner_app_admission(
    application_postgres_dsn, revocation, monkeypatch
):
    from open_work_hub_api.domains.auth.app_access_models import AppUserGrant
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.hermes import router
    from open_work_hub_api.domains.hermes.schemas import HermesApprovalDecision, HermesSteerRequest

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            chat = stage(db, binding, session_for(db, binding))
            mail = stage(db, binding, None, kind="workload", owner_app_id="mail")
            mail.output_payload = {"private_mail_result": "synthetic"}
            mail.hermes_run_id = "native-mail-run"
            db.commit()
            assert (
                router.get_run(mail.id, db=db, current_user=user).output_payload
                == mail.output_payload
            )
            stream = router.stream_run_events(mail.id, last_event_id=None, db=db, current_user=user)
            await stream.body_iterator.aclose()
            before = router.list_runs(None, None, 100, 0, db, user)
            assert before.total == 2
            assert {row.id for row in before.data} == {chat.id, mail.id}
            if revocation == "grant":
                db.delete(db.get(AppUserGrant, ("mail", user.id)))
            elif revocation == "company":
                db.get(CompanyAppControl, "mail").enabled = False
            else:
                user.login_blocked = True
            db.commit()
            page = router.list_runs(None, None, 1, 0, db, user)
            assert page.total == (0 if revocation == "user" else 1)
            assert [row.id for row in page.data] == ([] if revocation == "user" else [chat.id])
            assert router.list_runs(None, None, 1, 1, db, user).data == []
            for read in (router.get_run, router.stream_run_events):
                with pytest.raises(HTTPException) as denied:
                    read(mail.id, db=db, current_user=user)
                assert denied.value.status_code == 404
            monkeypatch.setattr(
                router, "runtime_client", lambda: pytest.fail("Denied control reached Hermes")
            )
            for control, kwargs in (
                (router.stop_run, {}),
                (router.steer_run, {"body": HermesSteerRequest(input="change")}),
                (
                    router.resolve_approval,
                    {"body": HermesApprovalDecision(request_id="pending", choice="once")},
                ),
            ):
                with pytest.raises(HTTPException) as denied:
                    await control(mail.id, db=db, current_user=user, **kwargs)
                assert denied.value.status_code == 404
            db.refresh(mail)
            assert mail.status == "pending"
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("revoked_app", ["mail", "chatbot"])
async def test_open_run_stream_stops_before_next_batch_after_app_revocation(
    application_postgres_dsn, monkeypatch, revoked_app
):
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.hermes import router

    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            run = stage(db, binding, None, kind="workload", owner_app_id="mail")
            repo = HermesRunRepository(db)
            repo.append_event(run.id, {"event": "run.progress", "message": "before revocation"})
            db.commit()
            initial_events = repo.list_events_after(run.id, after_sequence=0)
            monkeypatch.setattr(router, "get_session_factory", lambda: sessionmaker(engine))
            stream = router._event_stream(run_id=run.id, user_id=user.id, after_sequence=0)
            for event in initial_events:
                assert f"id: {event.sequence}\n" in await anext(stream)
            with Session(engine) as authority:
                authority.get(CompanyAppControl, revoked_app).enabled = False
                HermesRunRepository(authority).append_event(
                    run.id, {"event": "run.progress", "message": "private result after revocation"}
                )
                authority.commit()
            assert await anext(stream) == 'event: error\ndata: {"code":"hermes.access_revoked"}\n\n'
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["read", "write", "upload"])
async def test_slow_file_transfer_keeps_other_requests_responsive(
    application_postgres_dsn, monkeypatch, operation
):
    import asyncio
    import base64
    import threading
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.core.db import get_db_session
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.hermes import mcp_router, file_router
    from open_work_hub_api.domains.auth.dependencies import require_current_user
    from open_work_hub_api.domains.hermes.service import mcp_profile_bearer_secret

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine)
    monkeypatch.setattr(mcp_router, "get_session_factory", lambda: factory)
    entered, release = threading.Event(), threading.Event()
    objects = {}
    armed = False
    event_loop_thread = threading.get_ident()

    def delay():
        if armed:
            assert threading.get_ident() != event_loop_thread
            entered.set()
            assert release.wait(timeout=5), "Other requests did not run during storage I/O"

    class StoredBody(BytesIO):
        def release_conn(self):
            pass

    class Store:
        def put_object(self, _bucket, key, data, length, **kwargs):
            delay()
            objects[key] = data.read(length)

        def get_object(self, _bucket, key):
            delay()
            return StoredBody(objects[key])

    monkeypatch.setattr(files, "get_minio_client", lambda: Store())
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    settings = get_settings().model_copy(
        update={"hermes_mcp_shared_secret": SecretStr("synthetic-file-transfer-secret")}
    )
    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    try:
        with factory() as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            session = session_for(db, binding)
            run = stage(db, binding, session)
            run.hermes_run_id = "run_file_transfer"
            run.status = "running"
            db.commit()
            row = files.save_file(db, session=session, path="saved.txt", data=b"saved")
            params = (
                {"id": row.id}
                if operation == "read"
                else {"path": "new.txt", "data": base64.b64encode(b"new").decode()}
            )
            profile = binding.profile_name
            session_id, user_id = session.id, user.id
            if operation == "upload":
                run.status = "completed"
                db.commit()
            token = mcp_profile_bearer_secret(settings, profile)
        app = FastAPI()
        app.include_router(mcp_router.router)
        app.include_router(file_router.router)
        app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id=user_id)

        def get_db():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db_session] = get_db
        headers = {"Authorization": f"Bearer {token}", "X-Hermes-Run-Id": "run_file_transfer"}
        armed = True
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            url = f"/internal/hermes/mcp?profile={profile}"
            transfer = asyncio.create_task(
                client.post(
                    f"/sessions/{session_id}/files",
                    headers={"Content-Type": "application/octet-stream", "X-File-Name": "new.txt"},
                    content=b"new",
                )
                if operation == "upload"
                else client.post(
                    url,
                    headers=headers,
                    json={"id": 1, "method": f"owh/files/{operation}", "params": params},
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 2), "Storage transfer did not start"
                ping = await asyncio.wait_for(
                    client.post(url, headers=headers, json={"id": 2, "method": "ping"}), timeout=1
                )
                assert ping.status_code == 200 and ping.json()["result"] == {}
            finally:
                release.set()
            response = await transfer
            assert (
                response.status_code == (201 if operation == "upload" else 200)
                and "error" not in response.json()
            )
            if operation == "upload":
                assert response.json()["relative_path"] == "new.txt"
                return
            if operation == "read":
                assert base64.b64decode(response.json()["result"]["data"]) == b"saved"
            else:
                assert response.json()["result"]["relative_path"] == "new.txt"
    finally:
        release.set()
        engine.dispose()


@pytest.mark.anyio
async def test_upload_rechecks_app_admission_after_receiving_body(
    application_postgres_dsn, monkeypatch
):
    from starlette.requests import Request
    from open_work_hub_api.domains.auth.models import CompanyAppControl
    from open_work_hub_api.domains.hermes import file_router

    engine = create_engine(application_postgres_dsn)
    monkeypatch.setattr(
        file_router,
        "save_file",
        lambda *args, **kwargs: pytest.fail("Revoked upload reached storage"),
    )
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            session = session_for(db, binding)
            db.commit()

            async def receive():
                with Session(engine) as authority:
                    authority.get(CompanyAppControl, "chatbot").enabled = False
                    authority.commit()
                return {"type": "http.request", "body": b"saved", "more_body": False}

            request = Request(
                {"type": "http", "headers": [(b"content-type", b"application/octet-stream")]},
                receive,
            )
            with pytest.raises(HTTPException) as denied:
                await file_router.upload_file(session.id, request, "saved.txt", db, user)
            assert denied.value.status_code == 403
    finally:
        engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("saturation", ["default", "operations", "both"])
async def test_structured_callback_completes_while_callers_exhaust_thread_capacity(
    application_postgres_dsn, monkeypatch, saturation
):
    import asyncio
    import threading
    from anyio import CapacityLimiter, to_thread
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr
    from sqlalchemy.orm import sessionmaker
    from open_work_hub_api.core.settings import get_settings
    from open_work_hub_api.domains.hermes import mcp_router
    from open_work_hub_api.domains.hermes.service import mcp_profile_bearer_secret

    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine)
    monkeypatch.setattr(mcp_router, "get_session_factory", lambda: factory)
    settings = get_settings().model_copy(
        update={"hermes_mcp_shared_secret": SecretStr("synthetic-capacity-secret")}
    )
    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    default = to_thread.current_default_thread_limiter()
    previous_tokens = default.total_tokens
    default.total_tokens = 1
    operation_token = mcp_router._OPERATION_THREADS.set(CapacityLimiter(1))
    release = threading.Event()
    waiters = []

    def hold(entered):
        entered.set()
        assert release.wait(timeout=5), "Callback could not release waiting callers"

    try:
        with factory() as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            run = stage(
                db,
                binding,
                None,
                kind="workload",
                workload_id="chatbot",
                output_schema={
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            )
            run.hermes_run_id = "run_saturated_callback"
            run.status = "running"
            db.commit()
            run_id, profile = run.id, binding.profile_name
            token = mcp_profile_bearer_secret(settings, profile)
        for kind in ("default", "operations") if saturation == "both" else (saturation,):
            entered = threading.Event()
            call = (
                to_thread.run_sync(hold, entered)
                if kind == "default"
                else mcp_router._run_callback(hold, entered, operation=True)
            )
            waiters.append(asyncio.create_task(call))
            assert await asyncio.to_thread(entered.wait, 1)
        app = FastAPI()
        app.include_router(mcp_router.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await asyncio.wait_for(
                client.post(
                    f"/internal/hermes/mcp?profile={profile}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Hermes-Run-Id": "run_saturated_callback",
                    },
                    json={"id": 1, "method": "owh/submit", "params": {"result": {"value": 42}}},
                ),
                timeout=2,
            )
            assert response.status_code == 200
            assert response.json()["result"] == {"accepted": True}
        with factory() as db:
            assert db.get(HermesRunProjection, run_id).output_payload == {"value": 42}
        assert all(not task.done() for task in waiters)
    finally:
        release.set()
        await asyncio.gather(*waiters)
        default.total_tokens = previous_tokens
        mcp_router._OPERATION_THREADS.reset(operation_token)
        engine.dispose()
