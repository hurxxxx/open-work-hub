from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileSourceMetadata,
    FileManagerFolder,
)
from open_work_hub_api.domains.retrieval.files_generation_runner import (
    FilesBackendPairInspection,
    FilesGenerationBaselineMode,
    FilesGenerationError,
    FilesGenerationMaterializationBatch,
    FilesGenerationPairSpec,
    FilesGenerationRunner,
    FilesPhysicalProjectionInventory,
    FilesSourceProjectionSnapshot,
    load_files_source_snapshot,
)
from open_work_hub_api.domains.retrieval.files_quality_judgments import FilesQualityJudgmentSnapshot
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalEvaluationReport,
    RetrievalQualityGateArtifact,
    retrieval_embedding_generation_identity,
    retrieval_quality_corpus_sha256,
    retrieval_reranker_generation_identity,
)
from open_work_hub_api.domains.retrieval.files_generation_backends import (
    FilesPhysicalGenerationBackends,
)
from open_work_hub_api.domains.retrieval.files_generation_materializer import (
    FilesCachedProjectionMaterializer,
)
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionGeneration,
    RetrievalProjectionGenerationAttestation,
    RetrievalProjectionGenerationState,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_identity import (
    canonical_search_document_id,
    canonical_vector_point_id,
)
from open_work_hub_api.domains.rag.runtime import (
    resolve_default_collection_name,
    resolve_partitioned_rag_collection_alias,
)
from open_work_hub_api.domains.search.index_gateway import (
    keyword_search_index_alias,
    keyword_search_partitioned_index_alias,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
    NATIVE_DOC_RESOURCE_TYPE,
)


_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_RUNNER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "manage_files_retrieval_generation.py"
)
_PARTITION_ID = "826901c6-58b1-4687-b7e0-d7844a337a01"


def _load_runner_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "test_manage_files_retrieval_generation_script",
        _RUNNER_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generation_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        RetrievalPartition.__table__,
        RetrievalProjectionEvent.__table__,
        RetrievalProjectionGeneration.__table__,
        RetrievalProjectionGenerationAttestation.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add(
            RetrievalPartition(
                id=_PARTITION_ID,
                source_namespace="files-generation-test",
                candidate_scope_kind="company",
                is_default_ingest=False,
            )
        )
    try:
        yield factory
    finally:
        engine.dispose()


def _settings(*, environment: str = "development") -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        opensearch_url="http://opensearch.invalid",
        opensearch_index_prefix="test",
        keyword_search_backend="opensearch",
        rag_vector_index_provider="qdrant",
        rag_qdrant_url="http://qdrant.invalid",
        rag_qdrant_api_key="secret-never-rendered",
        rag_qdrant_collection_prefix="test-rag",
        rag_embedding_provider="fake",
        rag_rerank_provider="fake",
        rag_local_reranker_model="fake-reranker",
        rag_rerank_candidate_k=20,
        files_retrieval_enabled=False,
    )


def _source_snapshot(
    *,
    count: int = 0,
    unavailable: int = 0,
    event_watermark: int = 0,
    files_event_watermark: int = 0,
) -> FilesSourceProjectionSnapshot:
    identity = _EMPTY_SHA256 if count == 0 else "1" * 64
    return FilesSourceProjectionSnapshot(
        event_watermark=event_watermark,
        files_event_watermark=files_event_watermark,
        resource_count=count,
        identity_sha256=identity,
        artifact_sha256=_EMPTY_SHA256 if count == 0 else "2" * 64,
        unsupported_count=0,
        unavailable_count=unavailable,
    )


def _inventory(
    *, resources: int = 0, records: int | None = None
) -> FilesPhysicalProjectionInventory:
    return FilesPhysicalProjectionInventory(
        resource_count=resources,
        record_count=resources if records is None else records,
        identity_sha256=_EMPTY_SHA256 if resources == 0 else "1" * 64,
        content_sha256=_EMPTY_SHA256 if resources == 0 else "3" * 64,
        config_sha256="4" * 64,
        physical_id="physical-id",
        projection_sha256=_EMPTY_SHA256 if resources == 0 else "5" * 64,
    )


def _loaded_source_snapshot(
    *,
    metadata_version: int = 1,
    access_scope_kind: str = "company",
    source_title: str | None = None,
) -> FilesSourceProjectionSnapshot:
    external = source_title is not None
    row = SimpleNamespace(
        id="file-1",
        extraction_status="ready",
        extraction_content_checksum="a" * 64,
        extraction_text="stable source text",
        extraction_blocks=[
            {
                "document_id": "file-1",
                "block_id": "file-1:text:1",
                "locator_kind": "document",
                "locator_label": "Document",
                "section_path": "Body",
                "block_kind": "text",
                "text": "stable source text",
                "rows": [],
            }
        ],
        extraction_metadata={"parser_version": "test-v1"},
        file_partition_id=_PARTITION_ID,
        projection_version=1,
        head_partition_id=_PARTITION_ID,
        desired_state="active",
        content_checksum="a" * 64,
        filename="source.txt",
        content_type="text/plain",
        size_bytes=18,
        visibility="company",
        folder_id=None,
        corpus_id="corpus-1",
        owner_id="user-1",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        owner_display_name="Owner",
        owner_full_name="Owner Name",
        corpus_partition_id=_PARTITION_ID,
        corpus_access_scope_kind=access_scope_kind,
        corpus_metadata_version=metadata_version,
        corpus_source_managed=external,
        corpus_authorization_mode="explicit_grants" if external else "cohort",
        source_metadata_source_kind="external_repository" if external else None,
        source_metadata_source_updated_at=(datetime(2026, 1, 2, tzinfo=UTC) if external else None),
        source_metadata_title=source_title,
        source_metadata_author="Source Author" if external else None,
        source_metadata_authored_at=(datetime(2025, 12, 1, tzinfo=UTC) if external else None),
        source_metadata_department="Engineering" if external else None,
        source_metadata_document_type="report" if external else None,
        source_metadata_acl_resolved=True if external else None,
        partition_source_namespace="files",
        partition_candidate_scope_kind=access_scope_kind,
        partition_candidate_user_id=None,
        partition_state="active",
        partition_metadata_version=metadata_version,
        partition_is_default_ingest=False,
    )

    class Result:
        def __iter__(self):
            return iter((row,))

    class Db:
        def execute(self, _statement: object) -> Result:
            return Result()

        def scalar(self, _statement: object) -> int:
            return 0

    return load_files_source_snapshot(Db())  # type: ignore[arg-type]


def test_source_snapshot_binds_corpus_and_partition_acl_metadata_versions() -> None:
    first = _loaded_source_snapshot(metadata_version=1)
    transitioned = _loaded_source_snapshot(metadata_version=2)

    assert first.unavailable_count == transitioned.unavailable_count == 0
    assert transitioned.identity_sha256 == first.identity_sha256
    assert transitioned.artifact_sha256 == first.artifact_sha256
    assert transitioned.acl_envelope_sha256 != first.acl_envelope_sha256
    assert first.opensearch_projection_sha256 is not None
    assert first.qdrant_projection_sha256 is not None
    assert transitioned.opensearch_projection_sha256 == first.opensearch_projection_sha256
    assert transitioned.qdrant_projection_sha256 == first.qdrant_projection_sha256
    assert first.qdrant_record_count == 1


def test_source_snapshot_separates_acl_transitions_from_projection_content() -> None:
    initial = _loaded_source_snapshot()
    company = _loaded_source_snapshot(
        metadata_version=2,
        access_scope_kind="company",
    )
    moved = _loaded_source_snapshot(
        metadata_version=3,
    )

    assert (
        len(
            {
                initial.acl_envelope_sha256,
                company.acl_envelope_sha256,
                moved.acl_envelope_sha256,
            }
        )
        == 3
    )
    assert {
        initial.opensearch_projection_sha256,
        company.opensearch_projection_sha256,
        moved.opensearch_projection_sha256,
    } == {initial.opensearch_projection_sha256}
    assert {
        initial.qdrant_projection_sha256,
        company.qdrant_projection_sha256,
        moved.qdrant_projection_sha256,
    } == {initial.qdrant_projection_sha256}


def test_source_snapshot_includes_safe_external_metadata_in_projection_contracts() -> None:
    first = _loaded_source_snapshot(source_title="Source title v1")
    updated = _loaded_source_snapshot(source_title="Source title v2")

    assert first.unavailable_count == updated.unavailable_count == 0
    assert first.identity_sha256 == updated.identity_sha256
    assert first.artifact_sha256 == updated.artifact_sha256
    assert first.acl_envelope_sha256 == updated.acl_envelope_sha256
    assert first.opensearch_projection_sha256 != updated.opensearch_projection_sha256
    assert first.qdrant_projection_sha256 != updated.qdrant_projection_sha256


