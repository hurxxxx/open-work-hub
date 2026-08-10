from __future__ import annotations

from dataclasses import replace

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.core.telemetry import (
    bootstrap_telemetry,
    current_trace_id,
    get_tracer_provider,
    start_as_current_span,
)
from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.rag.contracts import (
    RagScopeKind,
    RagSyncLane,
    RagSyncOperation,
    RagTraceContext,
)
from open_alm_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from open_alm_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_alm_api.domains.retrieval.projection_fencing import (
    ProjectionEventRef,
    record_projection_event,
)
import open_alm_api.domains.rag.outbox as rag_outbox
from open_alm_api.domains.rag.outbox import (
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from open_alm_api.domains.rag.source_adapter_registry import (
    RagResourceAdapter,
    RagVisibilityScopeAdapter,
    register_rag_resource_adapter,
    register_rag_visibility_scope_adapter,
    reset_rag_source_adapters,
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


def _versioned_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RetrievalPartition.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            RagSyncJob.__table__,
        ],
    )
    session = Session(engine)
    session.add_all(
        [
            Workspace(
                id=workspace_id,
                key=workspace_id,
                name=workspace_id,
                description="",
                active=True,
            )
            for workspace_id in ("ws-1", "ws-2")
        ]
    )
    session.add(
        RetrievalPartition(
            id="11111111-1111-1111-1111-111111111111",
            source_namespace="docs",
            managed_workspace_id="ws-1",
            candidate_scope_kind="workspace",
            candidate_workspace_id="ws-1",
            state="active",
            metadata_version=1,
            is_default_ingest=True,
        )
    )
    session.commit()
    return session


def _record_doc_event(
    session: Session,
    *,
    resource_id: str,
    desired_state: str = "active",
    content_checksum: str | None = None,
) -> ProjectionEventRef:
    return record_projection_event(
        session,
        resource_type="doc",
        resource_id=resource_id,
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
        change_kind="delete" if desired_state == "deleted" else "content",
        desired_state=desired_state,
        content_checksum=content_checksum,
        diagnostic_workspace_id="ws-1",
    )


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

    monkeypatch.setattr(rag_outbox, "get_celery_client", lambda: _FakeCeleryClient())


@pytest.fixture(autouse=True)
def _registered_rag_outbox_adapters():
    reset_rag_source_adapters()
    register_rag_resource_adapter(
        RagResourceAdapter(
            resource_type="doc",
            app_id="tests",
            load_projection=lambda db, resource_id, rag_service: None,
        )
    )
    for scope_type in ("workspace_membership", "meeting", "pms_meeting"):
        register_rag_visibility_scope_adapter(
            RagVisibilityScopeAdapter(
                scope_type=scope_type,
                resource_type="doc",
                resource_ids=lambda db, job: [],
            )
        )
    try:
        yield
    finally:
        reset_rag_source_adapters()


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


def test_enqueue_rag_sync_job_supports_company_scope_without_workspace() -> None:
    session = _session()
    try:
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                scope_kind=RagScopeKind.COMPANY,
                workspace_id="ignored-workspace",
                resource_type="doc",
                resource_id="company-doc-1",
                operation=RagSyncOperation.UPSERT,
            )

        stored = session.scalar(select(RagSyncJob).where(RagSyncJob.id == job.id))
        assert stored is not None
        assert stored.scope_kind == "company"
        assert stored.workspace_id is None
        assert stored.resource_id == "company-doc-1"
    finally:
        session.close()


def test_enqueue_rag_sync_job_requires_workspace_for_workspace_scope() -> None:
    session = _session()
    try:
        with pytest.raises(ValueError, match="requires workspace_id"):
            enqueue_rag_sync_job(
                session,
                workspace_id=None,
                resource_type="doc",
                resource_id="doc-without-workspace",
                operation=RagSyncOperation.UPSERT,
            )
    finally:
        session.close()


def test_enqueue_rag_sync_job_accepts_extension_resource_keys() -> None:
    session = _session()
    resource_id = "external-system:project-alpha:record-" + ("x" * 64)
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_external_record",
                app_id="plugin",
                load_projection=lambda db, resource_id, rag_service: None,
            )
        )
        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="plugin_external_record",
                resource_id=resource_id,
                operation=RagSyncOperation.UPSERT,
            )

        stored = session.scalar(select(RagSyncJob).where(RagSyncJob.id == job.id))
        assert stored is not None
        assert stored.resource_type == "plugin_external_record"
        assert stored.resource_id == resource_id
    finally:
        session.close()


def test_enqueue_rag_sync_job_rejects_unregistered_resource_type() -> None:
    session = _session()
    try:
        with pytest.raises(
            ValueError,
            match="RAG resource_type is not registered: missing_resource",
        ):
            enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="missing_resource",
                resource_id="resource-1",
            )
    finally:
        session.close()


