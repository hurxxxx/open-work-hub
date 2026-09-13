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
async def test_model_snapshot_has_no_secret_and_auxiliary_follows_main():
    policy = HermesModelPolicy("local", "openai", "local-test", "http://model:8000/v1", "", 8192)
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
    assert config["delegation"]["provider"] == "auto"
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
async def test_workload_uses_durable_dispatch_and_validated_native_submission(
    application_postgres_dsn, monkeypatch
):
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
    try:
        with factory() as db:
            user, binding = seed(db)
            owner_id, binding_id, profile_name = user.id, binding.id, binding.profile_name
            db.merge(CompanyAppControl(app_id="chatbot", enabled=True))
            db.flush()
            db.merge(AppAccessPolicy(app_id="chatbot", audience="all"))
            db.commit()

        async def ensure(db, **kwargs):
            assert kwargs["user"].id == owner_id
            assert kwargs["model_policy"].route == "local"
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
                assert "owh_submit_result" in kwargs["instructions"]
                attempts.append(kwargs["idempotency_key"])
                return {"run_id": "run_native_fixture", "status": "running"}

            async def iter_run_events(self, profile, run_id):
                for result in ({"value": "wrong type"}, {"value": 42}):
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
        result = await workloads.run_workload(
            context,
            resolved,
            {"messages": [{"role": "user", "content": "Return a validated value"}]},
            timeout_seconds=10,
            output_schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        assert result["structured_output"] == {"value": 42}
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