def _quality_corpus_bytes() -> bytes:
    return json.dumps(
        {
            "artifact_version": 1,
            "corpus_id": "files-generation-quality-v1",
            "cases": [
                {
                    "query_id": f"query-{index}",
                    "user_id": "user-1",
                    "query": f"quality query {index}",
                    "relevant_resource_ids": ["file-1"],
                    "forbidden_resource_ids": ["file-forbidden"],
                    "source_kinds": ["files"],
                }
                for index in range(60)
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _passing_v3_quality_artifact(
    *,
    settings: SimpleNamespace,
    corpus_bytes: bytes,
) -> RetrievalQualityGateArtifact:
    embedding_identity = retrieval_embedding_generation_identity(settings)
    reranker_identity = retrieval_reranker_generation_identity(settings)
    baseline = RetrievalEvaluationReport(
        query_count=60,
        recall_at_k=0.5,
        mrr_at_k=0.5,
        ndcg_at_k=0.5,
        p95_latency_ms=100,
        acl_violation_count=0,
        citation_failure_count=0,
    )
    hybrid = baseline.model_copy(update={"recall_at_k": 1.0, "mrr_at_k": 1.0, "ndcg_at_k": 1.0})
    return RetrievalQualityGateArtifact(
        artifact_version=3,
        corpus_id="files-generation-quality-v1",
        corpus_sha256=retrieval_quality_corpus_sha256(corpus_bytes),
        index_generation="v3-quality",
        keyword_index_uuid="physical-id",
        keyword_index_config_sha256="4" * 64,
        keyword_index_sha256="3" * 64,
        qdrant_physical_id="physical-id",
        qdrant_config_sha256="4" * 64,
        qdrant_content_sha256="3" * 64,
        embedding_model_identity=embedding_identity.model_identity,
        embedding_config_sha256=embedding_identity.config_sha256,
        reranker_model_identity=reranker_identity.model_identity,
        reranker_config_sha256=reranker_identity.config_sha256,
        source_files_event_watermark=0,
        source_resource_count=1,
        source_identity_sha256="1" * 64,
        source_artifact_sha256="2" * 64,
        source_acl_envelope_sha256=_EMPTY_SHA256,
        judgment_acl_sha256="6" * 64,
        hybrid=hybrid,
        bm25=baseline,
        dense=baseline,
    )


class _FakeBackends:
    def __init__(self) -> None:
        self.opensearch: FilesPhysicalProjectionInventory | None = None
        self.qdrant: FilesPhysicalProjectionInventory | None = None
        self.prepare_calls = 0
        self.aliases: dict[str, str] = {}
        self.alias_operations: list[tuple[str, str, str | None]] = []
        self.fail_alias_backend: str | None = None
        self.fail_after_move = False
        self.fail_remove_backend: str | None = None

    def inspect_pair(self, spec) -> FilesBackendPairInspection:
        del spec
        return FilesBackendPairInspection(
            opensearch=self.opensearch,
            qdrant=self.qdrant,
        )

    def prepare_empty_pair(self, spec) -> None:
        del spec
        self.prepare_calls += 1
        self.opensearch = _inventory()
        self.qdrant = _inventory(records=0)

    def alias_target(self, *, backend: str, alias_name: str) -> str | None:
        del backend
        return self.aliases.get(alias_name)

    def set_alias(self, *, backend: str, alias_name: str, physical_name: str) -> None:
        self.alias_operations.append((backend, alias_name, physical_name))
        if self.fail_alias_backend == backend and not self.fail_after_move:
            raise RuntimeError("secret backend failure")
        self.aliases[alias_name] = physical_name
        if self.fail_alias_backend == backend and self.fail_after_move:
            raise RuntimeError("secret backend failure after move")

    def remove_alias(self, *, backend: str, alias_name: str) -> None:
        self.alias_operations.append((backend, alias_name, None))
        if self.fail_remove_backend == backend:
            raise RuntimeError("secret alias restore failure")
        self.aliases.pop(alias_name, None)


class _FakeMaterializer:
    def __init__(
        self,
        *,
        backends: _FakeBackends,
        target_resources: int,
        complete: bool = True,
        caught_up: bool = True,
    ) -> None:
        self.backends = backends
        self.target_resources = target_resources
        self.complete = complete
        self.caught_up = caught_up
        self.calls = 0

    def materialize_batch(self, **kwargs) -> FilesGenerationMaterializationBatch:
        self.calls += 1
        through = int(kwargs["through_event_sequence"])
        after = int(kwargs["after_event_sequence"])
        if self.complete:
            self.backends.opensearch = _inventory(resources=self.target_resources)
            self.backends.qdrant = _inventory(
                resources=self.target_resources,
                records=max(self.target_resources, 1),
            )
        return FilesGenerationMaterializationBatch(
            target_event_sequence=through,
            next_event_sequence=through if self.complete else after + 1,
            scanned_events=1,
            keyword_succeeded=1,
            vector_succeeded=1,
            complete=self.complete,
            caught_up=self.caught_up,
            keyword_remaining=0,
            vector_remaining=0,
        )

    def inspect_reconciliation(self, *, through_event_sequence: int) -> object:
        return SimpleNamespace(
            target_event_sequence=through_event_sequence,
            current_event_sequence=through_event_sequence,
            keyword_remaining=0,
            vector_remaining=0,
            caught_up=True,
        )


def _runner(
    factory: sessionmaker[Session],
    backends: _FakeBackends,
    *,
    snapshot: FilesSourceProjectionSnapshot | None = None,
    materializer: _FakeMaterializer | None = None,
    source_snapshot_loader: Callable[[Session], FilesSourceProjectionSnapshot] | None = None,
) -> FilesGenerationRunner:
    return FilesGenerationRunner(
        session_factory=factory,
        settings=_settings(),  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=(
            source_snapshot_loader or (lambda _db: snapshot or _source_snapshot())
        ),
        materializer=materializer,
    )


def _append_projection_event(
    factory: sessionmaker[Session],
    *,
    resource_type: str,
    resource_id: str,
) -> int:
    with factory.begin() as db:
        event_sequence = (
            int(db.scalar(select(func.max(RetrievalProjectionEvent.event_sequence))) or 0) + 1
        )
        db.add(
            RetrievalProjectionEvent(
                event_sequence=event_sequence,
                resource_type=resource_type,
                resource_id=resource_id,
                projection_version=1,
                retrieval_partition_id=_PARTITION_ID,
                change_kind="delete",
                desired_state="deleted",
            )
        )
    return event_sequence


def _scoped_empty_source_snapshot(db: Session) -> FilesSourceProjectionSnapshot:
    return _source_snapshot(
        event_watermark=int(
            db.scalar(select(func.max(RetrievalProjectionEvent.event_sequence))) or 0
        ),
        files_event_watermark=int(
            db.scalar(
                select(func.max(RetrievalProjectionEvent.event_sequence)).where(
                    RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
                )
            )
            or 0
        ),
    )


def test_empty_development_pair_preparation_is_idempotent(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _runner(generation_session_factory, backends)

    first = runner.prepare(
        generation_key="dev-empty",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    second = runner.prepare(
        generation_key="dev-empty",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    assert first.generation_key == second.generation_key == "dev-empty"
    assert first.state == second.state == "replaying"
    assert backends.prepare_calls == 1
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert len(rows) == 2
    assert {row.state for row in rows} == {"replaying"}
    assert {row.expected_projection_count for row in rows} == {0}


def test_adopt_prepared_reuses_complete_projection_without_reprocessing(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = _inventory(resources=1, records=7)
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=_source_snapshot(count=1),
    )

    result = runner.prepare(
        generation_key="adopt-ready",
        baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
    )

    assert result.state == "replaying"
    assert result.source_resource_count == 1
    assert backends.prepare_calls == 0


def test_adopt_prepared_rejects_missing_qdrant_chunk_with_same_resource_identity(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = _inventory(resources=1, records=1)
    snapshot = replace(_source_snapshot(count=1), qdrant_record_count=2)
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=snapshot,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.prepare(
            generation_key="missing-qdrant-chunk",
            baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
        )

    assert caught.value.code == "qdrant_point_count_mismatch"


def test_adopt_prepared_rejects_changed_opensearch_payload_with_same_identity(
    generation_session_factory: sessionmaker[Session],
) -> None:
    expected_contract = "5" * 64
    backends = _FakeBackends()
    backends.opensearch = replace(
        _inventory(resources=1),
        projection_sha256="6" * 64,
    )
    backends.qdrant = _inventory(resources=1)
    snapshot = replace(
        _source_snapshot(count=1),
        opensearch_projection_sha256=expected_contract,
    )
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=snapshot,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.prepare(
            generation_key="changed-opensearch-payload",
            baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
        )

    assert caught.value.code == "opensearch_projection_content_mismatch"


def test_adopt_prepared_rejects_changed_qdrant_payload_with_same_chunk_identity(
    generation_session_factory: sessionmaker[Session],
) -> None:
    expected_contract = "5" * 64
    backends = _FakeBackends()
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = replace(
        _inventory(resources=1),
        projection_sha256="6" * 64,
    )
    snapshot = replace(
        _source_snapshot(count=1),
        qdrant_projection_sha256=expected_contract,
    )
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=snapshot,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.prepare(
            generation_key="changed-qdrant-payload",
            baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
        )

    assert caught.value.code == "qdrant_projection_content_mismatch"


def test_adopt_prepared_never_silently_creates_a_missing_baseline(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=_source_snapshot(count=1),
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.prepare(
            generation_key="missing-prepared",
            baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
        )

    assert caught.value.code == "prepared_baseline_missing"
    assert backends.prepare_calls == 0
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.state for row in rows} == {"preparing"}


def test_empty_prepare_repairs_a_partial_physical_creation_idempotently(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    backends.opensearch = _inventory()
    runner = _runner(generation_session_factory, backends)

    result = runner.prepare(
        generation_key="resume-partial",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    assert result.state == "replaying"
    assert backends.prepare_calls == 1
    assert backends.opensearch is not None
    assert backends.qdrant is not None


def test_cached_artifact_materialization_bootstraps_nonempty_pair_without_adoption_deadlock(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    snapshot = _source_snapshot(count=1)
    materializer = _FakeMaterializer(backends=backends, target_resources=1)
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=snapshot,
        materializer=materializer,
    )

    prepared = runner.prepare(
        generation_key="cached-bootstrap",
        baseline_mode=FilesGenerationBaselineMode.CACHED_ARTIFACTS,
    )
    materialized = runner.materialize(
        generation_key="cached-bootstrap",
        after_event_sequence=0,
        through_event_sequence=0,
        limit=100,
        writes_quiesced=True,
        workers_stopped=True,
    )

    assert prepared.state == "baselining"
    assert materialized.state == "replaying"
    assert materialized.complete is True
    assert materializer.calls == 1
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.state for row in rows} == {"replaying"}
    assert {row.expected_projection_count for row in rows} == {1}


def test_materializer_refreshes_delayed_opensearch_before_runner_reconciliation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            RetrievalProjectionGeneration.__table__,
            SearchIndexJob.__table__,
            RagSyncJob.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    checksum = "a" * 64
    with factory.begin() as db:
        db.add_all(
            [
                User(
                    id="user-1",
                    login_id="user-1",
                    email="user-1@example.com",
                    full_name="User 1",
                    password_hash="hash",
                ),
                RetrievalPartition(
                    id=_PARTITION_ID,
                    source_namespace="files",
                    candidate_scope_kind="company",
                    is_default_ingest=False,
                ),
            ]
        )
        db.flush()
        db.add(
            FileManagerFile(
                id="file-visible-after-refresh",
                retrieval_partition_id=_PARTITION_ID,
                owner_id="user-1",
                filename="delayed-visibility.txt",
                content_type="text/plain",
                size_bytes=25,
                storage_key="files/delayed-visibility/document.txt",
                visibility="company",
                extraction_status="ready",
                extraction_content_checksum=checksum,
                extraction_text="visible only after refresh",
                extraction_blocks=[
                    {
                        "document_id": "file-visible-after-refresh",
                        "block_id": "file-visible-after-refresh:text:1",
                        "locator_kind": "document",
                        "locator_label": "Document",
                        "section_path": "Body",
                        "block_kind": "text",
                        "text": "visible only after refresh",
                        "rows": [],
                    }
                ],
                extraction_metadata={"parser_version": "test-v1"},
            )
        )
        db.add_all(
            [
                RetrievalProjectionHead(
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id="file-visible-after-refresh",
                    projection_version=1,
                    retrieval_partition_id=_PARTITION_ID,
                    desired_state="active",
                    content_checksum=checksum,
                ),
                RetrievalProjectionEvent(
                    event_sequence=1,
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id="file-visible-after-refresh",
                    projection_version=1,
                    retrieval_partition_id=_PARTITION_ID,
                    change_kind="content",
                    desired_state="active",
                    content_checksum=checksum,
                ),
            ]
        )

    class DelayedVisibilityBackends(_FakeBackends):
        def __init__(self) -> None:
            super().__init__()
            self.opensearch = _inventory()
            self.qdrant = _inventory(records=0)
            self.inspection_counts: list[tuple[int, int]] = []

        def inspect_pair(self, spec) -> FilesBackendPairInspection:
            pair = super().inspect_pair(spec)
            assert pair.opensearch is not None and pair.qdrant is not None
            self.inspection_counts.append(
                (pair.opensearch.resource_count, pair.qdrant.resource_count)
            )
            return pair

    backends = DelayedVisibilityBackends()

    class DelayedVisibilityKeywordClient:
        def __init__(self) -> None:
            self.pending: FilesPhysicalProjectionInventory | None = None
            self.visible_counts_after_write: list[int] = []
            self.refresh_calls = 0

        def upsert_partitioned_document(self, _document: dict[str, Any]) -> str:
            self.pending = _inventory(resources=1)
            assert backends.opensearch is not None
            self.visible_counts_after_write.append(backends.opensearch.resource_count)
            return "indexed"

        def delete_partitioned_document(
            self,
            *,
            resource_type: str,
            resource_id: str,
            projection_version: int,
        ) -> str:
            del resource_type, resource_id, projection_version
            raise AssertionError("the upsert fixture must not delete a keyword document")

        def refresh_partitioned_index(self) -> None:
            self.refresh_calls += 1
            assert self.pending is not None
            backends.opensearch = self.pending
            self.pending = None

    class ImmediateRagService:
        sync_calls = 0

        def sync_projection_with_fence(
            self,
            projection: object,
            *,
            collection: str,
            before_vector_write: Callable[[], None],
        ) -> None:
            del projection, collection
            before_vector_write()
            self.sync_calls += 1
            backends.qdrant = _inventory(resources=1)

    keyword = DelayedVisibilityKeywordClient()
    rag = ImmediateRagService()
    materializer = FilesCachedProjectionMaterializer(
        session_factory=factory,
        settings=_settings(),  # type: ignore[arg-type]
        keyword_client_factory=lambda _physical: keyword,  # type: ignore[arg-type]
        rag_service_factory=lambda _collection: rag,  # type: ignore[arg-type]
    )
    snapshot = _source_snapshot(
        count=1,
        event_watermark=1,
        files_event_watermark=1,
    )
    runner = FilesGenerationRunner(
        session_factory=factory,
        settings=_settings(),  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: snapshot,
        materializer=materializer,
    )

    try:
        runner.prepare(
            generation_key="nrt-refresh",
            baseline_mode=FilesGenerationBaselineMode.CACHED_ARTIFACTS,
        )
        result = runner.materialize(
            generation_key="nrt-refresh",
            after_event_sequence=0,
            through_event_sequence=1,
            limit=100,
            writes_quiesced=True,
            workers_stopped=True,
        )

        assert keyword.visible_counts_after_write == [0]
        assert keyword.refresh_calls == 1
        assert keyword.pending is None
        assert rag.sync_calls == 1
        assert backends.inspection_counts == [(0, 0), (1, 1)]
        assert result.state == "replaying"
        assert result.complete is True
    finally:
        engine.dispose()


def test_materializer_rejects_incomplete_keyword_client_at_factory_boundary(
    generation_session_factory: sessionmaker[Session],
) -> None:
    class InvalidRefreshKeywordClient:
        refresh_partitioned_index = object()

        def upsert_partitioned_document(self, _document: dict[str, Any]) -> str:
            return "upserted"

        def delete_partitioned_document(self, **_kwargs: object) -> str:
            return "deleted"

    rag_factory_calls = 0

    def rag_factory(_collection: str) -> object:
        nonlocal rag_factory_calls
        rag_factory_calls += 1
        return object()

    materializer = FilesCachedProjectionMaterializer(
        session_factory=generation_session_factory,
        settings=_settings(),  # type: ignore[arg-type]
        keyword_client_factory=lambda _physical: InvalidRefreshKeywordClient(),  # type: ignore[arg-type]
        rag_service_factory=rag_factory,  # type: ignore[arg-type]
    )
    spec = FilesGenerationPairSpec(
        generation_key="incomplete-keyword-client",
        opensearch_physical_name="test_keyword_search_documents_v3_incomplete",
        opensearch_alias_name="test_keyword_search_documents_v3",
        qdrant_physical_name="test-rag-fake-v1-incomplete",
        qdrant_alias_name="test-rag-fake-v1",
    )

    with pytest.raises(
        RuntimeError,
        match="complete partitioned keyword generation client",
    ):
        materializer.materialize_batch(
            spec=spec,
            after_event_sequence=0,
            through_event_sequence=0,
            limit=100,
        )

    assert rag_factory_calls == 0


def test_unavailable_source_blocks_before_generation_or_backend_mutation(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=_source_snapshot(unavailable=1),
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.prepare(
            generation_key="blocked-source",
            baseline_mode=FilesGenerationBaselineMode.EMPTY,
        )

    assert caught.value.code == "source_baseline_unavailable"
    assert backends.prepare_calls == 0
    with generation_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RetrievalProjectionGeneration)) == 0


def test_prepare_dry_run_has_no_database_or_backend_writes(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _runner(generation_session_factory, backends)

    result = runner.prepare(
        generation_key="dry-run",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
        dry_run=True,
    )

    assert result.state == "planned"
    assert result.dry_run is True
    assert backends.prepare_calls == 0
    with generation_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RetrievalProjectionGeneration)) == 0


def _ready_empty_pair(
    factory: sessionmaker[Session],
    backends: _FakeBackends,
    *,
    generation_key: str,
) -> FilesGenerationRunner:
    runner = _runner(factory, backends)
    runner.prepare(
        generation_key=generation_key,
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key=generation_key,
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_non_production=True,
    )
    return runner


def test_validation_requires_explicit_reconciliation_watermark(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _runner(generation_session_factory, backends)
    runner.prepare(
        generation_key="needs-reconcile",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.validate(
            generation_key="needs-reconcile",
            writes_quiesced=True,
            allow_empty_non_production=True,
        )

    assert caught.value.code == "reconciliation_watermark_required"


def test_empty_generation_validation_is_forbidden_in_production(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=_settings(environment="production"),  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(),
    )
    runner.prepare(
        generation_key="prod-empty",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.validate(
            generation_key="prod-empty",
            writes_quiesced=True,
            reconciliation_watermark=0,
            allow_empty_non_production=True,
        )

    assert caught.value.code == "empty_generation_forbidden_in_production"


def test_empty_generation_can_be_preprovisioned_in_production_with_explicit_confirmation(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    settings = _settings(environment="production")
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(),
    )
    runner.prepare(
        generation_key="prod-empty-bootstrap",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    validation = runner.validate(
        generation_key="prod-empty-bootstrap",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_production_bootstrap=True,
    )
    cutover = runner.cutover(
        generation_key="prod-empty-bootstrap",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )

    assert validation.state == RetrievalProjectionGenerationState.READY.value
    assert cutover.state == RetrievalProjectionGenerationState.ACTIVE.value
    with generation_session_factory() as db:
        rows = tuple(
            db.scalars(
                select(RetrievalProjectionGeneration).order_by(
                    RetrievalProjectionGeneration.backend.asc()
                )
            ).all()
        )
    assert len(rows) == 2
    assert {row.state for row in rows} == {RetrievalProjectionGenerationState.ACTIVE.value}
    assert {
        row.validation_details["quality"]["mode"]  # type: ignore[index]
        for row in rows
    } == {"empty_production_bootstrap"}
    embedding_identity = retrieval_embedding_generation_identity(settings)
    reranker_identity = retrieval_reranker_generation_identity(settings)
    for row in rows:
        quality = row.validation_details["quality"]  # type: ignore[index]
        assert quality["quality_status"] == "deferred_until_nonempty"
        assert quality["embedding_model_identity"] == embedding_identity.model_identity
        assert quality["embedding_config_sha256"] == embedding_identity.config_sha256
        assert quality["reranker_model_identity"] == reranker_identity.model_identity
        assert quality["reranker_config_sha256"] == reranker_identity.config_sha256


def test_empty_production_bootstrap_rejects_unsupported_active_files(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=_settings(environment="production"),  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: replace(
            _source_snapshot(),
            unsupported_count=1,
        ),
    )
    runner.prepare(
        generation_key="prod-empty-unsupported",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.validate(
            generation_key="prod-empty-unsupported",
            writes_quiesced=True,
            reconciliation_watermark=0,
            allow_empty_production_bootstrap=True,
        )

    assert caught.value.code == "empty_production_bootstrap_requires_no_active_files"


def test_empty_production_bootstrap_rejects_existing_active_generation(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    settings = _settings(environment="production")
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(),
    )
    runner.prepare(
        generation_key="prod-empty-first",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="prod-empty-first",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_production_bootstrap=True,
    )
    runner.cutover(
        generation_key="prod-empty-first",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    runner.prepare(
        generation_key="prod-empty-second",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.validate(
            generation_key="prod-empty-second",
            writes_quiesced=True,
            reconciliation_watermark=0,
            allow_empty_production_bootstrap=True,
        )

    assert caught.value.code == "empty_production_bootstrap_requires_initial_activation"


def test_active_empty_generation_accepts_append_only_quality_attestation(
    generation_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = _FakeBackends()
    settings = _settings(environment="production")
    snapshots = [_source_snapshot()]
    materializer = _FakeMaterializer(backends=backends, target_resources=1)
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: snapshots[0],
        materializer=materializer,
        quality_judgment_validator=lambda _corpus: FilesQualityJudgmentSnapshot(
            acl_sha256="6" * 64,
            context_count=1,
            active_resource_count=1,
        ),
    )
    runner.prepare(
        generation_key="v3-quality",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="v3-quality",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_production_bootstrap=True,
    )
    runner.cutover(
        generation_key="v3-quality",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )

    _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-1",
    )
    snapshots[0] = _source_snapshot(
        count=1,
        event_watermark=1,
        files_event_watermark=1,
    )
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = _inventory(resources=1)
    monkeypatch.setattr(
        runner,
        "_active_source_scope_kinds",
        lambda: ("company",),
    )
    corpus_bytes = _quality_corpus_bytes()
    artifact = _passing_v3_quality_artifact(
        settings=settings,
        corpus_bytes=corpus_bytes,
    ).model_copy(update={"source_files_event_watermark": 1})

    first = runner.attest_active(
        generation_key="v3-quality",
        writes_quiesced=True,
        quality_artifact=artifact,
        quality_corpus_bytes=corpus_bytes,
        scope_coverage=["company"],
    )
    second = runner.attest_active(
        generation_key="v3-quality",
        writes_quiesced=True,
        quality_artifact=artifact,
        quality_corpus_bytes=corpus_bytes,
        scope_coverage=["company"],
    )

    assert first.state == second.state == "quality-attested"
    with generation_session_factory() as db:
        attestations = tuple(db.scalars(select(RetrievalProjectionGenerationAttestation)).all())
    assert len(attestations) == 1
    attestation = attestations[0]
    assert attestation.generation_key == "v3-quality"
    assert attestation.source_files_event_watermark == 1
    assert attestation.source_resource_count == 1
    assert attestation.scope_coverage == ["company"]
    assert attestation.quality_details["mode"] == "judged_corpus"


def test_active_quality_attestation_rejects_scope_mismatch(
    generation_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = _FakeBackends()
    settings = _settings(environment="production")
    snapshots = [_source_snapshot()]
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: snapshots[0],
        materializer=_FakeMaterializer(backends=backends, target_resources=1),
        quality_judgment_validator=lambda _corpus: FilesQualityJudgmentSnapshot(
            acl_sha256="6" * 64,
            context_count=1,
            active_resource_count=1,
        ),
    )
    runner.prepare(
        generation_key="v3-quality",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="v3-quality",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_production_bootstrap=True,
    )
    runner.cutover(
        generation_key="v3-quality",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    snapshots[0] = _source_snapshot(
        count=1,
        event_watermark=1,
        files_event_watermark=1,
    )
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = _inventory(resources=1)
    monkeypatch.setattr(
        runner,
        "_active_source_scope_kinds",
        lambda: ("company",),
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.attest_active(
            generation_key="v3-quality",
            writes_quiesced=True,
            quality_artifact=_passing_v3_quality_artifact(
                settings=settings,
                corpus_bytes=_quality_corpus_bytes(),
            ).model_copy(update={"source_files_event_watermark": 1}),
            quality_corpus_bytes=_quality_corpus_bytes(),
            scope_coverage=["personal"],
        )

    assert caught.value.code == "attestation_scope_coverage_mismatch"
    with generation_session_factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(RetrievalProjectionGenerationAttestation))
            == 0
        )


def test_empty_production_bootstrap_fences_model_configuration_drift(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    settings = _settings(environment="production")
    runner = FilesGenerationRunner(
        session_factory=generation_session_factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(),
    )
    runner.prepare(
        generation_key="prod-empty-model-fence",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="prod-empty-model-fence",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_production_bootstrap=True,
    )
    runner.cutover(
        generation_key="prod-empty-model-fence",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    settings.rag_local_reranker_model = "changed-reranker"

    with pytest.raises(FilesGenerationError) as caught:
        runner.verify_active()

    assert caught.value.code == "reranker_generation_configuration_drift"


def test_nonempty_validation_requires_v3_qdrant_and_embedding_identity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        RetrievalPartition.__table__,
        RetrievalProjectionEvent.__table__,
        RetrievalProjectionGeneration.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = _settings()
    backends = _FakeBackends()
    backends.opensearch = _inventory(resources=1)
    backends.qdrant = _inventory(resources=1, records=2)
    materializer = _FakeMaterializer(backends=backends, target_resources=1)
    judgment_sha256 = ["6" * 64]
    runner = FilesGenerationRunner(
        session_factory=factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(count=1),
        materializer=materializer,
        quality_judgment_validator=lambda _corpus: FilesQualityJudgmentSnapshot(
            acl_sha256=judgment_sha256[0],
            context_count=1,
            active_resource_count=1,
        ),
    )
    runner.prepare(
        generation_key="v3-quality",
        baseline_mode=FilesGenerationBaselineMode.ADOPT_PREPARED,
    )
    corpus_bytes = _quality_corpus_bytes()
    artifact = _passing_v3_quality_artifact(
        settings=settings,
        corpus_bytes=corpus_bytes,
    )

    result = runner.validate(
        generation_key="v3-quality",
        writes_quiesced=True,
        reconciliation_watermark=0,
        quality_artifact=artifact,
        quality_corpus_bytes=corpus_bytes,
    )

    assert result.state == "ready"
    with factory() as db:
        details = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())[0]
        assert details.validation_details["included_resource_types"] == [
            FILE_MANAGER_FILE_RESOURCE_TYPE
        ]
    assert details.validation_details["quality"]["artifact_version"] == 3

    with pytest.raises(FilesGenerationError) as missing_corpus:
        runner.cutover(
            generation_key="v3-quality",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )
    assert missing_corpus.value.code == "quality_corpus_required_for_cutover"
    assert backends.alias_operations == []

    judgment_sha256[0] = "7" * 64
    with pytest.raises(FilesGenerationError) as stale_acl:
        runner.cutover(
            generation_key="v3-quality",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
            quality_corpus_bytes=corpus_bytes,
        )
    assert stale_acl.value.code == "quality_judgment_acl_stale"
    assert backends.alias_operations == []
    judgment_sha256[0] = "6" * 64

    settings.rag_rerank_candidate_k = 40
    with pytest.raises(FilesGenerationError) as reranker_drift:
        runner._require_current_model_identities(details.validation_details)
    assert reranker_drift.value.code == "reranker_generation_configuration_drift"
    settings.rag_rerank_candidate_k = 20

    other_runner = FilesGenerationRunner(
        session_factory=factory,
        settings=settings,  # type: ignore[arg-type]
        backends=backends,
        source_snapshot_loader=lambda _db: _source_snapshot(count=1),
        materializer=materializer,
        quality_judgment_validator=lambda _corpus: FilesQualityJudgmentSnapshot(
            acl_sha256=judgment_sha256[0],
            context_count=1,
            active_resource_count=1,
        ),
    )
    changed_artifact = artifact.model_copy(update={"qdrant_content_sha256": "8" * 64})
    with pytest.raises(FilesGenerationError) as caught:
        other_runner._validate_quality(
            spec=other_runner._spec("v3-quality"),
            snapshot=_source_snapshot(count=1),
            inspection=backends.inspect_pair(None),
            quality_artifact=changed_artifact,
            quality_corpus_bytes=corpus_bytes,
            allow_empty_non_production=False,
        )
    assert caught.value.code == "quality_evidence_backend_mismatch"

    with factory.begin() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
        for row in rows:
            details = dict(row.validation_details or {})
            quality = dict(details.get("quality") or {})
            quality["qdrant_content_sha256"] = "8" * 64
            details["quality"] = quality
            row.validation_details = details
    with pytest.raises(FilesGenerationError) as tampered:
        runner.cutover(
            generation_key="v3-quality",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
            quality_corpus_bytes=corpus_bytes,
        )
    assert tampered.value.code == "stored_validation_quality_identity_mismatch"
    assert backends.alias_operations == []

    with factory.begin() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
        for row in rows:
            details = dict(row.validation_details or {})
            quality = dict(details.get("quality") or {})
            quality["qdrant_content_sha256"] = artifact.qdrant_content_sha256
            details["quality"] = quality
            row.validation_details = details

    original_set_alias = backends.set_alias

    def set_alias_then_change_acl(*, backend: str, alias_name: str, physical_name: str) -> None:
        original_set_alias(
            backend=backend,
            alias_name=alias_name,
            physical_name=physical_name,
        )
        if backend == "qdrant":
            judgment_sha256[0] = "7" * 64

    backends.set_alias = set_alias_then_change_acl  # type: ignore[method-assign]
    with pytest.raises(FilesGenerationError) as raced_acl:
        runner.cutover(
            generation_key="v3-quality",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
            quality_corpus_bytes=corpus_bytes,
        )
    assert raced_acl.value.code == "database_cutover_failed"
    assert backends.aliases == {}
    with factory() as db:
        states = set(db.scalars(select(RetrievalProjectionGeneration.state)).all())
    assert states == {"failed"}
    engine.dispose()


def test_initial_cutover_uses_dedicated_aliases_and_leaves_legacy_aliases_untouched(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    settings = _settings()
    legacy_opensearch_alias = keyword_search_index_alias(settings.opensearch_index_prefix)
    legacy_qdrant_alias = resolve_default_collection_name(settings)  # type: ignore[arg-type]
    backends.aliases[legacy_opensearch_alias] = "legacy-opensearch-v2"
    backends.aliases[legacy_qdrant_alias] = "legacy-qdrant"
    runner = _ready_empty_pair(
        generation_session_factory,
        backends,
        generation_key="first-active",
    )

    result = runner.cutover(
        generation_key="first-active",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )

    assert result.state == "active"
    assert backends.aliases[legacy_opensearch_alias] == "legacy-opensearch-v2"
    assert backends.aliases[legacy_qdrant_alias] == "legacy-qdrant"
    switched_aliases = {alias for _backend, alias, target in backends.alias_operations if target}
    assert legacy_opensearch_alias not in switched_aliases
    assert legacy_qdrant_alias not in switched_aliases


def test_alias_precondition_mismatch_never_overwrites_unknown_external_alias(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _ready_empty_pair(
        generation_session_factory,
        backends,
        generation_key="unknown-alias",
    )
    settings = _settings()
    opensearch_alias = keyword_search_partitioned_index_alias(settings.opensearch_index_prefix)
    qdrant_alias = resolve_partitioned_rag_collection_alias(settings)  # type: ignore[arg-type]
    backends.aliases[opensearch_alias] = "operator-owned-foreign-target"

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="unknown-alias",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "alias_precondition_mismatch"
    assert backends.aliases == {opensearch_alias: "operator-owned-foreign-target"}
    assert qdrant_alias not in backends.aliases
    assert backends.alias_operations == []
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.state for row in rows} == {"compensation_required"}


def test_cutover_rejects_changed_source_artifact_evidence(
    generation_session_factory: sessionmaker[Session],
) -> None:
    snapshot = [_source_snapshot()]
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=lambda _db: snapshot[0],
    )
    runner.prepare(
        generation_key="artifact-stale",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="artifact-stale",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_non_production=True,
    )
    snapshot[0] = replace(snapshot[0], artifact_sha256="9" * 64)

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="artifact-stale",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "stored_validation_stale"
    assert backends.alias_operations == []


def test_cutover_rejects_changed_source_acl_envelope_without_projection_event(
    generation_session_factory: sessionmaker[Session],
) -> None:
    snapshot = [_source_snapshot()]
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=lambda _db: snapshot[0],
    )
    runner.prepare(
        generation_key="acl-envelope-stale",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="acl-envelope-stale",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_non_production=True,
    )
    snapshot[0] = replace(snapshot[0], acl_envelope_sha256="9" * 64)

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="acl-envelope-stale",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "stored_validation_stale"
    assert backends.alias_operations == []


def test_active_verification_fails_for_missing_alias_and_configuration_drift(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    runner = _ready_empty_pair(
        generation_session_factory,
        backends,
        generation_key="verify-active",
    )
    runner.cutover(
        generation_key="verify-active",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    qdrant_alias = resolve_partitioned_rag_collection_alias(_settings())  # type: ignore[arg-type]
    qdrant_target = backends.aliases.pop(qdrant_alias)

    with pytest.raises(FilesGenerationError) as missing_alias:
        runner.verify_active()
    assert missing_alias.value.code == "active_alias_mismatch"

    backends.aliases[qdrant_alias] = qdrant_target
    with generation_session_factory.begin() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
        for row in rows:
            row.config_checksum = "5" * 64
    with pytest.raises(FilesGenerationError) as stale_evidence:
        runner.verify_active()
    assert stale_evidence.value.code == "active_generation_configuration_drift"


def test_active_verification_reconciles_current_source_projection_content(
    generation_session_factory: sessionmaker[Session],
) -> None:
    snapshot = replace(
        _source_snapshot(),
        qdrant_record_count=0,
        opensearch_projection_sha256=_EMPTY_SHA256,
        qdrant_projection_sha256=_EMPTY_SHA256,
    )
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        snapshot=snapshot,
    )
    runner.prepare(
        generation_key="active-content-reconciliation",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    assert backends.opensearch is not None and backends.qdrant is not None
    backends.opensearch = replace(
        backends.opensearch,
        projection_sha256=_EMPTY_SHA256,
    )
    backends.qdrant = replace(
        backends.qdrant,
        projection_sha256=_EMPTY_SHA256,
    )
    runner.validate(
        generation_key="active-content-reconciliation",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_non_production=True,
    )
    runner.cutover(
        generation_key="active-content-reconciliation",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    backends.opensearch = replace(
        backends.opensearch,
        projection_sha256="9" * 64,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.verify_active()

    assert caught.value.code == "opensearch_projection_content_mismatch"


def test_active_verification_allows_later_files_watermark_when_current_heads_are_reconciled(
    generation_session_factory: sessionmaker[Session],
) -> None:
    files_watermark = _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="deleted-before-activation",
    )
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=_scoped_empty_source_snapshot,
    )
    runner.prepare(
        generation_key="active-writes-continue",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="active-writes-continue",
        writes_quiesced=True,
        reconciliation_watermark=files_watermark,
        allow_empty_non_production=True,
    )
    runner.cutover(
        generation_key="active-writes-continue",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="deleted-after-activation",
    )

    status = runner.verify_active()

    assert status.deployment_enabled is False
    assert status.ready is False


def test_subsequent_generation_cutover_is_blocked_until_rollback_command_exists(
    generation_session_factory: sessionmaker[Session],
) -> None:
    backends = _FakeBackends()
    first = _ready_empty_pair(
        generation_session_factory,
        backends,
        generation_key="initial-only",
    )
    first.cutover(
        generation_key="initial-only",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )
    operations_after_initial = list(backends.alias_operations)

    second = _runner(generation_session_factory, backends)
    second.prepare(
        generation_key="future-upgrade",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    second.validate(
        generation_key="future-upgrade",
        writes_quiesced=True,
        reconciliation_watermark=0,
        allow_empty_non_production=True,
    )

    with pytest.raises(FilesGenerationError) as caught:
        second.cutover(
            generation_key="future-upgrade",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "generation_upgrade_rollback_unsupported"
    assert backends.alias_operations == operations_after_initial
    with generation_session_factory() as db:
        states = {
            row.generation_key: row.state
            for row in db.scalars(select(RetrievalProjectionGeneration)).all()
        }
    assert states["initial-only"] == "active"
    assert states["future-upgrade"] == "ready"


def test_unrelated_events_neither_advance_files_checkpoint_nor_block_cutover(
    generation_session_factory: sessionmaker[Session],
) -> None:
    _append_projection_event(
        generation_session_factory,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id="doc-before",
    )
    files_watermark = _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-deleted",
    )
    _append_projection_event(
        generation_session_factory,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id="doc-before-validation",
    )
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=_scoped_empty_source_snapshot,
    )

    runner.prepare(
        generation_key="files-scoped-watermark",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="files-scoped-watermark",
        writes_quiesced=True,
        reconciliation_watermark=files_watermark,
        allow_empty_non_production=True,
    )
    _append_projection_event(
        generation_session_factory,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id="doc-after-validation",
    )

    result = runner.cutover(
        generation_key="files-scoped-watermark",
        writes_quiesced=True,
        rollback_window=timedelta(days=7),
    )

    assert result.state == "active"
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.baseline_event_sequence for row in rows} == {files_watermark}
    assert {row.replay_event_sequence for row in rows} == {files_watermark}


def test_new_files_event_after_validation_blocks_cutover_before_alias_switch(
    generation_session_factory: sessionmaker[Session],
) -> None:
    files_watermark = _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-before-validation",
    )
    backends = _FakeBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=_scoped_empty_source_snapshot,
    )
    runner.prepare(
        generation_key="files-watermark-stale",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="files-watermark-stale",
        writes_quiesced=True,
        reconciliation_watermark=files_watermark,
        allow_empty_non_production=True,
    )
    _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-after-validation",
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="files-watermark-stale",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "stored_validation_stale"
    assert backends.alias_operations == []


def test_new_files_event_during_alias_switch_restores_aliases_and_compensates_pair(
    generation_session_factory: sessionmaker[Session],
) -> None:
    files_watermark = _append_projection_event(
        generation_session_factory,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-before-cutover",
    )

    class EventInjectingBackends(_FakeBackends):
        injected = False

        def set_alias(
            self,
            *,
            backend: str,
            alias_name: str,
            physical_name: str,
        ) -> None:
            super().set_alias(
                backend=backend,
                alias_name=alias_name,
                physical_name=physical_name,
            )
            if not self.injected:
                self.injected = True
                _append_projection_event(
                    generation_session_factory,
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id="file-during-cutover",
                )

    backends = EventInjectingBackends()
    runner = _runner(
        generation_session_factory,
        backends,
        source_snapshot_loader=_scoped_empty_source_snapshot,
    )
    runner.prepare(
        generation_key="files-cutover-race",
        baseline_mode=FilesGenerationBaselineMode.EMPTY,
    )
    runner.validate(
        generation_key="files-cutover-race",
        writes_quiesced=True,
        reconciliation_watermark=files_watermark,
        allow_empty_non_production=True,
    )

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="files-cutover-race",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "database_cutover_failed"
    assert backends.aliases == {}
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.state for row in rows} == {"failed"}


@pytest.mark.parametrize("fail_after_move", [False, True])
def test_partial_alias_failure_restores_both_aliases_and_compensates_database_pair(
    generation_session_factory: sessionmaker[Session],
    fail_after_move: bool,
) -> None:
    backends = _FakeBackends()
    runner = _ready_empty_pair(
        generation_session_factory,
        backends,
        generation_key="partial-alias",
    )
    backends.fail_alias_backend = "qdrant"
    backends.fail_after_move = fail_after_move

    with pytest.raises(FilesGenerationError) as caught:
        runner.cutover(
            generation_key="partial-alias",
            writes_quiesced=True,
            rollback_window=timedelta(days=7),
        )

    assert caught.value.code == "alias_cutover_failed"
    assert "secret" not in str(caught.value)
    assert backends.aliases == {}
    with generation_session_factory() as db:
        rows = tuple(db.scalars(select(RetrievalProjectionGeneration)).all())
    assert {row.state for row in rows} == {"failed"}
    assert {row.failure_reason for row in rows} == {"external_alias_switch_failed"}


def test_physical_backend_refuses_the_shared_legacy_alias_before_network_access() -> None:
    settings = _settings()
    backends = FilesPhysicalGenerationBackends(
        settings,  # type: ignore[arg-type]
        qdrant_client=object(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="dedicated"):
        backends.set_alias(
            backend="opensearch",
            alias_name=keyword_search_index_alias(settings.opensearch_index_prefix),
            physical_name="test_keyword_search_documents_v3_release",
        )


def test_physical_backend_counts_resource_presence_in_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Qdrant:
        def collection_exists(self, *, collection_name: str) -> bool:
            assert collection_name == "test-rag-fake-v1-release"
            return True

        def count(self, **kwargs) -> object:
            match = kwargs["count_filter"].must[1].match
            return SimpleNamespace(count=len(match.any))

    class Response:
        def __init__(self, count: int) -> None:
            self._count = count

        def json(self) -> dict[str, int]:
            return {"count": self._count}

    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=Qdrant(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        backends,
        "_require_physical_names_not_aliases",
        lambda _spec: None,
    )
    monkeypatch.setattr(
        backends,
        "_opensearch_client",
        lambda _name: SimpleNamespace(index_exists=lambda: True),
    )

    def request(_method: str, _path: str, **kwargs: object) -> Response:
        terms = kwargs["json"]["query"]["bool"]["filter"][1]["terms"]["entity_id"]  # type: ignore[index]
        assert len(terms) <= 100
        return Response(len(terms))

    monkeypatch.setattr(backends, "_opensearch_request", request)
    resource_ids = [f"file-{index}" for index in range(205)]

    presence = backends.count_resource_presence(
        FilesGenerationPairSpec(
            generation_key="release",
            opensearch_physical_name="test_keyword_search_documents_v3_release",
            opensearch_alias_name="test_keyword_search_documents_v3",
            qdrant_physical_name="test-rag-fake-v1-release",
            qdrant_alias_name="test-rag-fake-v1",
        ),
        resource_ids=resource_ids,
    )

    assert presence.opensearch_documents == 205
    assert presence.qdrant_points == 205


@pytest.mark.parametrize("alias_backend", ["opensearch", "qdrant"])
def test_physical_inventory_rejects_aliases_disguised_as_generation_names(
    monkeypatch: pytest.MonkeyPatch,
    alias_backend: str,
) -> None:
    physical_opensearch = "test_keyword_search_documents_v3_release"
    physical_qdrant = "test-rag-fake-v1-release"

    class Response:
        status_code = 200 if alias_backend == "opensearch" else 404

    qdrant = SimpleNamespace(
        get_aliases=lambda: SimpleNamespace(
            aliases=(
                [SimpleNamespace(alias_name=physical_qdrant)] if alias_backend == "qdrant" else []
            )
        )
    )
    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(backends, "_opensearch_request", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        backends,
        "_inspect_opensearch",
        lambda _spec: pytest.fail("alias must be rejected before inventory"),
    )
    monkeypatch.setattr(
        backends,
        "_inspect_qdrant",
        lambda _spec: pytest.fail("alias must be rejected before inventory"),
    )

    with pytest.raises(RuntimeError, match="alias"):
        backends.inspect_pair(
            SimpleNamespace(
                opensearch_physical_name=physical_opensearch,
                qdrant_physical_name=physical_qdrant,
            )
        )


def test_opensearch_inventory_rejects_noncanonical_document_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=object(),  # type: ignore[arg-type]
    )
    source = {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "entity_type": "file",
        "entity_id": "file-1",
        "retrieval_partition_id": _PARTITION_ID,
        "projection_version": 1,
    }

    class Response:
        def __init__(self, document_id: str) -> None:
            self.document_id = document_id

        def json(self) -> dict[str, object]:
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": self.document_id,
                            "_source": source,
                            "sort": [FILE_MANAGER_FILE_RESOURCE_TYPE, "file-1"],
                        }
                    ]
                }
            }

    expected = canonical_search_document_id(
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-1",
    )
    monkeypatch.setattr(
        backends, "_opensearch_request", lambda *_args, **_kwargs: Response(expected)
    )
    assert backends._opensearch_projection_identities("physical") == {("file-1", _PARTITION_ID, 1)}

    monkeypatch.setattr(
        backends,
        "_opensearch_request",
        lambda *_args, **_kwargs: Response("workspace:file:file-1"),
    )
    with pytest.raises(RuntimeError, match="document identity is not canonical"):
        backends._opensearch_projection_identities("physical")


def test_opensearch_inventory_contract_detects_document_content_checksum_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=object(),  # type: ignore[arg-type]
    )
    source: dict[str, object] = {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "entity_type": "file",
        "entity_id": "file-1",
        "retrieval_partition_id": _PARTITION_ID,
        "projection_version": 1,
        "body": "stable extracted body",
        "metadata": {"content_checksum": "a" * 64},
    }
    document_id = canonical_search_document_id(
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id="file-1",
    )

    class Response:
        def json(self) -> dict[str, object]:
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": document_id,
                            "_source": source,
                            "sort": [FILE_MANAGER_FILE_RESOURCE_TYPE, "file-1"],
                        }
                    ]
                }
            }

    client = SimpleNamespace(
        index_exists=lambda: True,
        count_documents=lambda: 1,
        quality_identity=lambda: ("index-uuid", "4" * 64),
        content_sha256=lambda: "3" * 64,
    )
    monkeypatch.setattr(backends, "_opensearch_client", lambda _name: client)
    monkeypatch.setattr(backends, "_opensearch_request", lambda *_args, **_kwargs: Response())
    spec = SimpleNamespace(opensearch_physical_name="physical")

    before = backends._inspect_opensearch(spec)  # type: ignore[arg-type]
    source["metadata"] = {"content_checksum": "b" * 64}
    after = backends._inspect_opensearch(spec)  # type: ignore[arg-type]

    assert before is not None and after is not None
    assert before.projection_sha256 is not None
    assert after.projection_sha256 != before.projection_sha256


def test_qdrant_inventory_rejects_noncanonical_point_uuid() -> None:
    payload = {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "resource_id": "file-1",
        "source_kind": "files",
        "chunk_id": "chunk-1",
        "retrieval_partition_id": _PARTITION_ID,
        "projection_version": 1,
    }

    class QdrantInventoryClient:
        point_id = canonical_vector_point_id(
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-1",
            chunk_id="chunk-1",
        )

        def collection_exists(self, *, collection_name: str) -> bool:
            del collection_name
            return True

        def get_collection(self, *, collection_name: str) -> object:
            del collection_name
            return SimpleNamespace(
                config=SimpleNamespace(params={}),
                payload_schema={},
            )

        def count(self, **_kwargs) -> object:
            return SimpleNamespace(count=1)

        def scroll(self, **_kwargs) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        id=self.point_id,
                        payload=payload,
                        vector={"dense": [0.1]},
                    )
                ],
                None,
            )

    qdrant = QdrantInventoryClient()
    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )
    spec = SimpleNamespace(qdrant_physical_name="test-rag-fake-v1-release")
    assert backends._inspect_qdrant(spec).resource_count == 1  # type: ignore[arg-type,union-attr]

    qdrant.point_id = "90b4df62-4e18-4d0a-9fb9-17138fbf78b9"
    with pytest.raises(RuntimeError, match="point identity is not canonical"):
        backends._inspect_qdrant(spec)  # type: ignore[arg-type]