def test_enqueue_rag_sync_job_rejects_upsert_without_projection_loader() -> None:
    session = _session()
    try:
        register_rag_resource_adapter(
            RagResourceAdapter(resource_type="delete_only_resource", app_id="plugin")
        )

        with pytest.raises(
            ValueError,
            match=("RAG resource_type does not support projection sync: delete_only_resource"),
        ):
            enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="delete_only_resource",
                resource_id="resource-1",
                operation=RagSyncOperation.UPSERT,
            )

        with session.begin():
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="delete_only_resource",
                resource_id="resource-1",
                operation=RagSyncOperation.DELETE,
            )

        assert job.operation == RagSyncOperation.DELETE.value
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
                trace_context={
                    "traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"
                },
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


def test_enqueue_rag_visibility_recompute_job_rejects_unregistered_scope_type() -> None:
    session = _session()
    try:
        with pytest.raises(
            ValueError,
            match="RAG visibility scope_type is not registered: missing_scope",
        ):
            enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="missing_scope",
                scope_id="scope-1",
            )
    finally:
        session.close()


def test_enqueue_rag_sync_job_captures_current_trace_context() -> None:
    bootstrap_telemetry(service_name="open-alm-api-test")
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
    bootstrap_telemetry(service_name="open-alm-api-test")

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


def test_enqueue_rag_sync_job_snapshots_projection_event_and_merges_canonically() -> None:
    session = _versioned_session()
    try:
        with session.begin():
            version_one = _record_doc_event(
                session,
                resource_id="versioned-doc",
                content_checksum="content-v1",
            )
            first = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="versioned-doc",
                content_checksum="content-v1",
                projection_event=version_one,
            )
            version_two = _record_doc_event(
                session,
                resource_id="versioned-doc",
                desired_state="deleted",
            )
            latest = enqueue_rag_sync_job(
                session,
                workspace_id="ws-2",
                resource_type="doc",
                resource_id="versioned-doc",
                operation=RagSyncOperation.DELETE,
                projection_event=version_two,
            )
            ignored = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="versioned-doc",
                content_checksum="content-v1",
                projection_event=version_one,
            )

        rows = session.scalars(
            select(RagSyncJob).where(RagSyncJob.resource_id == "versioned-doc")
        ).all()
        assert len(rows) == 1
        assert first.id == latest.id == ignored.id
        assert latest.workspace_id == "ws-2"
        assert latest.projection_event_sequence == version_two.event_sequence
        assert latest.projection_version == 2
        assert latest.retrieval_partition_id == version_two.retrieval_partition_id
        assert latest.desired_state == "deleted"
        assert latest.operation == RagSyncOperation.DELETE.value
        assert latest.content_checksum is None
    finally:
        session.close()


def test_enqueue_rag_sync_job_rejects_forged_projection_event() -> None:
    session = _versioned_session()
    try:
        with session.begin():
            event = _record_doc_event(
                session,
                resource_id="forged-doc",
                content_checksum="content-v1",
            )
            with pytest.raises(ValueError, match="persisted event"):
                enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="forged-doc",
                    projection_event=replace(event, content_checksum="forged"),
                )
    finally:
        session.close()


def test_enqueue_rag_sync_job_rejects_same_version_pending_mismatch() -> None:
    session = _versioned_session()
    try:
        with session.begin():
            event = _record_doc_event(
                session,
                resource_id="mismatched-pending-doc",
                content_checksum="content-v1",
            )
            job = enqueue_rag_sync_job(
                session,
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="mismatched-pending-doc",
                content_checksum="content-v1",
                projection_event=event,
            )
            job.content_checksum = "corrupted"
            session.flush()
            with pytest.raises(ValueError, match="same-version projection mismatch"):
                enqueue_rag_sync_job(
                    session,
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="mismatched-pending-doc",
                    content_checksum="content-v1",
                    projection_event=event,
                )
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

    monkeypatch.setattr(rag_outbox, "get_celery_client", lambda: _FakeCeleryClient())

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

    monkeypatch.setattr(rag_outbox, "get_celery_client", lambda: _FakeCeleryClient())

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


def test_enqueue_rag_visibility_recompute_job_merges_task_ids() -> None:
    session = _session()
    try:
        with session.begin():
            first = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="pms_meeting",
                scope_id="meeting-1",
                cursor={"task_ids": ["issue-1", "issue-2"], "operation": "visibility_update"},
            )
            second = enqueue_rag_visibility_recompute_job(
                session,
                workspace_id="ws-1",
                scope_type="pms_meeting",
                scope_id="meeting-1",
                cursor={"task_ids": ["issue-2", "issue-3"], "operation": "visibility_update"},
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
            "task_ids": ["issue-1", "issue-2", "issue-3"],
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
