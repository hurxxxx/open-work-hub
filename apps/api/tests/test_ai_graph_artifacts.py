from __future__ import annotations
import asyncio
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from open_work_hub_api.domains.ai_artifacts.contracts import (
    AiArtifactCreate,
    AiArtifactIndexGenerationCreate,
    AiArtifactQueryCreate,
    AiArtifactSourceCreate,
    AiIndexGenerationCreate,
)
from open_work_hub_api.domains.ai_artifacts.models import (
    AiArtifact,
    AiArtifactIndexGeneration,
    AiArtifactQuery,
    AiArtifactSource,
    AiIndexGeneration,
)
from open_work_hub_api.domains.ai_artifacts.repository import (
    AiArtifactImmutableError,
    AiArtifactNotFoundError,
    AiArtifactRepository,
    AiIndexGenerationRepository,
)
from open_work_hub_api.domains.ai_artifacts.router import _query_source_response
from open_work_hub_api.domains.ai_graph.contracts import (
    AiGraphLlmRequest,
    AiGraphNodeResult,
    AiGraphNodeSpec,
    AiGraphRunRequest,
    AiGraphSpec,
)
from open_work_hub_api.domains.ai_graph.gateway_adapter import AiGatewayGraphAdapter
from open_work_hub_api.domains.ai_graph.dispatch import stage_graph_dispatch
from open_work_hub_api.domains.ai_graph.execution_registry import (
    execute_registered_ai_graph,
    register_ai_graph_executor,
    reset_ai_graph_executors,
)
from open_work_hub_api.domains.ai_graph.models import (
    AiGraphDispatchOutbox,
    AiGraphRun,
    AiGraphRunInput,
    AiGraphRunNodeProgress,
)
from open_work_hub_api.domains.ai_graph.repository import (
    AiGraphDispatchRepository,
    AiGraphExecutionLeaseLostError,
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)
from open_work_hub_api.domains.ai_graph.router import _artifact_ids_by_run
from open_work_hub_api.domains.ai_graph.runtime import (
    AiGraphRuntimeContext,
    compile_graph,
    run_graph,
)
from open_work_hub_api.domains.conversations.models import Conversation, ConversationTurn


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (
        Conversation.__table__,
        ConversationTurn.__table__,
        AiGraphRun.__table__,
        AiGraphRunInput.__table__,
        AiGraphRunNodeProgress.__table__,
        AiGraphDispatchOutbox.__table__,
        AiIndexGeneration.__table__,
        AiArtifact.__table__,
        AiArtifactSource.__table__,
        AiArtifactQuery.__table__,
        AiArtifactIndexGeneration.__table__,
    ):
        table.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _linear_spec() -> AiGraphSpec:
    return AiGraphSpec(
        graph_id="test.report",
        graph_version="1",
        nodes=(
            AiGraphNodeSpec(node_id="collect", purpose="Collect evidence"),
            AiGraphNodeSpec(
                node_id="write",
                purpose="Write report",
                depends_on=("collect",),
            ),
        ),
    )


def _run_request(*, inputs: dict | None = None) -> AiGraphRunRequest:
    return AiGraphRunRequest(
        workspace_id="workspace-1",
        requested_by_user_id="user-1",
        app_id="docs",
        graph=_linear_spec(),
        inputs=inputs or {"question": "접속 오류를 보고해줘"},
        conversation_id="conversation-1",
    )


def _artifact_create(
    *,
    artifact_type: str = "report",
    content_text: str | None = "# 보고서",
    payload: dict | None = None,
) -> AiArtifactCreate:
    return AiArtifactCreate(
        workspace_id="workspace-1",
        owner_user_id="user-1",
        app_id="docs",
        artifact_type=artifact_type,
        title="접속 오류 분석",
        content_text=content_text,
        payload=payload,
        conversation_id="conversation-1",
    )