def test_qdrant_config_identity_ignores_dynamic_payload_index_point_counts() -> None:
    payload = {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "resource_id": "file-1",
        "source_kind": "files",
        "chunk_id": "chunk-1",
        "retrieval_partition_id": _PARTITION_ID,
        "projection_version": 1,
    }

    class QdrantInventoryClient:
        indexed_points = 1
        payload_type = "keyword"

        def collection_exists(self, *, collection_name: str) -> bool:
            del collection_name
            return True

        def get_collection(self, *, collection_name: str) -> object:
            del collection_name
            return SimpleNamespace(
                config=SimpleNamespace(params={"vectors": {"size": 1}}),
                payload_schema={
                    "retrieval_partition_id": {
                        "data_type": self.payload_type,
                        "params": {"is_tenant": True},
                        "points": self.indexed_points,
                    }
                },
            )

        def count(self, **_kwargs) -> object:
            return SimpleNamespace(count=1)

        def scroll(self, **_kwargs) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        id=canonical_vector_point_id(
                            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                            resource_id="file-1",
                            chunk_id="chunk-1",
                        ),
                        payload=payload,
                        vector={"dense": [0.1]},
                    )
                ],
                None,
            )

    qdrant = QdrantInventoryClient()
    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )
    spec = SimpleNamespace(qdrant_physical_name="test-rag-fake-v1-release")

    first = backends._inspect_qdrant(spec)  # type: ignore[arg-type]
    qdrant.indexed_points = 2
    second = backends._inspect_qdrant(spec)  # type: ignore[arg-type]
    assert first is not None and second is not None
    assert second.config_sha256 == first.config_sha256

    qdrant.payload_type = "integer"
    changed = backends._inspect_qdrant(spec)  # type: ignore[arg-type]
    assert changed is not None
    assert changed.config_sha256 != first.config_sha256


