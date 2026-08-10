from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.docs import search_hooks as docs_search_hooks
from ai_do_api.domains.meeting import search_hooks as meeting_search_hooks
from ai_do_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from ai_do_api.domains.retrieval.projection_fencing import (
    ProjectionEventRef,
    record_projection_event,
)
from ai_do_api.domains.search import indexing as search_indexing
from ai_do_api.domains.search import outbox as search_outbox
from ai_do_api.domains.search.indexing import process_search_index_job
from ai_do_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    register_search_entity_adapter,
    reset_search_entity_adapters,
)
from ai_do_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP
from ai_do_api.domains.search.entity_registry import reset_search_entity_descriptors
from ai_do_api.domains.search.models import SearchIndexJob
from ai_do_api.domains.search.outbox import enqueue_search_index_job
from ai_do_api.domains.search.projection_registry import reset_search_projection_adapters


_PROJECTION_PARTITION_ID = "722c2043-fc6f-4446-9811-dc35c263d445"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
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


def _projection_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RetrievalPartition.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            SearchIndexJob.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    session.add_all(
        [
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            ),
            Workspace(
                id="ws-2",
                key="ws-2",
                name="Workspace 2",
                description="",
                active=True,
            ),
            RetrievalPartition(
                id=_PROJECTION_PARTITION_ID,
                source_namespace="search-fence-test",
                candidate_scope_kind="company",
                is_default_ingest=False,
            ),
        ]
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

    monkeypatch.setattr(search_outbox, "get_celery_client", lambda: _FakeCeleryClient())


def _reset_search_registries() -> None:
    reset_search_entity_adapters()
    reset_search_entity_descriptors()
    reset_search_projection_adapters()


def _search_acl_fields() -> dict[str, object]:
    return {
        "owner_user_id": None,
        "visibility": None,
        "team_ids": [],
        "participant_user_ids": [],
        "shared_user_ids": [],
        "granted_user_ids": [],
        "target_keys": [],
    }


def _register_extension_search_entity(entity_type: str = "plugin_external_record") -> None:
    register_search_entity_adapter(
        SearchEntityAdapter(
            owner_app=DOCS_WORKSPACE_APP,
            entity_type=entity_type,
            resource_type="plugin_external_record",
            label="Plugin External Record",
            label_key="ai.search.entityPluginExternalRecord",
            workspace_loader=lambda db, *, workspace: [],
            document_loader=lambda db, *, entity_type, entity_id: {
                "workspace_id": "ws-1",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "title": "Plugin External Record",
            },
        )
    )


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
                trace_context={
                    "traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"
                },
            )

        stored = session.scalar(select(SearchIndexJob).where(SearchIndexJob.id == job.id))
        assert stored is not None
        assert stored.workspace_id == "ws-1"
        assert stored.entity_type == "doc"
        assert stored.entity_id == "doc-1"
        assert stored.operation == "upsert"
        assert stored.resource_type is None
        assert stored.projection_event_sequence is None
        assert stored.projection_version is None
        assert stored.desired_state is None
        assert stored.status == "pending"
        assert stored.trace_context == {
            "traceparent": "00-feedfacefeedfacefeedfacefeedface-beadbeadbeadbead-01"
        }
        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()


def test_versioned_enqueue_cross_workspace_higher_version_wins_over_late_delete(
    monkeypatch,
) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            departed = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-versioned",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="delete",
                desired_state="deleted",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned",
                operation="delete",
                projection_event=departed,
            )
            moved = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-versioned",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-2",
            )
            merged = enqueue_search_index_job(
                session,
                workspace_id="ws-2",
                entity_type="doc",
                entity_id="doc-versioned",
                operation="upsert",
                projection_event=moved,
            )
            ignored = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned",
                operation="delete",
                projection_event=departed,
            )

        assert merged.id == job.id == ignored.id
        stored = session.get(SearchIndexJob, job.id)
        assert stored is not None
        assert stored.workspace_id == "ws-2"
        assert stored.resource_type == "docs_native_doc"
        assert stored.projection_event_sequence == moved.event_sequence
        assert stored.projection_version == 2
        assert stored.retrieval_partition_id == _PROJECTION_PARTITION_ID
        assert stored.desired_state == "active"
        assert stored.operation == "upsert"
        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()


