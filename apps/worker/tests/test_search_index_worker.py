# ruff: noqa: E402

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_alm_api.core.db import Base  # noqa: E402
from open_alm_api.domains.auth.models import Workspace  # noqa: E402
from open_alm_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP  # noqa: E402
from open_alm_api.domains.search.entity_adapter_registry import (  # noqa: E402
    SearchEntityAdapter,
    register_search_entity_adapter,
    reset_search_entity_adapters,
)
from open_alm_api.domains.search.entity_registry import reset_search_entity_descriptors  # noqa: E402
from open_alm_api.domains.search.models import SearchIndexJob  # noqa: E402
from open_alm_api.domains.retrieval.models import (  # noqa: E402
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_alm_api.domains.retrieval.projection_fencing import (  # noqa: E402
    record_projection_event,
)


_PROJECTION_PARTITION_ID = "e1ada2fd-9ba0-4426-bd09-61e1a6c18e80"
from open_alm_api.domains.search.projection_registry import (  # noqa: E402
    reset_search_projection_adapters,
)


def _worker_dsn(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _reload_worker_module(module_name: str):
    for cached_name in list(sys.modules):
        if cached_name == "open_alm_worker" or cached_name.startswith("open_alm_worker."):
            sys.modules.pop(cached_name, None)
    return importlib.import_module(module_name)


def _reset_search_registries() -> None:
    reset_search_entity_adapters()
    reset_search_entity_descriptors()
    reset_search_projection_adapters()


def _seed_llm_routing_control_plane(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE ai_model_provider_configs (
                provider_id TEXT PRIMARY KEY
            )
            """
        )
        connection.execute("CREATE TABLE ai_model_catalog_entries (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE ai_model_route_overrides (workload_id TEXT PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE image_model_provider_configs (provider_id TEXT PRIMARY KEY)"
        )
        connection.execute("CREATE TABLE image_model_profiles (profile_id TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO ai_model_provider_configs (provider_id) VALUES (?)",
            [(provider_id,) for provider_id in ("anthropic", "gemini", "local", "openai")],
        )
        connection.commit()
    finally:
        connection.close()


def test_search_worker_routes_files_only_to_the_active_partitioned_index(
    monkeypatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    settings = SimpleNamespace(files_retrieval_enabled=True)
    pair = SimpleNamespace(opensearch_physical_name="files-v3-release")
    expected_client = object()
    calls: list[tuple[object, object]] = []
    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda db, *, settings: calls.append((db, settings)) or pair,
    )
    monkeypatch.setattr(
        tasks_module,
        "build_partitioned_keyword_search_client",
        lambda resolved_settings, *, physical_index_name: (
            expected_client
            if (
                resolved_settings is settings
                and physical_index_name == pair.opensearch_physical_name
            )
            else None
        ),
    )
    monkeypatch.setattr(
        tasks_module,
        "_search_client",
        lambda: (_ for _ in ()).throw(
            AssertionError("Files must not use the legacy keyword index")
        ),
    )
    db = object()

    client = tasks_module._search_client_for_job(
        db,
        SimpleNamespace(
            entity_type="file",
            resource_type="file_manager_file",
            retrieval_partition_id="partition-1",
            projection_event_sequence=1,
            projection_version=1,
            desired_state="active",
        ),
    )

    assert client is expected_client
    assert calls == [(db, settings)]


def test_search_worker_keeps_non_file_jobs_on_the_legacy_index(monkeypatch) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    expected_client = object()
    monkeypatch.setattr(tasks_module, "_search_client", lambda: expected_client)
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy sources must not resolve the Files generation")
        ),
    )

    client = tasks_module._search_client_for_job(
        object(),
        SimpleNamespace(entity_type="doc"),
    )

    assert client is expected_client


def test_search_worker_fails_closed_when_files_operator_gate_is_disabled(
    monkeypatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(files_retrieval_enabled=False),
    )

    with pytest.raises(
        tasks_module.PartitionedRetrievalRuntimeUnavailable,
        match="operator_gate_disabled",
    ):
        tasks_module._search_client_for_job(
            object(),
            SimpleNamespace(entity_type="file"),
        )


def test_search_worker_pauses_files_job_without_consuming_retry_budget_when_gate_is_disabled(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-files-gate-paused.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
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
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                ),
                RetrievalPartition(
                    id=_PROJECTION_PARTITION_ID,
                    source_namespace="files",
                    managed_workspace_id="ws-1",
                    candidate_scope_kind="workspace",
                    candidate_workspace_id="ws-1",
                    is_default_ingest=False,
                ),
            ]
        )
        session.flush()
        event = record_projection_event(
            session,
            resource_type="file_manager_file",
            resource_id="file-paused",
            retrieval_partition_id=_PROJECTION_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            diagnostic_workspace_id="ws-1",
        )
        session.add(
            SearchIndexJob(
                id="job-files-gate-paused",
                workspace_id="ws-1",
                retrieval_partition_id=event.retrieval_partition_id,
                resource_type=event.resource_type,
                projection_event_sequence=event.event_sequence,
                projection_version=event.projection_version,
                desired_state=event.desired_state,
                entity_type="file",
                entity_id=event.resource_id,
                operation="upsert",
                trace_context={},
                status="pending",
                attempts=3,
            )
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    monkeypatch.setenv("OPEN_ALM_FILES_RETRIEVAL_ENABLED", "0")
    monkeypatch.setenv("OPEN_ALM_RAG_JOB_MAX_ATTEMPTS", "3")
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(
        tasks_module.index_resource,
        "retry",
        lambda **_kwargs: pytest.fail("operator pause must not schedule a Celery retry"),
    )

    result = tasks_module.index_resource.run("job-files-gate-paused")

    assert result == "operator_gate_paused"
    with Session(engine) as session:
        stored = session.get(SearchIndexJob, "job-files-gate-paused")
        assert stored is not None
        assert stored.status == "pending"
        assert stored.attempts == 3
        assert stored.next_retry_at is not None
        assert stored.last_error == "operator_gate_disabled"


def test_search_worker_rejects_unfenced_file_job_before_backend_resolution(
    monkeypatch,
) -> None:
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(
        tasks_module,
        "get_settings",
        lambda: SimpleNamespace(files_retrieval_enabled=True),
    )
    monkeypatch.setattr(
        tasks_module,
        "resolve_active_partitioned_generation_pair",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unfenced Files jobs must be rejected before backend resolution")
        ),
    )

    with pytest.raises(
        tasks_module.PartitionedRetrievalRuntimeUnavailable,
        match="unfenced_file_job",
    ):
        tasks_module._search_client_for_job(
            object(),
            SimpleNamespace(
                entity_type="file",
                resource_type=None,
                retrieval_partition_id=None,
                projection_event_sequence=None,
                projection_version=None,
                desired_state=None,
            ),
        )


def test_search_worker_fails_unsupported_entity_without_retry(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "worker-search.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    with Session(engine) as session:
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
            SearchIndexJob(
                id="job-unsupported-entity",
                workspace_id="ws-1",
                entity_type="plugin_typo",
                entity_id="record-1",
                operation="upsert",
                trace_context={},
                status="pending",
                attempts=0,
            )
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    _reset_search_registries()
    try:
        tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
        monkeypatch.setattr(
            tasks_module.index_resource,
            "retry",
            lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("unsupported search entity must not retry")
            ),
        )

        result = tasks_module.index_resource.run("job-unsupported-entity")

        assert result == "unsupported_entity_type"
        with Session(engine) as session:
            stored = session.get(SearchIndexJob, "job-unsupported-entity")
            assert stored is not None
            assert stored.status == "failed"
            assert stored.attempts == 1
            assert stored.next_retry_at is None
            assert stored.last_error is not None
            assert stored.last_error.startswith("unsupported_entity_type: ")
    finally:
        _reset_search_registries()


def test_search_worker_cancels_stale_versioned_job_before_backend_mutation(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-projection-fence.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
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
    with Session(engine) as session:
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
                    source_namespace="worker-search-fence-test",
                    candidate_scope_kind="company",
                    is_default_ingest=False,
                ),
            ]
        )
        session.flush()
        tombstone = record_projection_event(
            session,
            resource_type="docs_native_doc",
            resource_id="doc-stale-worker",
            retrieval_partition_id=_PROJECTION_PARTITION_ID,
            change_kind="delete",
            desired_state="deleted",
            diagnostic_workspace_id="ws-1",
        )
        session.add(
            SearchIndexJob(
                id="job-stale-versioned",
                workspace_id="ws-1",
                retrieval_partition_id=tombstone.retrieval_partition_id,
                resource_type=tombstone.resource_type,
                projection_event_sequence=tombstone.event_sequence,
                projection_version=tombstone.projection_version,
                desired_state=tombstone.desired_state,
                entity_type="doc",
                entity_id=tombstone.resource_id,
                operation="delete",
                trace_context={},
                status="pending",
                attempts=0,
            )
        )
        record_projection_event(
            session,
            resource_type="docs_native_doc",
            resource_id="doc-stale-worker",
            retrieval_partition_id=_PROJECTION_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            diagnostic_workspace_id="ws-2",
        )
        session.commit()

    class _FailingSearchClient:
        def upsert_document(self, document: dict) -> None:
            del document
            raise AssertionError("stale versioned job must not upsert")

        def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
            del workspace_id, entity_type, entity_id
            raise AssertionError("stale versioned job must not delete")

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(tasks_module, "_search_client", lambda: _FailingSearchClient())

    result = tasks_module.index_resource.run("job-stale-versioned")

    assert result == "superseded"
    with Session(engine) as session:
        stored = session.get(SearchIndexJob, "job-stale-versioned")
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.last_error == "superseded_by_projection_head:before_mutation"


def test_search_worker_processes_fenced_non_file_job_with_legacy_mutation(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-fenced-doc.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
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
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(
                    id="ws-1",
                    key="ws-1",
                    name="Workspace 1",
                    description="",
                    active=True,
                ),
                RetrievalPartition(
                    id=_PROJECTION_PARTITION_ID,
                    source_namespace="worker-search-fenced-doc-test",
                    candidate_scope_kind="workspace",
                    candidate_workspace_id="ws-1",
                    is_default_ingest=False,
                ),
            ]
        )
        session.flush()
        tombstone = record_projection_event(
            session,
            resource_type="docs_native_doc",
            resource_id="doc-current-worker",
            retrieval_partition_id=_PROJECTION_PARTITION_ID,
            change_kind="delete",
            desired_state="deleted",
            diagnostic_workspace_id="ws-1",
        )
        session.add(
            SearchIndexJob(
                id="job-current-fenced-doc",
                workspace_id="ws-1",
                retrieval_partition_id=tombstone.retrieval_partition_id,
                resource_type=tombstone.resource_type,
                projection_event_sequence=tombstone.event_sequence,
                projection_version=tombstone.projection_version,
                desired_state=tombstone.desired_state,
                entity_type="doc",
                entity_id=tombstone.resource_id,
                operation="delete",
                trace_context={},
                status="pending",
                attempts=0,
            )
        )
        session.commit()

    captured: list[tuple[str, str, str]] = []

    class _LegacySearchClientWithPartitionedMethods:
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
            raise AssertionError("fenced non-Files jobs must keep the legacy mutation path")

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(
        tasks_module,
        "_search_client",
        lambda: _LegacySearchClientWithPartitionedMethods(),
    )

    result = tasks_module.index_resource.run("job-current-fenced-doc")

    assert result == "deleted"
    assert captured == [("ws-1", "doc", "doc-current-worker")]
    with Session(engine) as session:
        stored = session.get(SearchIndexJob, "job-current-fenced-doc")
        assert stored is not None
        assert stored.status == "succeeded"


def test_search_worker_fails_projection_identity_mismatch_without_retry(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-identity.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    with Session(engine) as session:
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
            SearchIndexJob(
                id="job-identity-mismatch",
                workspace_id="ws-1",
                entity_type="plugin_external_record",
                entity_id="record-1",
                operation="upsert",
                trace_context={},
                status="pending",
                attempts=0,
            )
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    _reset_search_registries()
    try:
        tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_WORKSPACE_APP,
                entity_type="plugin_external_record",
                resource_type="plugin_external_record",
                label="Plugin External Record",
                label_key="ai.search.entityPluginExternalRecord",
                workspace_loader=lambda db, *, workspace: [],
                document_loader=lambda db, *, entity_type, entity_id: {
                    "workspace_id": "ws-other",
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "title": "Wrong workspace",
                },
            )
        )
        monkeypatch.setattr(
            tasks_module.index_resource,
            "retry",
            lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("projection identity mismatch must not retry")
            ),
        )

        result = tasks_module.index_resource.run("job-identity-mismatch")

        assert result == "projection_identity_mismatch"
        with Session(engine) as session:
            stored = session.get(SearchIndexJob, "job-identity-mismatch")
            assert stored is not None
            assert stored.status == "failed"
            assert stored.attempts == 1
            assert stored.next_retry_at is None
            assert stored.last_error is not None
            assert stored.last_error.startswith("projection_identity_mismatch: ")
    finally:
        _reset_search_registries()


def test_search_worker_cancels_superseded_processing_job_before_mutation(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-superseded.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                SearchIndexJob(
                    id="job-stale-processing",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="upsert",
                    trace_context={},
                    status="processing",
                    attempts=1,
                    created_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=2),
                ),
                SearchIndexJob(
                    id="job-newer-pending",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="delete",
                    trace_context={},
                    status="pending",
                    attempts=0,
                    created_at=now - timedelta(minutes=1),
                    updated_at=now - timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")

    class _FailingSearchClient:
        def upsert_document(self, document):
            del document
            raise AssertionError("superseded search job must not mutate the index")

        def delete_document(self, *, workspace_id, entity_type, entity_id):
            del workspace_id, entity_type, entity_id
            raise AssertionError("superseded search job must not mutate the index")

    monkeypatch.setattr(tasks_module, "_search_client", lambda: _FailingSearchClient())

    result = tasks_module.index_resource.run("job-stale-processing")

    assert result == "superseded"
    with Session(engine) as session:
        stale = session.get(SearchIndexJob, "job-stale-processing")
        pending = session.get(SearchIndexJob, "job-newer-pending")
        assert stale is not None
        assert pending is not None
        assert stale.status == "cancelled"
        assert stale.last_error == "superseded_by:job-newer-pending:before_mutation"
        assert pending.status == "pending"


def test_search_worker_does_not_treat_older_pending_job_as_superseding(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-older-pending.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                SearchIndexJob(
                    id="job-older-pending",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="delete",
                    trace_context={},
                    status="pending",
                    attempts=0,
                    created_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=3),
                ),
                SearchIndexJob(
                    id="job-current-processing",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="upsert",
                    trace_context={},
                    status="processing",
                    attempts=0,
                    created_at=now - timedelta(hours=1),
                    updated_at=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    with Session(engine) as session:
        older = session.get(SearchIndexJob, "job-older-pending")
        current = session.get(SearchIndexJob, "job-current-processing")
        assert older is not None
        assert current is not None
        assert older.status == "pending"
        assert current.status == "processing"
        assert tasks_module._has_superseding_pending_job(session, job=current) is False


def test_search_worker_cancels_older_pending_job_before_retry(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "worker-search-retry-older-pending.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                SearchIndexJob(
                    id="job-older-pending",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="delete",
                    trace_context={},
                    status="pending",
                    attempts=0,
                    created_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=3),
                ),
                SearchIndexJob(
                    id="job-current-processing",
                    workspace_id="ws-1",
                    entity_type="plugin_external_record",
                    entity_id="record-1",
                    operation="upsert",
                    trace_context={},
                    status="processing",
                    attempts=1,
                    created_at=now - timedelta(hours=1),
                    updated_at=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    with Session(engine) as session:
        current = session.get(SearchIndexJob, "job-current-processing")
        assert current is not None
        tasks_module._cancel_older_pending_search_index_jobs(session, job=current)

    with Session(engine) as session:
        older = session.get(SearchIndexJob, "job-older-pending")
        current = session.get(SearchIndexJob, "job-current-processing")
        assert older is not None
        assert current is not None
        assert older.status == "cancelled"
        assert older.last_error == "superseded_by:job-current-processing:retry"
        assert current.status == "processing"


def test_search_republisher_publishes_due_pending_jobs(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "worker-search-republish.sqlite3"
    _seed_llm_routing_control_plane(db_path)
    engine = create_engine(_worker_dsn(db_path))
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            SearchIndexJob.__table__,
        ],
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                SearchIndexJob(
                    id="job-due",
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="doc-due",
                    operation="upsert",
                    trace_context={},
                    status="pending",
                    attempts=0,
                    next_retry_at=None,
                ),
                SearchIndexJob(
                    id="job-future",
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="doc-future",
                    operation="upsert",
                    trace_context={},
                    status="pending",
                    attempts=0,
                    next_retry_at=now + timedelta(minutes=5),
                ),
                SearchIndexJob(
                    id="job-processing",
                    workspace_id="ws-1",
                    entity_type="doc",
                    entity_id="doc-processing",
                    operation="upsert",
                    trace_context={},
                    status="processing",
                    attempts=1,
                ),
            ]
        )
        session.commit()

    published: list[tuple[str, list[str], str]] = []

    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            assert retry is False
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryApp:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", _worker_dsn(db_path))
    tasks_module = _reload_worker_module("open_alm_worker.tasks.search_index")
    monkeypatch.setattr(tasks_module, "celery_app", _FakeCeleryApp())

    assert tasks_module.republish_pending_index_jobs.run(limit=10) == 1
    assert published == [("search.index_resource", ["job-due"], "search_index_realtime")]
