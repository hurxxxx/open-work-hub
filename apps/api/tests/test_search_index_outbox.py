from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import Base
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.search import indexing as search_indexing
from aidoo_api.domains.search import outbox as search_outbox
from aidoo_api.domains.search.indexing import process_search_index_job
from aidoo_api.domains.search.models import SearchIndexJob
from aidoo_api.domains.search.outbox import enqueue_search_index_job


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
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

    monkeypatch.setattr(search_outbox, "_get_celery_client", lambda: _FakeCeleryClient())


def test_enqueue_search_index_job_persists_resource_job(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-1",
                operation="upsert",
                trace_context={"traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"},
            )

        stored = session.scalar(select(SearchIndexJob).where(SearchIndexJob.id == job.id))
        assert stored is not None
        assert stored.workspace_id == "ws-1"
        assert stored.entity_type == "doc"
        assert stored.entity_id == "doc-1"
        assert stored.operation == "upsert"
        assert stored.status == "pending"
        assert stored.trace_context == {"traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"}
        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()


def test_enqueue_search_index_job_dedupes_pending_rows_and_latest_operation_wins(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            first = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-2",
                operation="delete",
            )
            second = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-2",
                operation="upsert",
            )

        rows = session.scalars(select(SearchIndexJob).where(SearchIndexJob.entity_id == "doc-2")).all()
        assert len(rows) == 1
        assert second.id == first.id
        assert rows[0].operation == "upsert"
        assert published == [("search.index_resource", [first.id], "search_index_realtime")]
    finally:
        session.close()


def test_enqueue_search_index_job_does_not_publish_on_rollback(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        try:
            with session.begin():
                enqueue_search_index_job(
                    session,
                    workspace_id="ws-1",
                    entity_type="meeting",
                    entity_id="meeting-1",
                    operation="upsert",
                )
                raise RuntimeError("rollback")
        except RuntimeError:
            pass

        assert published == []
    finally:
        session.close()


def test_enqueue_search_index_job_ignores_nested_commit_before_outer_commit(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-nested-commit",
                operation="upsert",
            )
            with session.begin_nested():
                pass
            assert published == []

        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()


def test_enqueue_search_index_job_keeps_publish_after_nested_rollback(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _session()
    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-nested-rollback",
                operation="upsert",
            )
            try:
                with session.begin_nested():
                    raise RuntimeError("rollback savepoint")
            except RuntimeError:
                pass
            assert published == []

        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()


def test_process_search_index_job_upserts_loaded_projection(monkeypatch) -> None:
    session = _session()
    calls: list[tuple[str, object]] = []
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            calls.append(("upsert", document))

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            calls.append(("delete", (workspace_id, entity_type, entity_id)))

    monkeypatch.setattr(
        search_indexing,
        "load_search_document",
        lambda db, entity_type, entity_id: {
            "workspace_id": "ws-1",
            "entity_type": str(entity_type),
            "entity_id": entity_id,
            "title": "Doc",
        },
    )

    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-3",
                operation="upsert",
                trace_context={},
            )

        result = process_search_index_job(session, job.id, client=_FakeClient())
        stored = session.get(SearchIndexJob, job.id)
        assert result == "upserted"
        assert stored is not None
        assert stored.status == "succeeded"
        assert calls == [
            (
                "upsert",
                {
                    "workspace_id": "ws-1",
                    "entity_type": "doc",
                    "entity_id": "doc-3",
                    "title": "Doc",
                },
            )
        ]
    finally:
        session.close()


def test_process_search_index_job_deletes_when_projection_missing(monkeypatch) -> None:
    session = _session()
    calls: list[tuple[str, object]] = []
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            calls.append(("upsert", document))

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            calls.append(("delete", (workspace_id, entity_type, entity_id)))

    monkeypatch.setattr(search_indexing, "load_search_document", lambda db, entity_type, entity_id: None)

    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="planner_event",
                entity_id="event-1",
                operation="delete",
                trace_context={},
            )

        result = process_search_index_job(session, job.id, client=_FakeClient())
        stored = session.get(SearchIndexJob, job.id)
        assert result == "deleted_missing_projection"
        assert stored is not None
        assert stored.status == "succeeded"
        assert calls == [("delete", ("ws-1", "planner_event", "event-1"))]
    finally:
        session.close()