def test_versioned_enqueue_is_idempotent_and_same_version_mismatch_fails(
    monkeypatch,
) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-idempotent",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            first = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-idempotent",
                projection_event=projection_event,
            )
            second = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-idempotent",
                projection_event=projection_event,
            )
        assert first.id == second.id

        with session.begin():
            stored = session.get(SearchIndexJob, first.id)
            assert stored is not None
            stored.operation = "delete"
            session.add(stored)

        with session.begin(), pytest.raises(ValueError, match="same-version"):
            enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-idempotent",
                operation="upsert",
                projection_event=projection_event,
            )
    finally:
        session.close()


def test_versioned_enqueue_validates_adapter_and_event_snapshot(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="meeting",
                resource_id="meeting-mismatch",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            with pytest.raises(ValueError, match="resource_type"):
                enqueue_search_index_job(
                    session,
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="meeting-mismatch",
                    projection_event=projection_event,
                )
            with pytest.raises(ValueError, match="resource_id"):
                enqueue_search_index_job(
                    session,
                    workspace_id="ws-1",
                    entity_type="meeting",
                    entity_id="other-meeting",
                    projection_event=projection_event,
                )
            with pytest.raises(ValueError, match="event snapshot"):
                enqueue_search_index_job(
                    session,
                    workspace_id="ws-1",
                    entity_type="meeting",
                    entity_id="meeting-mismatch",
                    projection_event=replace(
                        projection_event,
                        retrieval_partition_id="cf0ac696-f0e0-45a0-9c9c-2d5eb02384e8",
                    ),
                )
            with pytest.raises(ValueError, match="desired_state"):
                enqueue_search_index_job(
                    session,
                    workspace_id="ws-1",
                    entity_type="meeting",
                    entity_id="meeting-mismatch",
                    operation="delete",
                    projection_event=projection_event,
                )
        assert published == []
    finally:
        session.close()


def test_legacy_enqueue_cannot_overwrite_versioned_pending_snapshot(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-versioned-legacy",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            versioned = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned-legacy",
                operation="upsert",
                projection_event=projection_event,
            )
            legacy = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned-legacy",
                operation="delete",
            )

        assert versioned.id == legacy.id
        stored = session.get(SearchIndexJob, versioned.id)
        assert stored is not None
        assert stored.projection_version == 1
        assert stored.operation == "upsert"
    finally:
        session.close()


def test_versioned_enqueue_upgrades_same_target_legacy_pending_job(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            legacy = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-legacy-upgrade",
            )
            projection_event = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-legacy-upgrade",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            upgraded = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-legacy-upgrade",
                projection_event=projection_event,
            )

        assert upgraded.id == legacy.id
        assert upgraded.resource_type == "docs_native_doc"
        assert upgraded.projection_event_sequence == projection_event.event_sequence
        assert upgraded.projection_version == 1
    finally:
        session.close()