def test_qdrant_inventory_contract_detects_payload_checksum_drift_without_reembedding() -> None:
    payload = {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "resource_id": "file-1",
        "source_kind": "files",
        "chunk_id": "chunk-1",
        "retrieval_partition_id": _PARTITION_ID,
        "projection_version": 1,
        "metadata": {"content_checksum": "a" * 64},
    }
    dense_vector = [0.1]

    class QdrantInventoryClient:
        def collection_exists(self, *, collection_name: str) -> bool:
            del collection_name
            return True

        def get_collection(self, *, collection_name: str) -> object:
            del collection_name
            return SimpleNamespace(config=SimpleNamespace(params={}), payload_schema={})

        def count(self, **_kwargs) -> object:
            return SimpleNamespace(count=1)

        def scroll(self, **_kwargs) -> tuple[list[object], None]:
            return (
                [
                    SimpleNamespace(
                        id=canonical_vector_point_id(
                            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                            resource_id="file-1",
                            chunk_id="chunk-1",
                        ),
                        payload=payload,
                        vector={"dense": dense_vector},
                    )
                ],
                None,
            )

    backends = FilesPhysicalGenerationBackends(
        _settings(),  # type: ignore[arg-type]
        qdrant_client=QdrantInventoryClient(),  # type: ignore[arg-type]
    )
    spec = SimpleNamespace(qdrant_physical_name="test-rag-fake-v1-release")

    before = backends._inspect_qdrant(spec)  # type: ignore[arg-type]
    payload["metadata"] = {"content_checksum": "b" * 64}
    payload_changed = backends._inspect_qdrant(spec)  # type: ignore[arg-type]
    payload["metadata"] = {"content_checksum": "a" * 64}
    dense_vector[0] = 0.2
    vector_changed = backends._inspect_qdrant(spec)  # type: ignore[arg-type]

    assert before is not None and payload_changed is not None and vector_changed is not None
    assert before.projection_sha256 is not None
    assert payload_changed.projection_sha256 != before.projection_sha256
    assert vector_changed.projection_sha256 == before.projection_sha256
    assert vector_changed.content_sha256 != before.content_sha256


