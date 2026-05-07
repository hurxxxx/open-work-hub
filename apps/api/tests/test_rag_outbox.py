from __future__ import annotations

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.core.telemetry import (
    bootstrap_telemetry,
    current_trace_id,
    get_tracer_provider,
    start_as_current_span,
)
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.rag.contracts import RagSyncLane, RagSyncOperation, RagTraceContext
from ai_do_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
import ai_do_api.domains.rag.outbox as rag_outbox
from ai_do_api.domains.rag.outbox import (
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )
    session = Session(engine)
    session.add(
        Workspace(
            id="ws-1",
            key="ws-1",
            name="Workspace 1",
            description="",
            active=True,
        )
    )
    session.commit()
    return session


def _stub_celery(monkeypatch, published: list[tuple[str, list[str], str]]) -> None:
    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            assert retry is False
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    monkeypatch.setattr(rag_outbox, "_get_celery_client", lambda: _FakeCeleryClient())


def test_enqueue_rag_sync_job_persists_resource_job() -> None:
    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-1",
                operation=RagSyncOperation.VISIBILITY_UPDATE,
                lane=RagSyncLane.BACKFILL,
                content_checksum="content-v1",
                visibility_checksum="vis-v2",
                trace_context=RagTraceContext(
                    traceparent="00-abcdef1234567890abcdef1234567890-1234567890abcdef-01"
                ),
            )

        stored = session.scalar(select(RagSyncJob).where(RagSyncJob.id == job.id))
        assert stored is not None
        assert stored.workspace_id == "ws-1"
        assert stored.lane == "backfill"
        assert stored.operation == "visibility_update"
        assert stored.content_checksum == "content-v1"
        assert stored.visibility_checksum == "vis-v2"
        assert stored.trace_context == {
            "traceparent": "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01",
            "tracestate": None,
            "baggage": {},
        }
    finally:
        session.close()


def test_enqueue_rag_visibility_recompute_job_persists_cursor() -> None:
    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-1",
                cursor={"resource_type": "doc", "offset": 10},
                trace_context={"traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"},
            )

        stored = session.scalar(
            select(RagVisibilityRecomputeJob).where(RagVisibilityRecomputeJob.id == job.id)
        )
        assert stored is not None
        assert stored.scope_type == "workspace_membership"
        assert stored.scope_id == "binding-1"
        assert stored.cursor == {"resource_type": "doc", "offset": 10}
        assert stored.trace_context == {
            "traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"
        }
    finally:
        session.close()


def test_enqueue_rag_sync_job_captures_current_trace_context() -> None:
    bootstrap_telemetry(service_name="ai-do-api-test")
    exporter = InMemorySpanExporter()
    provider = get_tracer_provider()
    assert provider is not None
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    session = _session()
    try:
        with start_as_current_span(
            tracer_name="tests.rag",
            span_name="tests.enqueue_rag_sync_job",
        ):
            expected_trace_id = current_trace_id()
            with session.begin():
                job = enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-2",
                )

        stored = session.scalar(select(RagSyncJob).where(RagSyncJob.id == job.id))
        assert stored is not None
        assert stored.trace_context is not None
        assert stored.trace_context["traceparent"].startswith("00-")
        assert expected_trace_id is not None
        assert expected_trace_id in stored.trace_context["traceparent"]
        spans = exporter.get_finished_spans()
        assert any(span.name == "tests.enqueue_rag_sync_job" for span in spans)
    finally:
        session.close()


def test_enqueue_rag_sync_job_allows_explicit_empty_trace_context() -> None:
    bootstrap_telemetry(service_name="ai-do-api-test")

    session = _session()
    try:
        with start_as_current_span(
            tracer_name="tests.rag",
            span_name="tests.enqueue_rag_sync_job.suppressed",
        ):
            with session.begin():
                job = enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-3",
                    trace_context={},
                )

        stored = session.scalar(select(RagSyncJob).where(RagSyncJob.id == job.id))
        assert stored is not None
        assert stored.trace_context == {}
    finally:
        session.close()


def test_enqueue_rag_sync_job_dedupes_pending_rows_and_upgrades_operation() -> None:
    session = _session()
    try:
        with session.begin():
            first = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-4",
                operation=RagSyncOperation.VISIBILITY_UPDATE,
                visibility_checksum="vis-v1",
            )
            second = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-4",
                operation=RagSyncOperation.UPSERT,
                content_checksum="content-v2",
            )

        rows = session.scalars(
            select(RagSyncJob).where(
                RagSyncJob.workspace_id == "ws-1",
                RagSyncJob.resource_type == "doc",
                RagSyncJob.resource_id == "doc-4",
            )
        ).all()
        assert len(rows) == 1
        assert second.id == first.id
        stored = rows[0]
        assert stored.operation == "upsert"
        assert stored.content_checksum == "content-v2"
        assert stored.visibility_checksum == "vis-v1"
    finally:
        session.close()