def test_pending_versioned_resource_identity_is_unique_across_workspaces() -> None:
    session = _projection_session()
    try:
        with pytest.raises(IntegrityError):
            with session.begin():
                projection_event = record_projection_event(
                    session,
                    resource_type="docs_native_doc",
                    resource_id="doc-canonical-unique",
                    retrieval_partition_id=_PROJECTION_PARTITION_ID,
                    change_kind="content",
                    desired_state="active",
                    diagnostic_workspace_id="ws-1",
                )
                session.add_all(
                    [
                        SearchIndexJob(
                            id="canonical-job-a",
                            workspace_id="ws-1",
                            retrieval_partition_id=_PROJECTION_PARTITION_ID,
                            resource_type="docs_native_doc",
                            projection_event_sequence=projection_event.event_sequence,
                            projection_version=projection_event.projection_version,
                            desired_state="active",
                            entity_type="doc",
                            entity_id="doc-canonical-unique",
                            operation="upsert",
                            trace_context={},
                            status="pending",
                            attempts=0,
                        ),
                        SearchIndexJob(
                            id="canonical-job-b",
                            workspace_id="ws-2",
                            retrieval_partition_id=_PROJECTION_PARTITION_ID,
                            resource_type="docs_native_doc",
                            projection_event_sequence=projection_event.event_sequence,
                            projection_version=projection_event.projection_version,
                            desired_state="active",
                            entity_type="doc",
                            entity_id="doc-canonical-unique",
                            operation="upsert",
                            trace_context={},
                            status="pending",
                            attempts=0,
                        ),
                    ]
                )
                session.flush()
    finally:
        session.close()


def test_docs_hook_forwards_optional_projection_event(monkeypatch) -> None:
    projection_event = ProjectionEventRef(
        event_sequence=42,
        resource_type="docs_native_doc",
        resource_id="doc-hook",
        projection_version=3,
        retrieval_partition_id=_PROJECTION_PARTITION_ID,
        change_kind="content",
        desired_state="active",
        content_checksum=None,
        visibility_checksum=None,
        diagnostic_workspace_id="ws-1",
    )
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        docs_search_hooks,
        "enqueue_search_index_job",
        lambda db, **kwargs: captured.append(kwargs),
    )

    docs_search_hooks.enqueue_doc_search_index(
        object(),
        doc=SimpleNamespace(id="doc-hook", workspace_id="ws-1"),
        projection_event=projection_event,
    )

    assert captured == [
        {
            "workspace_id": "ws-1",
            "entity_type": docs_search_hooks.SearchEntityType.DOC,
            "entity_id": "doc-hook",
            "operation": "upsert",
            "projection_event": projection_event,
        }
    ]


def test_meeting_search_only_hook_records_event_from_source_binding(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    session = _projection_session()
    try:
        with session.begin():
            meeting_search_hooks.enqueue_meeting_search_index(
                session,
                meeting=SimpleNamespace(
                    id="meeting-hook",
                    workspace_id="ws-1",
                    retrieval_partition_id=_PROJECTION_PARTITION_ID,
                ),
            )

        job = session.scalar(
            select(SearchIndexJob).where(SearchIndexJob.entity_id == "meeting-hook")
        )
        event = session.scalar(
            select(RetrievalProjectionEvent).where(
                RetrievalProjectionEvent.resource_id == "meeting-hook"
            )
        )
        assert job is not None
        assert event is not None
        assert job.resource_type == "meeting"
        assert job.projection_event_sequence == event.event_sequence
        assert job.projection_version == event.projection_version == 1
    finally:
        session.close()


def test_enqueue_search_index_job_accepts_extension_resource_keys(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    _reset_search_registries()
    _register_extension_search_entity()
    session = _session()
    entity_id = "external-system:project-alpha:record-" + ("x" * 64)
    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="plugin_external_record",
                entity_id=entity_id,
                operation="upsert",
            )

        stored = session.scalar(select(SearchIndexJob).where(SearchIndexJob.id == job.id))
        assert stored is not None
        assert stored.entity_type == "plugin_external_record"
        assert stored.entity_id == entity_id
        assert published == [("search.index_resource", [job.id], "search_index_realtime")]
    finally:
        session.close()
        _reset_search_registries()


def test_enqueue_search_index_job_rejects_unregistered_upsert_entity_type(monkeypatch) -> None:
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)
    _reset_search_registries()
    session = _session()
    try:
        with pytest.raises(ValueError, match="lacks projection adapter"):
            enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="plugin_typo",
                entity_id="record-1",
                operation="upsert",
            )
        assert published == []
    finally:
        session.close()
        _reset_search_registries()


