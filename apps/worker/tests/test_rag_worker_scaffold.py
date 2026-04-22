# ruff: noqa: E402

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from aidoo_api.core.db import Base  # noqa: E402
from aidoo_api.core.telemetry import (
    bootstrap_telemetry,
    get_tracer_provider,
    start_as_current_span,
)  # noqa: E402
from aidoo_api.domains.auth.models import User, Workspace  # noqa: E402
from aidoo_api.domains.docs.models import (  # noqa: E402
    DocMeetingAccess,
    NativeDoc,
    NativeDocContainer,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from aidoo_api.domains.rag.contracts import RagSyncOperation  # noqa: E402
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE  # noqa: E402
from aidoo_api.domains.rag.models import RagSyncJob  # noqa: E402
from aidoo_api.domains.rag.outbox import enqueue_rag_sync_job  # noqa: E402


def _worker_db_path(tmp_path: Path) -> Path:
    return tmp_path / "worker-rag.sqlite3"


def _worker_dsn(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _init_worker_db(
    db_path: Path,
    *,
    create_policy_table: bool,
    seed_policy_rows: bool,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        if create_policy_table:
            connection.execute(
                """
                CREATE TABLE llm_policies (
                    id TEXT PRIMARY KEY,
                    task_kind TEXT NOT NULL,
                    policy_mode TEXT NOT NULL,
                    description TEXT NOT NULL,
                    updated_by TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        if seed_policy_rows:
            connection.executemany(
                """
                INSERT INTO llm_policies (
                    id, task_kind, policy_mode, description, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "1",
                        "chatbot",
                        "local_only",
                        "Interactive chat — user-facing",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "2",
                        "meeting_summary",
                        "local_only",
                        "Meeting transcript summarization (worker)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "3",
                        "meeting_insight_actions",
                        "local_only",
                        "Meeting action-item extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "4",
                        "meeting_insight_decisions",
                        "local_only",
                        "Meeting decision extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "5",
                        "meeting_insight_followup",
                        "local_only",
                        "Meeting follow-up schedule extraction (worker/read refresh)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                    (
                        "6",
                        "batch_generation",
                        "local_only",
                        "Long-form batch generation (reports etc.)",
                        None,
                        "2026-04-18T00:00:00",
                        "2026-04-18T00:00:00",
                    ),
                ],
            )
        connection.commit()
    finally:
        connection.close()


def _reload_worker_module(module_name: str):
    for cached_name in list(sys.modules):
        if cached_name == "aidoo_worker" or cached_name.startswith("aidoo_worker."):
            sys.modules.pop(cached_name, None)
    return importlib.import_module(module_name)


def test_celery_routes_rag_tasks_to_dedicated_queues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))

    celery_module = _reload_worker_module("aidoo_worker.celery_app")
    routes = celery_module.celery_app.conf.task_routes

    assert routes["rag.sync_resource"]["queue"] == "rag_sync_realtime"
    assert routes["rag.sync_backfill_resource"]["queue"] == "rag_sync_backfill"
    assert routes["rag.recompute_visibility"]["queue"] == "rag_visibility_recompute"


def test_sync_resource_worker_span_inherits_outbox_trace_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
        ],
    )

    bootstrap_telemetry(service_name="aidoo-worker-test")
    exporter = InMemorySpanExporter()
    provider = get_tracer_provider()
    assert provider is not None
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with start_as_current_span(
        tracer_name="tests.worker",
        span_name="tests.rag_parent",
    ) as parent_span:
        parent_span_id = parent_span.get_span_context().span_id
        with Session(engine) as session:
            with session.begin():
                session.add(
                    Workspace(
                        id="ws-1",
                        key="ws-1",
                        name="Workspace 1",
                        description="",
                        active=True,
                    )
                )
                job = enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-1",
                )
                job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "disabled"
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert "tests.rag_parent" in spans
    assert "rag.sync_resource" in spans
    child_span = spans["rag.sync_resource"]
    assert child_span.parent is not None
    assert child_span.parent.span_id == parent_span_id
    assert child_span.context.trace_id == spans["tests.rag_parent"].context.trace_id


def test_sync_resource_worker_upserts_docs_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocContainer.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            job_id = job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    result = tasks_module.sync_resource.run(job_id)

    assert result == "succeeded"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name(NATIVE_DOC_RESOURCE_TYPE)
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is not None
    assert snapshot.resource_id == "doc-1"
    assert snapshot.resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert "worker sync content" in snapshot.text_content

    with Session(engine) as session:
        stored = session.get(RagSyncJob, job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1


def test_sync_resource_worker_deletes_docs_projection_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = _worker_db_path(tmp_path)
    _init_worker_db(
        db_path,
        create_policy_table=True,
        seed_policy_rows=True,
    )
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_RAG_ENABLED", "1")
    monkeypatch.setenv("DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX", "worker-rag-test")

    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocContainer.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            DocMeetingAccess.__table__,
            RagSyncJob.__table__,
        ],
    )

    with Session(engine) as session:
        with session.begin():
            session.add(
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                )
            )
            session.add(
                User(
                    id="user-1",
                    email="worker-doc-owner@aidoo.local",
                    full_name="Worker Doc Owner",
                    password_hash="hash",
                    status="active",
                )
            )
            session.add(
                NativeDoc(
                    id="doc-1",
                    workspace_id="ws-1",
                    owner_id="user-1",
                    title="Worker Synced Doc",
                    source_app="docs",
                    source_kind="manual",
                    generation_kind="human",
                )
            )
            session.add(
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Overview",
                    content_blocks=[{"type": "paragraph", "text": "worker sync content"}],
                    sort_order=0,
                    created_by_id="user-1",
                )
            )
            upsert_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
            )
            upsert_job_id = upsert_job.id

    tasks_module = _reload_worker_module("aidoo_worker.tasks.rag_sync")
    assert tasks_module.sync_resource.run(upsert_job_id) == "succeeded"

    with Session(engine) as session:
        with session.begin():
            delete_job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                resource_id="doc-1",
                operation=RagSyncOperation.DELETE,
            )
            delete_job_id = delete_job.id

    result = tasks_module.sync_resource.run(delete_job_id)

    assert result == "deleted"
    bundle = tasks_module._provider_bundle()
    collection = tasks_module._collection_name(NATIVE_DOC_RESOURCE_TYPE)
    snapshot = bundle.vector_index.snapshot_projection(collection=collection, chunk_id="doc-1:0")
    assert snapshot is None

    with Session(engine) as session:
        stored = session.get(RagSyncJob, delete_job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 1