def test_graph_contract_rejects_cycles_and_ambiguous_conditional_edges() -> None:
    with pytest.raises(ValidationError, match="acyclic"):
        AiGraphSpec(
            graph_id="cycle",
            graph_version="1",
            nodes=(
                AiGraphNodeSpec(node_id="a", purpose="a", depends_on=("b",)),
                AiGraphNodeSpec(node_id="b", purpose="b", depends_on=("a",)),
            ),
        )

    with pytest.raises(ValidationError, match="either by routes or dependencies"):
        AiGraphSpec(
            graph_id="ambiguous",
            graph_version="1",
            nodes=(
                AiGraphNodeSpec(
                    node_id="route",
                    purpose="route",
                    routes={"report": "report"},
                ),
                AiGraphNodeSpec(
                    node_id="report",
                    purpose="report",
                    depends_on=("route",),
                ),
            ),
        )


def test_langgraph_conditional_route_executes_only_selected_branch() -> None:
    completed: list[str] = []

    async def route(_state, _context):
        return AiGraphNodeResult(output={"intent": "report"}, route="report")

    async def report(_state, _context):
        return AiGraphNodeResult(output="# grounded report")

    async def direct(_state, _context):
        raise AssertionError("unselected branch executed")

    async def progress(node_id: str) -> None:
        completed.append(node_id)

    spec = AiGraphSpec(
        graph_id="conditional",
        graph_version="1",
        nodes=(
            AiGraphNodeSpec(
                node_id="route",
                purpose="Route request",
                routes={"report": "report", "direct": "direct"},
            ),
            AiGraphNodeSpec(node_id="report", purpose="Write report"),
            AiGraphNodeSpec(node_id="direct", purpose="Answer directly"),
        ),
    )
    graph = compile_graph(
        spec,
        {"route": route, "report": report, "direct": direct},
        InMemorySaver(),
    )

    async def invoke() -> dict:
        return await graph.graph.ainvoke(
            {"inputs": {}, "outputs": {}, "errors": {}, "routes": {}},
            config={"configurable": {"thread_id": "run-1"}},
            context=AiGraphRuntimeContext(
                run_id="run-1",
                workspace_id="workspace-1",
                requested_by_user_id="user-1",
                app_id="docs",
                conversation_id=None,
                progress_callback=progress,
            ),
        )

    state = asyncio.run(invoke())
    assert state["outputs"] == {
        "route": {"intent": "report"},
        "report": "# grounded report",
    }
    assert completed == ["route", "report"]


def test_graph_llm_adapter_uses_registered_gateway_only(monkeypatch) -> None:
    import open_work_hub_api.domains.ai_graph.gateway_adapter as adapter_module

    observed: dict[str, object] = {}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            observed["committed"] = True

        def rollback(self):
            observed["rolled_back"] = True

    def execute(workload_id, context, _db, **kwargs):
        observed["workload_id"] = workload_id
        observed["context"] = context
        observed["kwargs"] = kwargs
        return SimpleNamespace(
            completion=SimpleNamespace(
                text="grounded",
                model="routed-model",
                usage={"input_tokens": 10},
                finish_reason="stop",
            ),
            decision=SimpleNamespace(chosen_pool="local"),
        )

    monkeypatch.setattr(
        adapter_module,
        "resolve_llm_workload",
        lambda _workload_id: SimpleNamespace(
            workload_id="report.generate",
            app_ids=("docs",),
        ),
    )
    monkeypatch.setattr(adapter_module, "execute_llm", execute)
    adapter = AiGatewayGraphAdapter(session_factory=lambda: FakeSession())
    result = adapter.invoke(
        AiGraphLlmRequest(
            workload_id="report.generate",
            app_id="docs",
            workspace_id="workspace-1",
            source="worker.test",
            messages=[{"role": "user", "content": "report"}],
            graph_run_id="run-1",
        )
    )

    assert result.text == "grounded"
    assert result.chosen_pool == "local"
    assert observed["workload_id"] == "report.generate"
    assert observed["kwargs"]["agent_run_id"] == "run-1"
    assert observed["committed"] is True