def test_enqueue_search_index_job_dedupes_pending_rows_and_latest_operation_wins(
    monkeypatch,
) -> None:
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

        rows = session.scalars(
            select(SearchIndexJob).where(SearchIndexJob.entity_id == "doc-2")
        ).all()
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
            **_search_acl_fields(),
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
                    **_search_acl_fields(),
                },
            )
        ]
    finally:
        session.close()


def test_versioned_search_job_stale_head_skips_backend_mutation(monkeypatch) -> None:
    session = _projection_session()
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            del document
            raise AssertionError("stale versioned job must not upsert")

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            del workspace_id, entity_type, entity_id
            raise AssertionError("stale versioned job must not delete")

    try:
        with session.begin():
            first = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-stale-head",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="delete",
                desired_state="deleted",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-stale-head",
                operation="delete",
                projection_event=first,
            )
            record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-stale-head",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-2",
            )

        result = process_search_index_job(session, job.id, client=_FakeClient())
        stored = session.get(SearchIndexJob, job.id)
        assert result == "superseded"
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.last_error == "superseded_by_projection_head:before_mutation"
    finally:
        session.close()


def test_versioned_non_files_search_job_keeps_legacy_upsert(
    monkeypatch,
) -> None:
    session = _projection_session()
    captured: list[dict] = []

    class _LegacyClientWithPartitionedMethods:
        def upsert_document(self, document: dict) -> None:
            captured.append(document)

        def upsert_partitioned_document(self, document: dict) -> str:
            del document
            raise AssertionError("non-Files jobs must not use the Files v3 mutation")

        def delete_document(self, **kwargs) -> None:
            del kwargs
            raise AssertionError("upsert jobs must not delete")

    monkeypatch.setattr(search_indexing, "_ensure_search_projection_adapter", lambda value: None)
    monkeypatch.setattr(
        search_indexing,
        "load_search_document",
        lambda db, entity_type, entity_id: {
            "workspace_id": "ws-1",
            "entity_type": str(entity_type),
            "entity_id": entity_id,
            "title": "Legacy projection with a database fence",
            **_search_acl_fields(),
        },
    )
    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-versioned-legacy-upsert",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned-legacy-upsert",
                operation="upsert",
                projection_event=projection_event,
            )

        result = process_search_index_job(
            session,
            job.id,
            client=_LegacyClientWithPartitionedMethods(),
        )

        assert result == "upserted"
        assert captured == [
            {
                "workspace_id": "ws-1",
                "entity_type": "doc",
                "entity_id": "doc-versioned-legacy-upsert",
                "title": "Legacy projection with a database fence",
                **_search_acl_fields(),
            }
        ]
    finally:
        session.close()


def test_versioned_non_files_search_job_keeps_legacy_delete() -> None:
    session = _projection_session()
    captured: list[tuple[str, str, str]] = []

    class _LegacyClientWithPartitionedMethods:
        def delete_document(
            self,
            *,
            workspace_id: str,
            entity_type: str,
            entity_id: str,
        ) -> None:
            captured.append((workspace_id, entity_type, entity_id))

        def delete_partitioned_document(self, **kwargs) -> str:
            del kwargs
            raise AssertionError("non-Files jobs must not use the Files v3 mutation")

    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="docs_native_doc",
                resource_id="doc-versioned-legacy-delete",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="delete",
                desired_state="deleted",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-versioned-legacy-delete",
                operation="delete",
                projection_event=projection_event,
            )

        result = process_search_index_job(
            session,
            job.id,
            client=_LegacyClientWithPartitionedMethods(),
        )

        assert result == "deleted"
        assert captured == [("ws-1", "doc", "doc-versioned-legacy-delete")]
    finally:
        session.close()