def test_cli_requires_exact_generation_confirmation_before_production_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    monkeypatch.setattr(script, "get_settings", lambda: _settings(environment="production"))
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: pytest.fail("production confirmation must precede backend access"),
    )

    exit_code = script.main(
        [
            "prepare",
            "--generation",
            "release-safe",
            "--baseline-mode",
            "adopt-prepared",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == "status=failed reason=production_confirmation_required"


def test_cli_requires_exact_empty_production_bootstrap_confirmation_before_backend_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    monkeypatch.setattr(script, "get_settings", lambda: _settings(environment="production"))
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: pytest.fail("empty bootstrap confirmation must precede backend access"),
    )

    exit_code = script.main(
        [
            "validate",
            "--generation",
            "release-empty",
            "--confirm-production-generation",
            "release-empty",
            "--confirm-writes-quiesced",
            "--reconciliation-watermark",
            "0",
            "--confirm-empty-production-bootstrap",
            "wrong-confirmation",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        captured.err.strip()
        == "status=failed reason=empty_production_bootstrap_confirmation_required"
    )


def test_cli_requires_exact_active_attestation_confirmation_before_backend_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    monkeypatch.setattr(script, "get_settings", lambda: _settings(environment="production"))
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: pytest.fail("attestation confirmation must precede backend access"),
    )

    exit_code = script.main(
        [
            "attest-active",
            "--generation",
            "prod-empty-20260723",
            "--confirm-writes-quiesced",
            "--quality-report",
            "/not/read-before-confirmation/report.json",
            "--quality-corpus",
            "/not/read-before-confirmation/corpus.json",
            "--scope-coverage",
            "company",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == "status=failed reason=production_confirmation_required"


def test_cli_sanitizes_unexpected_backend_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    secret = "qdrant-api-key-secret"
    monkeypatch.setattr(script, "get_settings", _settings)
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    exit_code = script.main(
        [
            "prepare",
            "--generation",
            "safe-error",
            "--baseline-mode",
            "empty",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == "status=failed reason=files_generation_operation_failed"
    assert secret not in captured.err


def test_non_active_materializer_resolves_matching_paused_jobs_after_both_backend_writes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        RetrievalPartition.__table__,
        RetrievalProjectionEvent.__table__,
        RetrievalProjectionHead.__table__,
        SearchIndexJob.__table__,
        RagSyncJob.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    partition_id = "eb7d34b8-ae95-4b3e-85bd-08ee02e99f5d"
    with factory.begin() as db:
        db.add(
            RetrievalPartition(
                id=partition_id,
                source_namespace="files",
                candidate_scope_kind="company",
                is_default_ingest=True,
            )
        )
        db.add(
            RetrievalProjectionEvent(
                event_sequence=1,
                resource_type="file_manager_file",
                resource_id="deleted-file",
                projection_version=1,
                retrieval_partition_id=partition_id,
                change_kind="delete",
                desired_state="deleted",
            )
        )
        db.add(
            RetrievalProjectionHead(
                resource_type="file_manager_file",
                resource_id="deleted-file",
                projection_version=1,
                retrieval_partition_id=partition_id,
                desired_state="deleted",
            )
        )
        db.add(
            SearchIndexJob(
                id="search-job",
                retrieval_partition_id=partition_id,
                resource_type="file_manager_file",
                projection_event_sequence=1,
                projection_version=1,
                desired_state="deleted",
                entity_type="file",
                entity_id="deleted-file",
                operation="delete",
                status="pending",
            )
        )
        db.add(
            RagSyncJob(
                id="rag-job",
                scope_kind="company",
                retrieval_partition_id=partition_id,
                projection_event_sequence=1,
                projection_version=1,
                desired_state="deleted",
                lane="realtime",
                resource_type="file_manager_file",
                resource_id="deleted-file",
                operation="delete",
                status="pending",
            )
        )

    class KeywordClient:
        calls = 0
        refresh_calls = 0

        def upsert_partitioned_document(self, _document: dict[str, Any]) -> str:
            raise AssertionError("the delete fixture must not upsert a keyword document")

        def delete_partitioned_document(self, **_kwargs) -> str:
            self.calls += 1
            return "deleted"

        def refresh_partitioned_index(self) -> None:
            self.refresh_calls += 1

    class RagService:
        calls = 0
        fail = True

        def delete_projection(self, **_kwargs) -> None:
            self.calls += 1
            if self.fail:
                raise RuntimeError("vector write failed")

    keyword = KeywordClient()
    rag = RagService()
    materializer = FilesCachedProjectionMaterializer(
        session_factory=factory,
        settings=_settings(),  # type: ignore[arg-type]
        keyword_client_factory=lambda _physical: keyword,  # type: ignore[arg-type]
        rag_service_factory=lambda _collection: rag,  # type: ignore[arg-type]
    )
    spec = SimpleNamespace(
        opensearch_physical_name="test_keyword_search_documents_v3_jobs",
        qdrant_physical_name="test-rag-fake-v1-jobs",
    )

    with pytest.raises(RuntimeError, match="vector write failed"):
        materializer.materialize_batch(
            spec=spec,  # type: ignore[arg-type]
            after_event_sequence=0,
            through_event_sequence=1,
            limit=100,
        )
    with factory() as db:
        assert db.get(SearchIndexJob, "search-job").status == "pending"
        assert db.get(RagSyncJob, "rag-job").status == "pending"

    rag.fail = False
    batch = materializer.materialize_batch(
        spec=spec,  # type: ignore[arg-type]
        after_event_sequence=0,
        through_event_sequence=1,
        limit=100,
    )

    assert batch.caught_up is True
    assert batch.keyword_remaining == 0
    assert batch.vector_remaining == 0
    assert keyword.calls == 2
    assert keyword.refresh_calls == 1
    assert rag.calls == 2
    with factory() as db:
        assert db.get(SearchIndexJob, "search-job").status == "succeeded"
        assert db.get(RagSyncJob, "rag-job").status == "succeeded"
    engine.dispose()


def test_generation_cli_rejects_removed_workspace_scope_before_backend_access(monkeypatch):
    script = _load_runner_script()
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: pytest.fail("removed scope must not access backends"),
    )
    with pytest.raises(SystemExit) as error:
        script.main(
            ["attest-active", "--generation", "company-release", "--scope-coverage", "workspace"]
        )
    assert error.value.code == 2