def test_projection_progress_and_bootstrap_input_are_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        run_repository = AiGraphRunRepository(db)
        run = run_repository.create(_run_request())
        AiGraphRunInputRepository(db).create(
            graph_run_id=run.id,
            payload={"question": "접속 오류"},
            schema_version=1,
        )
        run_repository.transition(run.id, "running")
        run_repository.advance(run.id, node_id="collect")
        run_repository.advance(run.id, node_id="collect")
        db.commit()

        assert run.current_step == 1
        assert run.progress_percent == 50
        assert run.stage == "collect"
        assert db.get(AiGraphRunInput, run.id).payload_json == {"question": "접속 오류"}
        assert len(db.query(AiGraphRunNodeProgress).all()) == 1

        run_repository.transition(run.id, "completed")
        AiGraphRunInputRepository(db).delete_after_terminal(run.id)
        db.commit()
        assert db.get(AiGraphRunInput, run.id) is None


def test_dispatch_outbox_can_be_claimed_retried_and_acked(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        prepared = stage_graph_dispatch(
            db,
            run_request=_run_request(),
            pending_artifact=_artifact_create(
                content_text=None,
                payload={"request": "접속 오류를 보고해줘"},
            ),
        )
        db.commit()
        assert prepared.outbox.payload_ref == f"ai-graph-input:{prepared.graph_run.id}"
        assert prepared.pending_artifact.status == "pending"

        repository = AiGraphDispatchRepository(db)
        claimed = repository.claim_due(claim_token="publisher-1")
        assert [item.id for item in claimed] == [prepared.outbox.id]
        repository.mark_retry(
            prepared.outbox.id,
            claim_token="publisher-1",
            error_code="broker.unavailable",
            retry_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
        )
        claimed_again = repository.claim_due(claim_token="publisher-2")
        repository.mark_dispatched(
            claimed_again[0].id,
            claim_token="publisher-2",
            celery_task_id="celery-1",
        )
        db.commit()
        assert prepared.outbox.status == "dispatched"
        assert prepared.outbox.attempts == 2

        completed = AiArtifactRepository(db).create_completed(
            _artifact_create().model_copy(update={"graph_run_id": prepared.graph_run.id})
        )
        db.commit()
        assert _artifact_ids_by_run(
            db,
            [prepared.graph_run.id],
            workspace_id="workspace-1",
            user_id="user-1",
        ) == {prepared.graph_run.id: completed.id}


def test_dispatch_rejects_incoherent_artifact_before_staging_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        mismatched = _artifact_create().model_copy(
            update={
                "workspace_id": "workspace-2",
                "owner_user_id": "user-2",
                "app_id": "another-app",
                "conversation_id": "conversation-2",
                "visibility": "workspace",
                "graph_run_id": "already-bound",
            }
        )
        with pytest.raises(
            ValueError,
            match=(
                "workspace_id, app_id, owner_user_id, conversation_id, visibility, graph_run_id"
            ),
        ):
            stage_graph_dispatch(
                db,
                run_request=_run_request(),
                pending_artifact=mismatched,
            )

        assert db.query(AiGraphRun).count() == 0
        assert db.query(AiArtifact).count() == 0
        assert db.query(AiGraphDispatchOutbox).count() == 0


def test_dispatch_can_stage_artifact_free_app_owned_work(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        prepared = stage_graph_dispatch(db, run_request=_run_request())
        db.commit()

        assert prepared.pending_artifact is None
        assert prepared.run_input.graph_run_id == prepared.graph_run.id
        assert prepared.outbox.graph_run_id == prepared.graph_run.id
        assert db.query(AiArtifact).count() == 0


def test_graph_run_artifact_lookup_enforces_acl_and_prefers_completed_artifact(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        run_repository = AiGraphRunRepository(db)
        preferred_run = run_repository.create(_run_request())
        private_foreign_run = run_repository.create(_run_request())
        shared_run = run_repository.create(_run_request())
        artifacts = AiArtifactRepository(db)

        artifacts.create_pending(
            _artifact_create(content_text=None).model_copy(
                update={"graph_run_id": preferred_run.id}
            )
        )
        preferred = artifacts.create_completed(
            _artifact_create().model_copy(update={"graph_run_id": preferred_run.id})
        )
        artifacts.create_completed(
            _artifact_create().model_copy(
                update={
                    "graph_run_id": preferred_run.id,
                    "owner_user_id": "user-2",
                }
            )
        )
        artifacts.create_completed(
            _artifact_create().model_copy(
                update={
                    "graph_run_id": preferred_run.id,
                    "workspace_id": "workspace-2",
                    "visibility": "workspace",
                }
            )
        )
        artifacts.create_completed(
            _artifact_create().model_copy(
                update={
                    "graph_run_id": private_foreign_run.id,
                    "owner_user_id": "user-2",
                }
            )
        )
        shared = artifacts.create_completed(
            _artifact_create().model_copy(
                update={
                    "graph_run_id": shared_run.id,
                    "owner_user_id": "user-2",
                    "visibility": "workspace",
                }
            )
        )
        db.commit()

        assert _artifact_ids_by_run(
            db,
            [preferred_run.id, private_foreign_run.id, shared_run.id],
            workspace_id="workspace-1",
            user_id="user-1",
        ) == {
            preferred_run.id: preferred.id,
            shared_run.id: shared.id,
        }


def test_graph_execution_claim_skips_duplicates_and_reclaims_stale_lease(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with session_factory() as db:
        repository = AiGraphRunRepository(db)
        run = repository.create(_run_request())
        first = repository.claim_execution(
            run.id,
            claim_token="worker-1",
            now=now,
            lease_duration=timedelta(minutes=5),
        )
        duplicate = repository.claim_execution(
            run.id,
            claim_token="worker-2",
            now=now + timedelta(minutes=1),
        )
        assert first.acquired is True
        assert first.resume_from_checkpoint is False
        assert duplicate.acquired is False
        assert duplicate.reason == "active_lease"

        reclaimed = repository.claim_execution(
            run.id,
            claim_token="worker-3",
            now=now + timedelta(minutes=6),
        )
        assert reclaimed.acquired is True
        assert reclaimed.reason == "stale_lease"
        assert reclaimed.resume_from_checkpoint is True
        assert run.execution_claim_token == "worker-3"
        assert run.execution_attempts == 2
        with pytest.raises(AiGraphExecutionLeaseLostError):
            repository.transition(
                run.id,
                "completed",
                claim_token="worker-1",
            )
        with pytest.raises(AiGraphExecutionLeaseLostError):
            repository.transition(run.id, "failed")
        with pytest.raises(AiGraphExecutionLeaseLostError):
            repository.advance(run.id, node_id="collect")


def test_graph_executor_registry_resolves_exact_graph_version(
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    import open_work_hub_api.domains.ai_graph.execution_registry as registry_module

    calls: list[str] = []
    request_v1 = _run_request()
    request_v2 = request_v1.model_copy(
        update={
            "graph": request_v1.graph.model_copy(
                update={"graph_version": "2"},
            )
        }
    )
    with session_factory() as db:
        run_v1 = AiGraphRunRepository(db).create(request_v1)
        run_v2 = AiGraphRunRepository(db).create(request_v2)
        db.commit()

    monkeypatch.setattr(
        registry_module,
        "get_session_factory",
        lambda: session_factory,
    )
    reset_ai_graph_executors()
    try:
        register_ai_graph_executor(
            request_v1.graph.graph_id,
            request_v1.graph.graph_version,
            lambda run_id: calls.append(f"v1:{run_id}") or "v1",
        )
        assert execute_registered_ai_graph(run_v1.id) == "v1"
        with pytest.raises(LookupError, match="@2"):
            execute_registered_ai_graph(run_v2.id)
        assert calls == [f"v1:{run_v1.id}"]
    finally:
        reset_ai_graph_executors()


def test_graph_execution_lease_renewal_is_fenced_by_claim_token(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with session_factory() as db:
        repository = AiGraphRunRepository(db)
        run = repository.create(_run_request())
        repository.claim_execution(
            run.id,
            claim_token="worker-1",
            now=now,
            lease_duration=timedelta(seconds=1),
        )
        repository.renew_execution_lease(
            run.id,
            claim_token="worker-1",
            now=now + timedelta(milliseconds=500),
            lease_duration=timedelta(minutes=5),
        )
        assert run.execution_lease_expires_at == now + timedelta(
            minutes=5,
            milliseconds=500,
        )
        with pytest.raises(AiGraphExecutionLeaseLostError):
            repository.renew_execution_lease(
                run.id,
                claim_token="worker-2",
            )


def test_run_graph_renews_execution_lease_while_node_is_running(
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    import open_work_hub_api.domains.ai_graph.runtime as runtime_module

    renewals: list[str] = []
    original = AiGraphRunRepository.renew_execution_lease

    def observe_renewal(self, run_id: str, **kwargs):
        renewals.append(run_id)
        return original(self, run_id, **kwargs)

    monkeypatch.setattr(
        runtime_module,
        "_EXECUTION_LEASE_HEARTBEAT_INTERVAL_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        AiGraphRunRepository,
        "renew_execution_lease",
        observe_renewal,
    )

    async def collect(_state, _context):
        await asyncio.sleep(0.05)
        return AiGraphNodeResult(output={"count": 1})

    async def write(_state, _context):
        return AiGraphNodeResult(output="# report")

    result = asyncio.run(
        run_graph(
            compile_graph(
                _linear_spec(),
                {"collect": collect, "write": write},
                InMemorySaver(),
            ),
            _run_request(),
            session_factory=session_factory,
        )
    )

    assert result.status == "completed"
    assert renewals == [result.run_id] * len(renewals)
    assert len(renewals) >= 1


def test_run_graph_invokes_nodes_once_and_terminal_duplicate_is_skipped(
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[str] = []

    async def collect(_state, _context):
        calls.append("collect")
        return AiGraphNodeResult(output={"count": 1})

    async def write(_state, _context):
        calls.append("write")
        return AiGraphNodeResult(output="# report")

    compiled = compile_graph(
        _linear_spec(),
        {"collect": collect, "write": write},
        InMemorySaver(),
    )
    first = asyncio.run(
        run_graph(
            compiled,
            _run_request(),
            session_factory=session_factory,
        )
    )
    duplicate = asyncio.run(
        run_graph(
            compiled,
            _run_request(),
            run_id=first.run_id,
            session_factory=session_factory,
        )
    )

    assert first.status == "completed"
    assert duplicate.status == "skipped"
    assert duplicate.reason == "terminal"
    assert calls == ["collect", "write"]
    with session_factory() as db:
        run = AiGraphRunRepository(db).require(first.run_id)
        assert run.execution_attempts == 1
        assert run.current_step == 2
        assert db.query(AiGraphRunNodeProgress).count() == 2


def test_run_graph_logs_terminal_failure_with_run_context(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    log_records: list[tuple[str, dict[str, object]]] = []

    def record_error(message: str, *, extra: dict[str, object]) -> None:
        log_records.append((message, extra))

    monkeypatch.setattr(
        "open_work_hub_api.domains.ai_graph.runtime.logger.error",
        record_error,
    )

    async def collect(_state, _context):
        raise RuntimeError("fixture_graph_failure")

    async def write(_state, _context):
        return AiGraphNodeResult(output="# unreachable")

    result = asyncio.run(
        run_graph(
            compile_graph(
                _linear_spec(),
                {"collect": collect, "write": write},
                InMemorySaver(),
            ),
            _run_request(),
            session_factory=session_factory,
        )
    )

    assert result.status == "failed"
    assert result.errors == {"graph": "graph_execution.RuntimeError"}
    record = next(extra for message, extra in log_records if message == "AI graph execution failed")
    assert record["graph_run_id"] == result.run_id
    assert record["graph_id"] == "test.report"
    assert record["graph_version"] == "1"
    assert record["error_code"] == "graph_execution.RuntimeError"
    assert record["error_detail"] == "fixture_graph_failure"
    node_record = next(
        extra for message, extra in log_records if message == "AI graph node execution failed"
    )
    assert node_record["graph_run_id"] == result.run_id
    assert node_record["node_id"] == "collect"
    assert node_record["error_type"] == "RuntimeError"
    assert node_record["error_detail"] == "fixture_graph_failure"


def test_run_graph_resumes_completed_checkpoint_after_stale_lease_without_reexecution(
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[str] = []

    async def collect(_state, _context):
        calls.append("collect")
        return AiGraphNodeResult(output={"count": 1})

    async def write(_state, _context):
        calls.append("write")
        return AiGraphNodeResult(output="# report")

    compiled = compile_graph(
        _linear_spec(),
        {"collect": collect, "write": write},
        InMemorySaver(),
    )
    request = _run_request()
    with session_factory() as db:
        repository = AiGraphRunRepository(db)
        run = repository.create(request)
        repository.claim_execution(
            run.id,
            claim_token="crashed-worker",
            now=datetime(2026, 7, 26, 0, 0),
            lease_duration=timedelta(seconds=1),
        )
        run_id = run.id
        db.commit()

    async def seed_checkpoint() -> None:
        await compiled.graph.ainvoke(
            {
                "inputs": request.inputs,
                "outputs": {},
                "errors": {},
                "routes": {},
            },
            config={
                "configurable": {
                    "thread_id": run_id,
                    "checkpoint_ns": request.checkpoint_ns,
                }
            },
            context=AiGraphRuntimeContext(
                run_id=run_id,
                workspace_id=request.workspace_id,
                requested_by_user_id=request.requested_by_user_id,
                app_id=request.app_id,
                conversation_id=request.conversation_id,
                progress_callback=lambda _node_id: asyncio.sleep(0),
            ),
        )

    asyncio.run(seed_checkpoint())
    assert calls == ["collect", "write"]
    resumed = asyncio.run(
        run_graph(
            compiled,
            request,
            run_id=run_id,
            session_factory=session_factory,
        )
    )

    assert resumed.status == "completed"
    assert resumed.outputs == {"collect": {"count": 1}, "write": "# report"}
    assert calls == ["collect", "write"]
    with session_factory() as db:
        run = AiGraphRunRepository(db).require(run_id)
        assert run.execution_attempts == 2
        assert run.status == "completed"


def test_artifact_persists_grid_query_lineage_and_becomes_immutable(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        generation = AiIndexGenerationRepository(db).create_staging(
            AiIndexGenerationCreate(
                workspace_id="workspace-1",
                app_id="docs",
                generation_key="docs-20260726",
                backend="pgvector",
                source_namespace="docs",
                embedding_provider="local",
                embedding_model="bge-m3",
                embedding_dimensions=1024,
                document_count=20,
                chunk_count=100,
            )
        )
        generation_repository = AiIndexGenerationRepository(db)
        generation_repository.record_validation(
            generation.id,
            passed=True,
            validation={"recallAt10": 0.88},
        )
        generation_repository.activate(generation.id)

        repository = AiArtifactRepository(db)
        artifact = repository.create_completed(
            _artifact_create(),
            sources=(
                AiArtifactSourceCreate(
                    source_kind="document",
                    source_ref="issue:42",
                    grid_columns=[
                        {"key": "status", "label": "상태"},
                        {"key": "count", "label": "건수"},
                    ],
                    grid_rows=[{"status": "open", "count": 3}],
                    row_count=1,
                ),
            ),
            queries=(
                AiArtifactQueryCreate(
                    query_kind="sql_family",
                    family_id="issues.by_status",
                    query_spec={"family": "issues.by_status"},
                    statement_text=(
                        "SELECT status, count(*) FROM issues WHERE region = :region GROUP BY status"
                    ),
                    typed_params={"region": {"type": "string", "value": "중부"}},
                    execution_status="completed",
                    result_schema=[
                        {"name": "status", "type": "string"},
                        {"name": "count", "type": "integer"},
                    ],
                    result_rows=[{"status": "open", "count": 3}],
                    row_count=1,
                    duration_ms=14,
                    payload_bytes=31,
                    exactness="exact",
                ),
            ),
            index_generations=(AiArtifactIndexGenerationCreate(index_generation_id=generation.id),),
        )
        db.commit()
        loaded = repository.require(artifact.id, eager=True)

        assert re.fullmatch(r"AIR-\d{8}-\d{10}", loaded.artifact_number)
        assert loaded.queries[0].typed_params_json["region"]["value"] == "중부"
        assert loaded.queries[0].result_rows_json == [{"status": "open", "count": 3}]
        assert loaded.sources[0].grid_rows_json == [{"status": "open", "count": 3}]
        assert loaded.index_generations[0].index_generation_id == generation.id
        assert loaded.content_sha256
        query_source = _query_source_response(loaded.queries[0], ordinal=1)
        assert query_source.query_id == loaded.queries[0].id
        assert query_source.source_kind == "sql_query"
        assert query_source.grid_columns[0]["key"] == "status"
        assert query_source.grid_rows == [{"status": "open", "count": 3}]
        with pytest.raises(AiArtifactImmutableError):
            repository.add_source(
                loaded,
                AiArtifactSourceCreate(source_kind="document", source_ref="issue:99"),
            )


def test_ownerless_artifacts_must_be_workspace_visible() -> None:
    with pytest.raises(ValidationError, match="workspace visibility"):
        AiArtifactCreate(
            workspace_id="workspace-1",
            app_id="docs",
            artifact_type="analysis",
            title="system analysis",
            content_text="analysis",
            visibility="private",
        )


def test_completed_artifact_owner_can_change_only_visibility(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        repository = AiArtifactRepository(db)
        artifact = repository.create_completed(_artifact_create())
        db.commit()
        content_sha256 = artifact.content_sha256

        shared, changed = repository.set_completed_visibility(
            artifact.artifact_number,
            workspace_id="workspace-1",
            owner_user_id="user-1",
            visibility="workspace",
            expected_app_id="docs",
            expected_artifact_type="report",
        )
        db.commit()

        assert changed is True
        assert shared.id == artifact.id
        assert shared.visibility == "workspace"
        assert shared.content_text == "# 보고서"
        assert shared.content_sha256 == content_sha256
        unchanged, changed = repository.set_completed_visibility(
            artifact.id,
            workspace_id="workspace-1",
            owner_user_id="user-1",
            visibility="workspace",
        )
        assert unchanged is shared
        assert changed is False


def test_artifact_visibility_change_requires_completed_owned_artifact(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        repository = AiArtifactRepository(db)
        completed = repository.create_completed(_artifact_create())
        building = repository.create_building(
            _artifact_create(content_text=None).model_copy(update={"conversation_id": None})
        )
        db.commit()

        with pytest.raises(AiArtifactNotFoundError):
            repository.set_completed_visibility(
                completed.id,
                workspace_id="workspace-1",
                owner_user_id="another-user",
                visibility="workspace",
            )
        with pytest.raises(AiArtifactNotFoundError):
            repository.set_completed_visibility(
                completed.id,
                workspace_id="another-workspace",
                owner_user_id="user-1",
                visibility="workspace",
            )
        with pytest.raises(AiArtifactNotFoundError):
            repository.set_completed_visibility(
                building.id,
                workspace_id="workspace-1",
                owner_user_id="user-1",
                visibility="workspace",
            )
        with pytest.raises(AiArtifactNotFoundError):
            repository.set_completed_visibility(
                completed.id,
                workspace_id="workspace-1",
                owner_user_id="user-1",
                visibility="workspace",
                expected_app_id="another-app",
            )
        with pytest.raises(AiArtifactNotFoundError):
            repository.set_completed_visibility(
                completed.id,
                workspace_id="workspace-1",
                owner_user_id="user-1",
                visibility="workspace",
                expected_artifact_type="analysis",
            )