def test_versioned_files_search_job_uses_partitioned_external_version_upsert(
    monkeypatch,
) -> None:
    session = _projection_session()
    captured: list[dict] = []

    class _PartitionedClient:
        def upsert_partitioned_document(self, document: dict) -> str:
            captured.append(document)
            return "upserted"

        def upsert_document(self, document: dict) -> None:
            del document
            raise AssertionError("versioned jobs must not use the legacy upsert")

        def delete_document(self, **kwargs) -> None:
            del kwargs
            raise AssertionError("versioned jobs must not use the legacy delete")

    monkeypatch.setattr(search_indexing, "_ensure_search_projection_adapter", lambda value: None)
    monkeypatch.setattr(
        search_indexing,
        "load_search_document",
        lambda db, entity_type, entity_id: {
            "workspace_id": "ws-1",
            "entity_type": str(entity_type),
            "entity_id": entity_id,
            "title": "Partitioned projection",
            **_search_acl_fields(),
        },
    )
    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="file_manager_file",
                resource_id="file-versioned-upsert",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="file",
                entity_id="file-versioned-upsert",
                operation="upsert",
                projection_event=projection_event,
            )

        result = process_search_index_job(session, job.id, client=_PartitionedClient())

        assert result == "upserted"
        assert captured == [
            {
                "workspace_id": "ws-1",
                "entity_type": "file",
                "entity_id": "file-versioned-upsert",
                "title": "Partitioned projection",
                **_search_acl_fields(),
                "resource_type": "file_manager_file",
                "retrieval_partition_id": _PROJECTION_PARTITION_ID,
                "projection_version": 1,
            }
        ]
    finally:
        session.close()


def test_versioned_files_search_job_uses_partitioned_external_version_delete() -> None:
    session = _projection_session()
    captured: list[tuple[str, str, int]] = []

    class _PartitionedClient:
        def delete_partitioned_document(
            self,
            *,
            resource_type: str,
            resource_id: str,
            projection_version: int,
        ) -> str:
            captured.append((resource_type, resource_id, projection_version))
            return "deleted"

        def delete_document(self, **kwargs) -> None:
            del kwargs
            raise AssertionError("versioned jobs must not use the legacy delete")

    try:
        with session.begin():
            projection_event = record_projection_event(
                session,
                resource_type="file_manager_file",
                resource_id="file-versioned-delete",
                retrieval_partition_id=_PROJECTION_PARTITION_ID,
                change_kind="delete",
                desired_state="deleted",
                diagnostic_workspace_id="ws-1",
            )
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="file",
                entity_id="file-versioned-delete",
                operation="delete",
                projection_event=projection_event,
            )

        result = process_search_index_job(session, job.id, client=_PartitionedClient())

        assert result == "deleted"
        assert captured == [("file_manager_file", "file-versioned-delete", 1)]
    finally:
        session.close()


@pytest.mark.parametrize(
    ("entity_type", "resource_type"),
    [
        ("file", "docs_native_doc"),
        ("doc", "file_manager_file"),
    ],
)
def test_partitioned_keyword_generation_rejects_mismatched_files_identity(
    entity_type: str,
    resource_type: str,
) -> None:
    job = SimpleNamespace(entity_type=entity_type, resource_type=resource_type)

    with pytest.raises(
        search_indexing.KeywordSearchBackendError,
        match="entity and resource identities do not match",
    ):
        search_indexing._uses_partitioned_keyword_generation(job)


def test_process_search_index_job_rejects_mismatched_projection_identity(monkeypatch) -> None:
    session = _session()
    published: list[tuple[str, list[str], str]] = []
    _stub_celery(monkeypatch, published)

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            del document
            raise AssertionError("upsert should not run")

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            del workspace_id, entity_type, entity_id
            raise AssertionError("delete should not run")

    monkeypatch.setattr(
        search_indexing,
        "load_search_document",
        lambda db, entity_type, entity_id: {
            "workspace_id": "ws-other",
            "entity_type": str(entity_type),
            "entity_id": entity_id,
            "title": "Wrong workspace",
        },
    )

    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-mismatch",
                operation="upsert",
                trace_context={},
            )

        with pytest.raises(search_indexing.SearchProjectionIdentityError):
            process_search_index_job(session, job.id, client=_FakeClient())

        stored = session.get(SearchIndexJob, job.id)
        assert stored is not None
        assert stored.status == "processing"
        assert stored.attempts == 1
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

    monkeypatch.setattr(
        search_indexing, "load_search_document", lambda db, entity_type, entity_id: None
    )

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
        assert result == "deleted"
        assert stored is not None
        assert stored.status == "succeeded"
        assert calls == [("delete", ("ws-1", "planner_event", "event-1"))]
    finally:
        session.close()


