from __future__ import annotations

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import Base
from aidoo_api.core.telemetry import (
    bootstrap_telemetry,
    current_trace_id,
    get_tracer_provider,
    start_as_current_span,
)
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.rag.contracts import RagSyncLane, RagSyncOperation, RagTraceContext
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from aidoo_api.domains.rag.outbox import (
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
    bootstrap_telemetry(service_name="aidoo-api-test")
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
    bootstrap_telemetry(service_name="aidoo-api-test")

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