def test_enqueue_rag_sync_job_publishes_only_after_commit(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []

    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            assert retry is False
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    monkeypatch.setattr(rag_outbox, "_get_celery_client", lambda: _FakeCeleryClient())

    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-publish",
            )
            assert published == []

        assert published == [("rag.sync_resource", [job.id], "rag_sync_realtime")]
    finally:
        session.close()


def test_enqueue_rag_sync_job_ignores_nested_commit_before_outer_commit(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-nested-commit",
            )
            with session.begin_nested():
                pass
            assert published == []

        assert published == [("rag.sync_resource", [job.id], "rag_sync_realtime")]
    finally:
        session.close()


def test_enqueue_rag_sync_job_keeps_publish_after_nested_rollback(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-nested-rollback",
            )
            try:
                with session.begin_nested():
                    raise RuntimeError("rollback savepoint")
            except RuntimeError:
                pass
            assert published == []

        assert published == [("rag.sync_resource", [job.id], "rag_sync_realtime")]
    finally:
        session.close()


def test_enqueue_rag_visibility_job_publishes_after_commit(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []

    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            assert retry is False
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    monkeypatch.setattr(rag_outbox, "_get_celery_client", lambda: _FakeCeleryClient())

    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="workspace_membership",
                scope_id="binding-publish",
            )

        assert published == [("rag.recompute_visibility", [job.id], "rag_visibility_recompute")]
    finally:
        session.close()


def test_enqueue_rag_sync_job_preserves_pending_delete_over_later_upsert() -> None:
    session = _session()
    try:
        with session.begin():
            first = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-5",
                operation=RagSyncOperation.DELETE,
            )
            second = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-5",
                operation=RagSyncOperation.UPSERT,
                content_checksum="content-v3",
            )

        rows = session.scalars(
            select(RagSyncJob).where(
                RagSyncJob.workspace_id == "ws-1",
                RagSyncJob.resource_type == "doc",
                RagSyncJob.resource_id == "doc-5",
            )
        ).all()
        assert len(rows) == 1
        assert second.id == first.id
        stored = rows[0]
        assert stored.operation == "delete"
        assert stored.content_checksum == "content-v3"
    finally:
        session.close()


def test_enqueue_rag_visibility_recompute_job_dedupes_scope_and_merges_doc_ids() -> None:
    session = _session()
    try:
        with session.begin():
            first = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-1",
                cursor={"doc_ids": ["doc-1", "doc-2"]},
            )
            second = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="meeting",
                scope_id="meeting-1",
                cursor={"doc_ids": ["doc-2", "doc-3"]},
            )

        rows = session.scalars(
            select(RagVisibilityRecomputeJob).where(
                RagVisibilityRecomputeJob.workspace_id == "ws-1",
                RagVisibilityRecomputeJob.scope_type == "meeting",
                RagVisibilityRecomputeJob.scope_id == "meeting-1",
            )
        ).all()
        assert len(rows) == 1
        assert second.id == first.id
        stored = rows[0]
        assert stored.cursor == {"doc_ids": ["doc-1", "doc-2", "doc-3"]}
    finally:
        session.close()


def test_enqueue_rag_visibility_recompute_job_merges_issue_ids() -> None:
    session = _session()
    try:
        with session.begin():
            first = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="pms_meeting",
                scope_id="meeting-1",
                cursor={"issue_ids": ["issue-1", "issue-2"], "operation": "visibility_update"},
            )
            second = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="pms_meeting",
                scope_id="meeting-1",
                cursor={"issue_ids": ["issue-2", "issue-3"], "operation": "visibility_update"},
            )

        rows = session.scalars(
            select(RagVisibilityRecomputeJob).where(
                RagVisibilityRecomputeJob.workspace_id == "ws-1",
                RagVisibilityRecomputeJob.scope_type == "pms_meeting",
                RagVisibilityRecomputeJob.scope_id == "meeting-1",
            )
        ).all()
        assert len(rows) == 1
        assert second.id == first.id
        stored = rows[0]
        assert stored.cursor == {
            "issue_ids": ["issue-1", "issue-2", "issue-3"],
            "operation": "visibility_update",
        }
    finally:
        session.close()


def test_enqueue_rag_sync_job_dedupe_keeps_lane_in_identity() -> None:
    session = _session()
    try:
        with session.begin():
            realtime = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-6",
                lane=RagSyncLane.REALTIME,
            )
            backfill = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-6",
                lane=RagSyncLane.BACKFILL,
            )

        rows = session.scalars(
            select(RagSyncJob).where(
                RagSyncJob.workspace_id == "ws-1",
                RagSyncJob.resource_type == "doc",
                RagSyncJob.resource_id == "doc-6",
            )
        ).all()
        assert len(rows) == 2
        assert {row.id for row in rows} == {realtime.id, backfill.id}
        assert sorted(row.lane for row in rows) == ["backfill", "realtime"]
    finally:
        session.close()