def test_process_search_index_job_respects_delete_operation_when_projection_exists(
    monkeypatch,
) -> None:
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
            "title": "Still Present",
        },
    )

    try:
        with session.begin():
            job = enqueue_search_index_job(
                session,
                workspace_id="ws-1",
                entity_type="doc",
                entity_id="doc-delete",
                operation="delete",
                trace_context={},
            )

        result = process_search_index_job(session, job.id, client=_FakeClient())
        stored = session.get(SearchIndexJob, job.id)
        assert result == "deleted"
        assert stored is not None
        assert stored.status == "succeeded"
        assert calls == [("delete", ("ws-1", "doc", "doc-delete"))]
    finally:
        session.close()


def test_process_search_index_job_fails_unregistered_upsert_entity_type() -> None:
    session = _session()
    _reset_search_registries()

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            del document
            raise AssertionError("upsert should not run")

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            del workspace_id, entity_type, entity_id
            raise AssertionError("delete should not run")

    try:
        with session.begin():
            job = SearchIndexJob(
                id="job-unknown-upsert",
                workspace_id="ws-1",
                entity_type="plugin_typo",
                entity_id="record-1",
                operation="upsert",
                trace_context={},
                status="pending",
                attempts=0,
            )
            session.add(job)

        with pytest.raises(search_indexing.UnsupportedSearchEntityError):
            process_search_index_job(session, job.id, client=_FakeClient())

        stored = session.get(SearchIndexJob, job.id)
        assert stored is not None
        assert stored.status == "processing"
        assert stored.attempts == 1
    finally:
        session.close()
        _reset_search_registries()


def test_process_search_index_job_ignores_fresh_processing_delivery() -> None:
    session = _session()
    calls: list[str] = []

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            del document
            calls.append("upsert")

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            del workspace_id, entity_type, entity_id
            calls.append("delete")

    try:
        with session.begin():
            session.add(
                SearchIndexJob(
                    id="job-processing-fresh",
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="doc-processing-fresh",
                    operation="delete",
                    trace_context={},
                    status="processing",
                    attempts=1,
                    updated_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )

        result = process_search_index_job(
            session,
            "job-processing-fresh",
            client=_FakeClient(),
        )

        stored = session.get(SearchIndexJob, "job-processing-fresh")
        assert result == "ignored"
        assert stored is not None
        assert stored.status == "processing"
        assert stored.attempts == 1
        assert calls == []
    finally:
        session.close()


def test_process_search_index_job_reclaims_stale_processing_delivery() -> None:
    session = _session()
    calls: list[tuple[str, object]] = []

    class _FakeClient:
        def upsert_document(self, document: dict) -> None:
            calls.append(("upsert", document))

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            calls.append(("delete", (workspace_id, entity_type, entity_id)))

    try:
        with session.begin():
            session.add(
                SearchIndexJob(
                    id="job-processing-stale",
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="doc-processing-stale",
                    operation="delete",
                    trace_context={},
                    status="processing",
                    attempts=1,
                    updated_at=(datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)),
                )
            )

        result = process_search_index_job(
            session,
            "job-processing-stale",
            client=_FakeClient(),
        )

        stored = session.get(SearchIndexJob, "job-processing-stale")
        assert result == "deleted"
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempts == 2
        assert calls == [("delete", ("ws-1", "doc", "doc-processing-stale"))]
    finally:
        session.close()
