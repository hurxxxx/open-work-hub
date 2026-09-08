from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import SimpleNamespace
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.settings import is_production_environment
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.document_processing import EvidenceBlock
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileSourceMetadata,
)
from open_work_hub_api.domains.files.rag_projection import (
    FileExtractionArtifact,
    build_file_rag_projection,
)
from open_work_hub_api.domains.files.search_projection import build_file_search_document
from open_work_hub_api.domains.rag.contracts import RagVectorRecord
from open_work_hub_api.domains.rag.providers.qdrant import qdrant_payload_from_record
from open_work_hub_api.domains.rag.runtime import (
    PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
    resolve_default_collection_name,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_work_hub_api.domains.retrieval.evaluation import (
    RetrievalQualityCorpus,
    RetrievalQualityGateArtifact,
    retrieval_embedding_generation_identity,
    retrieval_quality_corpus_sha256,
    retrieval_reranker_generation_identity,
    validate_quality_gate_artifact,
)
from open_work_hub_api.domains.retrieval.files_cutover import (
    FilesRetrievalCutoverStatus,
    check_files_retrieval_cutover,
)
from open_work_hub_api.domains.retrieval.files_quality_judgments import (
    FilesQualityJudgmentError,
    FilesQualityJudgmentSnapshot,
    validate_files_quality_judgments,
)
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalPartitionState,
    RetrievalProjectionBackend,
    RetrievalProjectionDesiredState,
    RetrievalProjectionEvent,
    RetrievalProjectionGeneration,
    RetrievalProjectionGenerationAttestation,
    RetrievalProjectionGenerationState,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_generations import (
    RetrievalProjectionGenerationCutoverTarget,
    RetrievalProjectionGenerationPairCutoverPlan,
    advance_generation_replay_checkpoint,
    compensate_generation_pair_cutover,
    complete_generation_pair_cutover,
    create_projection_generation,
    mark_generation_baselining,
    mark_generation_replaying,
    mark_generation_validating,
    prepare_generation_pair_cutover,
    record_generation_validation,
)
from open_work_hub_api.domains.retrieval.projection_identity import (
    canonical_search_document_id,
    canonical_vector_point_id,
)
from open_work_hub_api.domains.search.index_gateway import (
    RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
    keyword_search_index_alias,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
)
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_OPENSEARCH_MUTABLE_ACL_FIELDS = frozenset(
    {
        "id",
        "visibility",
        "deep_link",
        "source_updated_at",
        "created_at",
    }
)
_QDRANT_MUTABLE_ACL_FIELDS = frozenset({"scope_kind", "visibility_refs"})
_QDRANT_MUTABLE_ACL_METADATA_FIELDS = frozenset(
    {"origin_ref", "visibility", "access_scope_kind"}
)


class ProjectionContractDigest:
    """Streaming order-independent digest for source-derived projection records."""

    _MODULUS = 1 << 256

    def __init__(self) -> None:
        self._count = 0
        self._sum = 0
        self._xor = 0

    def add(self, value: bytes) -> None:
        item = int.from_bytes(hashlib.sha256(value).digest(), "big")
        self._count += 1
        self._sum = (self._sum + item) % self._MODULUS
        self._xor ^= item

    def hexdigest(self) -> str:
        if self._count == 0:
            return _EMPTY_SHA256
        canonical = (
            self._count.to_bytes(8, "big")
            + self._sum.to_bytes(32, "big")
            + self._xor.to_bytes(32, "big")
        )
        return hashlib.sha256(canonical).hexdigest()


def opensearch_projection_contract_bytes(
    *,
    document_id: str,
    document: dict[str, object],
) -> bytes:
    """Canonicalize stable Files content while excluding hydrated ACL routing hints."""

    stable_document = {
        key: value for key, value in document.items() if key not in _OPENSEARCH_MUTABLE_ACL_FIELDS
    }
    return _canonical_json_bytes({"id": document_id, "document": stable_document})


def qdrant_projection_contract_bytes(
    *,
    point_id: str,
    payload: dict[str, object],
) -> bytes:
    """Canonicalize chunk identity/content without vectors or mutable ACL hints."""

    stable_payload = {
        key: value for key, value in payload.items() if key not in _QDRANT_MUTABLE_ACL_FIELDS
    }
    raw_metadata = stable_payload.get("metadata")
    if isinstance(raw_metadata, dict):
        stable_payload["metadata"] = {
            str(key): value
            for key, value in raw_metadata.items()
            if str(key) not in _QDRANT_MUTABLE_ACL_METADATA_FIELDS
        }
    return _canonical_json_bytes({"id": point_id, "payload": stable_payload})


class FilesGenerationError(RuntimeError):
    """A stable, non-sensitive operator failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class FilesGenerationBaselineMode(StrEnum):
    EMPTY = "empty"
    ADOPT_PREPARED = "adopt-prepared"
    CACHED_ARTIFACTS = "cached-artifacts"


class FilesGenerationRuntimeSettings(Protocol):
    environment: str
    opensearch_url: str
    opensearch_index_prefix: str
    keyword_search_backend: str
    rag_vector_index_provider: str
    rag_qdrant_url: str
    rag_qdrant_api_key: str
    rag_qdrant_collection_prefix: str
    rag_embedding_provider: str
    files_retrieval_enabled: bool


@dataclass(frozen=True, slots=True)
class FilesGenerationPairSpec:
    generation_key: str
    opensearch_physical_name: str
    opensearch_alias_name: str
    qdrant_physical_name: str
    qdrant_alias_name: str


@dataclass(frozen=True, slots=True)
class FilesSourceProjectionSnapshot:
    event_watermark: int
    files_event_watermark: int
    resource_count: int
    identity_sha256: str
    artifact_sha256: str
    unsupported_count: int
    unavailable_count: int
    acl_envelope_sha256: str = _EMPTY_SHA256
    qdrant_record_count: int | None = None
    opensearch_projection_sha256: str | None = None
    qdrant_projection_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class FilesPhysicalProjectionInventory:
    resource_count: int
    record_count: int
    identity_sha256: str
    content_sha256: str
    config_sha256: str
    physical_id: str
    projection_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class FilesBackendPairInspection:
    opensearch: FilesPhysicalProjectionInventory | None
    qdrant: FilesPhysicalProjectionInventory | None


@dataclass(frozen=True, slots=True)
class FilesGenerationRunResult:
    generation_key: str
    state: str
    dry_run: bool
    source_resource_count: int
    unsupported_source_count: int
    next_event_sequence: int | None = None
    complete: bool | None = None

    def status_line(self) -> str:
        status = (
            f"status=ok generation={self.generation_key} state={self.state}"
            f" dry_run={int(self.dry_run)}"
            f" source_resources={self.source_resource_count}"
            f" unsupported_sources={self.unsupported_source_count}"
        )
        if self.next_event_sequence is not None:
            status += f" next_event_sequence={self.next_event_sequence}"
        if self.complete is not None:
            status += f" complete={int(self.complete)}"
        return status


@dataclass(frozen=True, slots=True)
class FilesGenerationMaterializationBatch:
    target_event_sequence: int
    next_event_sequence: int
    scanned_events: int
    keyword_succeeded: int
    vector_succeeded: int
    complete: bool
    caught_up: bool
    keyword_remaining: int
    vector_remaining: int


class FilesGenerationBackends(Protocol):
    def inspect_pair(self, spec: FilesGenerationPairSpec) -> FilesBackendPairInspection: ...

    def prepare_empty_pair(self, spec: FilesGenerationPairSpec) -> None: ...

    def alias_target(self, *, backend: str, alias_name: str) -> str | None: ...

    def set_alias(self, *, backend: str, alias_name: str, physical_name: str) -> None: ...

    def remove_alias(self, *, backend: str, alias_name: str) -> None: ...


class FilesGenerationMaterializer(Protocol):
    def materialize_batch(
        self,
        *,
        spec: FilesGenerationPairSpec,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
    ) -> FilesGenerationMaterializationBatch: ...

    def inspect_reconciliation(self, *, through_event_sequence: int) -> object: ...


SourceSnapshotLoader = Callable[[Session], FilesSourceProjectionSnapshot]
QualityJudgmentValidator = Callable[[RetrievalQualityCorpus], FilesQualityJudgmentSnapshot]
ActiveReleaseProbe = Callable[[Session], FilesRetrievalCutoverStatus]


class FilesGenerationRunner:
    """Prepare, validate, and atomically expose one Files retrieval generation pair.

    The runner deliberately keeps external operations outside PostgreSQL
    transactions. PostgreSQL ``activating`` is committed first, aliases are then
    switched independently, and the pair control plane is completed or
    compensated in a new transaction.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: FilesGenerationRuntimeSettings,
        backends: FilesGenerationBackends,
        source_snapshot_loader: SourceSnapshotLoader | None = None,
        active_release_probe: ActiveReleaseProbe | None = None,
        materializer: FilesGenerationMaterializer | None = None,
        quality_judgment_validator: QualityJudgmentValidator | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._backends = backends
        self._source_snapshot_loader = source_snapshot_loader or load_files_source_snapshot
        self._active_release_probe = active_release_probe or (
            lambda db: check_files_retrieval_cutover(db, settings=self._settings)  # type: ignore[arg-type]
        )
        self._materializer = materializer
        self._quality_judgment_validator = quality_judgment_validator or (
            lambda corpus: validate_files_quality_judgments(
                corpus=corpus,
                session_factory=self._session_factory,
            )
        )

    def prepare(
        self,
        *,
        generation_key: str,
        baseline_mode: FilesGenerationBaselineMode,
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        spec = self._spec(generation_key)
        snapshot = self._source_snapshot()
        self._require_available_source(snapshot)
        if baseline_mode is FilesGenerationBaselineMode.EMPTY and snapshot.resource_count != 0:
            raise FilesGenerationError("empty_baseline_requires_empty_source")

        pair = self._read_pair(spec.generation_key)
        if pair is None and dry_run:
            inspection = self._safe_inspect(spec)
            if baseline_mode is FilesGenerationBaselineMode.ADOPT_PREPARED:
                self._require_complete_inspection(inspection)
                self._reconcile(snapshot, inspection)
            return self._result(spec, snapshot=snapshot, state="planned", dry_run=True)

        if pair is None:
            self._register_pair(
                spec,
                baseline_event_sequence=snapshot.files_event_watermark,
            )
            pair = self._required_pair(spec.generation_key)
        self._require_registered_pair_matches_spec(pair, spec)
        state = self._paired_state(pair)

        if state in {
            RetrievalProjectionGenerationState.BASELINING.value,
            RetrievalProjectionGenerationState.REPLAYING.value,
            RetrievalProjectionGenerationState.VALIDATING.value,
            RetrievalProjectionGenerationState.READY.value,
            RetrievalProjectionGenerationState.ACTIVE.value,
        }:
            inspection = self._require_complete_inspection(self._safe_inspect(spec))
            if state != RetrievalProjectionGenerationState.BASELINING.value:
                self._reconcile(snapshot, inspection)
            return self._result(spec, snapshot=snapshot, state=state, dry_run=dry_run)
        if state != RetrievalProjectionGenerationState.PREPARING.value:
            raise FilesGenerationError("generation_not_preparable")

        inspection = self._safe_inspect(spec)
        if inspection.opensearch is None or inspection.qdrant is None:
            if baseline_mode is FilesGenerationBaselineMode.ADOPT_PREPARED:
                code = (
                    "partial_physical_generation"
                    if inspection.opensearch is not None or inspection.qdrant is not None
                    else "prepared_baseline_missing"
                )
                raise FilesGenerationError(code)
            if dry_run:
                return self._result(spec, snapshot=snapshot, state="planned", dry_run=True)
            try:
                self._backends.prepare_empty_pair(spec)
            except Exception as error:
                raise FilesGenerationError("physical_generation_prepare_failed") from error
            inspection = self._require_complete_inspection(self._safe_inspect(spec))

        if baseline_mode is not FilesGenerationBaselineMode.CACHED_ARTIFACTS:
            self._reconcile(snapshot, inspection)
        if dry_run:
            return self._result(spec, snapshot=snapshot, state="planned", dry_run=True)

        try:
            with self._session_factory.begin() as db:
                current = self._load_pair(db, spec.generation_key)
                self._require_registered_pair_matches_spec(current, spec)
                if (
                    self._paired_state(current)
                    == RetrievalProjectionGenerationState.PREPARING.value
                ):
                    for generation in current:
                        mark_generation_baselining(db, generation_id=generation.id)
                    if baseline_mode is not FilesGenerationBaselineMode.CACHED_ARTIFACTS:
                        for generation in current:
                            mark_generation_replaying(
                                db,
                                generation_id=generation.id,
                                expected_projection_count=snapshot.resource_count,
                            )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("generation_baseline_state_failed") from error
        result_state = (
            RetrievalProjectionGenerationState.BASELINING.value
            if baseline_mode is FilesGenerationBaselineMode.CACHED_ARTIFACTS
            else RetrievalProjectionGenerationState.REPLAYING.value
        )
        return self._result(
            spec,
            snapshot=snapshot,
            state=result_state,
            dry_run=False,
        )

    def materialize(
        self,
        *,
        generation_key: str,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
        writes_quiesced: bool,
        workers_stopped: bool,
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        return self._materialize_or_replay(
            generation_key=generation_key,
            after_event_sequence=after_event_sequence,
            through_event_sequence=through_event_sequence,
            limit=limit,
            writes_quiesced=writes_quiesced,
            workers_stopped=workers_stopped,
            finalize_baseline=True,
            dry_run=dry_run,
        )

    def replay(
        self,
        *,
        generation_key: str,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
        writes_quiesced: bool,
        workers_stopped: bool,
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        return self._materialize_or_replay(
            generation_key=generation_key,
            after_event_sequence=after_event_sequence,
            through_event_sequence=through_event_sequence,
            limit=limit,
            writes_quiesced=writes_quiesced,
            workers_stopped=workers_stopped,
            finalize_baseline=False,
            dry_run=dry_run,
        )

    def _materialize_or_replay(
        self,
        *,
        generation_key: str,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
        writes_quiesced: bool,
        workers_stopped: bool,
        finalize_baseline: bool,
        dry_run: bool,
    ) -> FilesGenerationRunResult:
        if not writes_quiesced:
            raise FilesGenerationError("materialization_requires_quiesced_writers")
        if not workers_stopped:
            raise FilesGenerationError("materialization_requires_stopped_workers")
        if after_event_sequence < 0 or through_event_sequence < after_event_sequence:
            raise FilesGenerationError("materialization_event_range_invalid")
        if limit < 1 or limit > 1_000:
            raise FilesGenerationError("materialization_limit_invalid")
        spec = self._spec(generation_key)
        snapshot = self._source_snapshot()
        self._require_available_source(snapshot)
        if through_event_sequence != snapshot.files_event_watermark:
            raise FilesGenerationError("materialization_watermark_mismatch")
        pair = self._required_pair(spec.generation_key)
        self._require_registered_pair_matches_spec(pair, spec)
        expected_state = (
            RetrievalProjectionGenerationState.BASELINING.value
            if finalize_baseline
            else RetrievalProjectionGenerationState.REPLAYING.value
        )
        state = self._paired_state(pair)
        if finalize_baseline and state == RetrievalProjectionGenerationState.REPLAYING.value:
            inspection = self._require_complete_inspection(self._safe_inspect(spec))
            self._reconcile(snapshot, inspection)
            return self._result(spec, snapshot=snapshot, state=state, dry_run=dry_run)
        if state != expected_state:
            raise FilesGenerationError("generation_not_materializable")
        if self._materializer is None:
            raise FilesGenerationError("generation_materializer_unavailable")
        if dry_run:
            return self._result(
                spec,
                snapshot=snapshot,
                state="materialization-planned" if finalize_baseline else "replay-planned",
                dry_run=True,
                next_event_sequence=after_event_sequence,
                complete=False,
            )
        try:
            batch = self._materializer.materialize_batch(
                spec=spec,
                after_event_sequence=after_event_sequence,
                through_event_sequence=through_event_sequence,
                limit=limit,
            )
        except Exception as error:
            raise FilesGenerationError("generation_materialization_failed") from error
        if not batch.complete:
            return self._result(
                spec,
                snapshot=snapshot,
                state=state,
                dry_run=False,
                next_event_sequence=batch.next_event_sequence,
                complete=False,
            )
        if not batch.caught_up or batch.keyword_remaining or batch.vector_remaining:
            raise FilesGenerationError("generation_materialization_not_caught_up")

        final_snapshot = self._source_snapshot()
        self._require_available_source(final_snapshot)
        if final_snapshot.files_event_watermark != through_event_sequence:
            raise FilesGenerationError("source_changed_during_materialization")
        inspection = self._require_complete_inspection(self._safe_inspect(spec))
        self._reconcile(final_snapshot, inspection)
        try:
            with self._session_factory.begin() as db:
                current = self._load_pair(db, spec.generation_key)
                if self._files_event_watermark(db) != final_snapshot.files_event_watermark:
                    raise FilesGenerationError("source_changed_during_materialization")
                if finalize_baseline:
                    for generation in current:
                        mark_generation_replaying(
                            db,
                            generation_id=generation.id,
                            expected_projection_count=final_snapshot.resource_count,
                        )
                for generation in current:
                    advance_generation_replay_checkpoint(
                        db,
                        generation_id=generation.id,
                        event_sequence=final_snapshot.files_event_watermark,
                    )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("generation_replay_checkpoint_failed") from error
        return self._result(
            spec,
            snapshot=final_snapshot,
            state=RetrievalProjectionGenerationState.REPLAYING.value,
            dry_run=False,
            next_event_sequence=batch.next_event_sequence,
            complete=True,
        )

    def validate(
        self,
        *,
        generation_key: str,
        writes_quiesced: bool,
        reconciliation_watermark: int | None = None,
        quality_artifact: RetrievalQualityGateArtifact | None = None,
        quality_corpus_bytes: bytes | None = None,
        allow_empty_non_production: bool = False,
        allow_empty_production_bootstrap: bool = False,
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        if not writes_quiesced:
            raise FilesGenerationError("validation_requires_quiesced_writers")
        if reconciliation_watermark is None:
            raise FilesGenerationError("reconciliation_watermark_required")
        if reconciliation_watermark < 0:
            raise FilesGenerationError("reconciliation_watermark_invalid")
        spec = self._spec(generation_key)
        snapshot = self._source_snapshot()
        self._require_available_source(snapshot)
        if reconciliation_watermark != snapshot.files_event_watermark:
            raise FilesGenerationError("reconciliation_watermark_mismatch")
        pair = self._required_pair(spec.generation_key)
        self._require_registered_pair_matches_spec(pair, spec)
        state = self._paired_state(pair)
        if state not in {
            RetrievalProjectionGenerationState.REPLAYING.value,
            RetrievalProjectionGenerationState.READY.value,
            RetrievalProjectionGenerationState.ACTIVE.value,
        }:
            raise FilesGenerationError("generation_not_validatable")

        inspection = self._require_complete_inspection(self._safe_inspect(spec))
        self._reconcile(snapshot, inspection)
        queue_details = self._validate_queue_evidence(snapshot)
        quality_details = self._validate_quality(
            spec=spec,
            snapshot=snapshot,
            inspection=inspection,
            quality_artifact=quality_artifact,
            quality_corpus_bytes=quality_corpus_bytes,
            allow_empty_non_production=allow_empty_non_production,
            allow_empty_production_bootstrap=allow_empty_production_bootstrap,
        )
        if state in {
            RetrievalProjectionGenerationState.READY.value,
            RetrievalProjectionGenerationState.ACTIVE.value,
        }:
            self._require_stored_validation(
                pair,
                snapshot=snapshot,
                inspection=inspection,
                quality_corpus_bytes=quality_corpus_bytes,
            )
            return self._result(spec, snapshot=snapshot, state=state, dry_run=dry_run)
        if dry_run:
            return self._result(spec, snapshot=snapshot, state="validation-planned", dry_run=True)

        details = self._validation_details(
            spec=spec,
            snapshot=snapshot,
            inspection=inspection,
            quality_details=quality_details,
            queue_details=queue_details,
        )
        try:
            with self._session_factory.begin() as db:
                current = self._load_pair(db, spec.generation_key)
                if self._files_event_watermark(db) != snapshot.files_event_watermark:
                    raise FilesGenerationError("source_changed_during_validation")
                for generation in current:
                    advance_generation_replay_checkpoint(
                        db,
                        generation_id=generation.id,
                        event_sequence=snapshot.files_event_watermark,
                    )
                    mark_generation_validating(db, generation_id=generation.id)
                evidence_by_backend = {
                    RetrievalProjectionBackend.OPENSEARCH.value: inspection.opensearch,
                    RetrievalProjectionBackend.QDRANT.value: inspection.qdrant,
                }
                for generation in current:
                    evidence = evidence_by_backend[generation.backend]
                    assert evidence is not None
                    record_generation_validation(
                        db,
                        generation_id=generation.id,
                        passed=True,
                        details=details,
                        content_checksum=evidence.content_sha256,
                        config_checksum=evidence.config_sha256,
                    )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("generation_validation_state_failed") from error
        return self._result(
            spec,
            snapshot=snapshot,
            state=RetrievalProjectionGenerationState.READY.value,
            dry_run=False,
        )

    def attest_active(
        self,
        *,
        generation_key: str,
        writes_quiesced: bool,
        quality_artifact: RetrievalQualityGateArtifact | None,
        quality_corpus_bytes: bytes | None,
        scope_coverage: Sequence[str],
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        """Append judged quality evidence to an initially empty active pair."""

        if not writes_quiesced:
            raise FilesGenerationError("attestation_requires_quiesced_writers")
        normalized_scopes = tuple(
            sorted({str(scope or "").strip().lower() for scope in scope_coverage})
        )
        if not normalized_scopes or any(
            scope not in {"company", "company", "personal"} for scope in normalized_scopes
        ):
            raise FilesGenerationError("attestation_scope_coverage_invalid")

        spec = self._spec(generation_key)
        snapshot = self._source_snapshot()
        self._require_available_source(snapshot)
        if snapshot.resource_count <= 0:
            raise FilesGenerationError("attestation_requires_nonempty_source")
        if snapshot.unsupported_count:
            raise FilesGenerationError("attestation_requires_supported_source")

        pair = self._required_pair(spec.generation_key)
        self._require_registered_pair_matches_spec(pair, spec)
        if self._paired_state(pair) != RetrievalProjectionGenerationState.ACTIVE.value:
            raise FilesGenerationError("attestation_requires_active_generation")
        activation_details = self._validation_contract(pair[0])
        activation_source = activation_details.get("source")
        activation_quality = activation_details.get("quality")
        if (
            not isinstance(activation_source, dict)
            or activation_source.get("resource_count") != 0
            or not isinstance(activation_quality, dict)
            or activation_quality.get("mode") != "empty_production_bootstrap"
            or activation_quality.get("quality_status") != "deferred_until_nonempty"
        ):
            raise FilesGenerationError("attestation_requires_deferred_quality")

        inspection = self._require_complete_inspection(self._safe_inspect(spec))
        self._reconcile(snapshot, inspection)
        self._require_active_release_evidence(
            pair,
            snapshot=snapshot,
            inspection=inspection,
        )
        self._require_aliases_at_target(spec)
        self._validate_queue_evidence(snapshot)
        actual_scopes = self._active_source_scope_kinds()
        if actual_scopes != normalized_scopes:
            raise FilesGenerationError("attestation_scope_coverage_mismatch")
        quality_details = self._validate_quality(
            spec=spec,
            snapshot=snapshot,
            inspection=inspection,
            quality_artifact=quality_artifact,
            quality_corpus_bytes=quality_corpus_bytes,
            allow_empty_non_production=False,
        )
        if quality_artifact is None:
            raise FilesGenerationError("quality_evidence_required")
        artifact_sha256 = hashlib.sha256(
            _canonical_json_bytes(quality_artifact.model_dump(mode="json"))
        ).hexdigest()
        existing = self._read_quality_attestation(
            generation_key=spec.generation_key,
            files_event_watermark=snapshot.files_event_watermark,
        )
        if existing is not None:
            self._require_matching_quality_attestation(
                existing,
                pair=pair,
                artifact_sha256=artifact_sha256,
                quality_details=quality_details,
                scope_coverage=normalized_scopes,
            )
            return self._result(
                spec,
                snapshot=snapshot,
                state="quality-attested",
                dry_run=dry_run,
            )
        if dry_run:
            return self._result(
                spec,
                snapshot=snapshot,
                state="quality-attestation-planned",
                dry_run=True,
            )

        final_snapshot = self._source_snapshot()
        if final_snapshot != snapshot:
            raise FilesGenerationError("source_changed_during_attestation")
        try:
            with self._session_factory.begin() as db:
                current = self._load_pair(db, spec.generation_key)
                if (
                    self._paired_state(current) != RetrievalProjectionGenerationState.ACTIVE.value
                    or self._files_event_watermark(db) != snapshot.files_event_watermark
                ):
                    raise FilesGenerationError("source_changed_during_attestation")
                conflict = db.scalar(
                    select(RetrievalProjectionGenerationAttestation).where(
                        RetrievalProjectionGenerationAttestation.generation_key
                        == spec.generation_key,
                        RetrievalProjectionGenerationAttestation.source_files_event_watermark
                        == snapshot.files_event_watermark,
                    )
                )
                if conflict is not None:
                    self._require_matching_quality_attestation(
                        conflict,
                        pair=current,
                        artifact_sha256=artifact_sha256,
                        quality_details=quality_details,
                        scope_coverage=normalized_scopes,
                    )
                else:
                    db.add(
                        RetrievalProjectionGenerationAttestation(
                            generation_key=spec.generation_key,
                            opensearch_generation_id=self._backend_row(
                                current,
                                RetrievalProjectionBackend.OPENSEARCH,
                            ).id,
                            qdrant_generation_id=self._backend_row(
                                current,
                                RetrievalProjectionBackend.QDRANT,
                            ).id,
                            source_files_event_watermark=snapshot.files_event_watermark,
                            source_resource_count=snapshot.resource_count,
                            quality_artifact_sha256=artifact_sha256,
                            quality_corpus_id=str(quality_details["corpus_id"]),
                            quality_corpus_sha256=str(quality_details["corpus_sha256"]),
                            scope_coverage=list(normalized_scopes),
                            quality_details=quality_details,
                        )
                    )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("quality_attestation_persist_failed") from error
        return self._result(
            spec,
            snapshot=snapshot,
            state="quality-attested",
            dry_run=False,
        )

    def cutover(
        self,
        *,
        generation_key: str,
        writes_quiesced: bool,
        rollback_window: timedelta,
        quality_corpus_bytes: bytes | None = None,
        dry_run: bool = False,
    ) -> FilesGenerationRunResult:
        if not writes_quiesced:
            raise FilesGenerationError("cutover_requires_quiesced_writers")
        if rollback_window <= timedelta(0):
            raise FilesGenerationError("rollback_window_invalid")
        spec = self._spec(generation_key)
        snapshot = self._source_snapshot()
        self._require_available_source(snapshot)
        pair = self._required_pair(spec.generation_key)
        self._require_registered_pair_matches_spec(pair, spec)
        state = self._paired_state(pair)
        if state == RetrievalProjectionGenerationState.ACTIVE.value:
            inspection = self._require_complete_inspection(self._safe_inspect(spec))
            self._reconcile(snapshot, inspection)
            self._require_active_release_evidence(
                pair,
                snapshot=snapshot,
                inspection=inspection,
            )
            self._require_aliases_at_target(spec)
            self._validate_queue_evidence(snapshot)
            return self._result(spec, snapshot=snapshot, state=state, dry_run=dry_run)
        if state == RetrievalProjectionGenerationState.ACTIVATING.value:
            if dry_run:
                return self._result(spec, snapshot=snapshot, state=state, dry_run=True)
            inspection = self._require_complete_inspection(self._safe_inspect(spec))
            self._reconcile(snapshot, inspection)
            self._require_stored_validation(
                pair,
                snapshot=snapshot,
                inspection=inspection,
                quality_corpus_bytes=quality_corpus_bytes,
            )
            return self._recover_activating_pair(
                spec=spec,
                pair=pair,
                snapshot=snapshot,
                rollback_window=rollback_window,
                quality_corpus_bytes=quality_corpus_bytes,
            )
        if state != RetrievalProjectionGenerationState.READY.value:
            raise FilesGenerationError("generation_not_ready_for_cutover")

        inspection = self._require_complete_inspection(self._safe_inspect(spec))
        self._reconcile(snapshot, inspection)
        self._require_stored_validation(
            pair,
            snapshot=snapshot,
            inspection=inspection,
            quality_corpus_bytes=quality_corpus_bytes,
        )
        if dry_run:
            return self._result(spec, snapshot=snapshot, state="cutover-planned", dry_run=True)

        try:
            final_snapshot = self._source_snapshot()
            if final_snapshot != snapshot:
                raise FilesGenerationError("source_changed_during_cutover")
            self._require_current_quality_judgments(
                self._validation_contract(pair[0]),
                quality_corpus_bytes=quality_corpus_bytes,
            )
            with self._session_factory.begin() as db:
                current = self._load_pair(db, spec.generation_key)
                if self._files_event_watermark(db) != snapshot.files_event_watermark:
                    raise FilesGenerationError("source_changed_during_cutover")
                active_generation_count = int(
                    db.scalar(
                        select(func.count())
                        .select_from(RetrievalProjectionGeneration)
                        .where(
                            RetrievalProjectionGeneration.state
                            == RetrievalProjectionGenerationState.ACTIVE.value
                        )
                    )
                    or 0
                )
                if active_generation_count:
                    raise FilesGenerationError("generation_upgrade_rollback_unsupported")
                plan = prepare_generation_pair_cutover(
                    db,
                    opensearch_generation_id=self._backend_row(
                        current, RetrievalProjectionBackend.OPENSEARCH
                    ).id,
                    qdrant_generation_id=self._backend_row(
                        current, RetrievalProjectionBackend.QDRANT
                    ).id,
                    writes_quiesced=True,
                    required_event_sequence=snapshot.files_event_watermark,
                )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("generation_pair_prepare_failed") from error

        try:
            self._require_aliases_at_previous(plan)
        except Exception as error:
            self._persist_compensation(
                plan,
                aliases_restored=False,
                reason="alias_precondition_mismatch",
            )
            raise FilesGenerationError("alias_precondition_mismatch") from error

        moved_targets: list[RetrievalProjectionGenerationCutoverTarget] = []
        attempted_target: RetrievalProjectionGenerationCutoverTarget | None = None
        try:
            for target in (plan.opensearch, plan.qdrant):
                attempted_target = target
                self._switch_alias(target)
                moved_targets.append(target)
            self._require_plan_aliases_at_target(plan)
        except Exception as error:
            if (
                attempted_target is not None
                and attempted_target not in moved_targets
                and self._alias_is_at_target(attempted_target)
            ):
                moved_targets.append(attempted_target)
            restored = self._restore_plan_aliases(
                plan,
                moved_targets=tuple(moved_targets),
            )
            self._persist_compensation(plan, aliases_restored=restored)
            code = "alias_cutover_failed" if restored else "alias_compensation_required"
            raise FilesGenerationError(code) from error

        try:
            final_snapshot = self._source_snapshot()
            if final_snapshot != snapshot:
                raise FilesGenerationError("source_changed_during_cutover")
            self._require_current_quality_judgments(
                self._validation_contract(pair[0]),
                quality_corpus_bytes=quality_corpus_bytes,
            )
            with self._session_factory.begin() as db:
                if self._files_event_watermark(db) != snapshot.files_event_watermark:
                    raise FilesGenerationError("source_changed_during_cutover")
                complete_generation_pair_cutover(
                    db,
                    plan=plan,
                    rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + rollback_window,
                    required_event_sequence=snapshot.files_event_watermark,
                )
        except Exception as error:
            restored = self._restore_plan_aliases(
                plan,
                moved_targets=(plan.opensearch, plan.qdrant),
            )
            self._persist_compensation(plan, aliases_restored=restored)
            code = "database_cutover_failed" if restored else "alias_compensation_required"
            raise FilesGenerationError(code) from error
        return self._result(
            spec,
            snapshot=snapshot,
            state=RetrievalProjectionGenerationState.ACTIVE.value,
            dry_run=False,
        )

    def verify_active(self) -> FilesRetrievalCutoverStatus:
        try:
            snapshot = self._source_snapshot()
            self._require_available_source(snapshot)
            with self._session_factory() as db:
                rows = tuple(
                    db.scalars(
                        select(RetrievalProjectionGeneration)
                        .where(
                            RetrievalProjectionGeneration.backend.in_(
                                (
                                    RetrievalProjectionBackend.OPENSEARCH.value,
                                    RetrievalProjectionBackend.QDRANT.value,
                                )
                            ),
                            RetrievalProjectionGeneration.state
                            == RetrievalProjectionGenerationState.ACTIVE.value,
                        )
                        .order_by(RetrievalProjectionGeneration.backend.asc())
                    ).all()
                )
                if len(rows) != 2 or len({row.generation_key for row in rows}) != 1:
                    raise FilesGenerationError("active_generation_pair_invalid")
                pair = (rows[0], rows[1])
                generation_key = pair[0].generation_key
                db.expunge_all()
            spec = self._spec(generation_key)
            self._require_registered_pair_matches_spec(pair, spec)
            inspection = self._require_complete_inspection(self._safe_inspect(spec))
            self._reconcile(snapshot, inspection)
            self._require_active_release_evidence(
                pair,
                snapshot=snapshot,
                inspection=inspection,
            )
            self._require_aliases_at_target(spec)
            self._validate_queue_evidence(snapshot)
            with self._session_factory() as db:
                status = self._active_release_probe(db)
            if status.deployment_enabled and not status.ready:
                raise FilesGenerationError("active_release_gate_not_ready")
            return status
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("active_release_gate_failed") from error

    def _spec(self, generation_key: str) -> FilesGenerationPairSpec:
        try:
            normalized = str(generation_key or "").strip().lower()
            spec = FilesGenerationPairSpec(
                generation_key=normalized,
                opensearch_physical_name=keyword_search_partitioned_index_name(
                    self._settings.opensearch_index_prefix,
                    generation=normalized,
                ),
                opensearch_alias_name=keyword_search_partitioned_index_alias(
                    self._settings.opensearch_index_prefix
                ),
                qdrant_physical_name=resolve_partitioned_rag_collection_name(
                    self._settings,
                    generation=normalized,
                ),
                qdrant_alias_name=resolve_partitioned_rag_collection_alias(self._settings),
            )
        except Exception as error:
            raise FilesGenerationError("generation_identity_invalid") from error
        if spec.opensearch_alias_name == keyword_search_index_alias(
            self._settings.opensearch_index_prefix
        ) or spec.qdrant_alias_name == resolve_default_collection_name(self._settings):
            raise FilesGenerationError("shared_legacy_alias_forbidden")
        return spec

    def _source_snapshot(self) -> FilesSourceProjectionSnapshot:
        try:
            with self._session_factory() as db:
                return self._source_snapshot_loader(db)
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("source_snapshot_failed") from error

    @staticmethod
    def _require_available_source(snapshot: FilesSourceProjectionSnapshot) -> None:
        if snapshot.unavailable_count:
            raise FilesGenerationError("source_baseline_unavailable")

    def _safe_inspect(self, spec: FilesGenerationPairSpec) -> FilesBackendPairInspection:
        try:
            return self._backends.inspect_pair(spec)
        except Exception as error:
            raise FilesGenerationError("physical_generation_inspection_failed") from error

    @staticmethod
    def _require_complete_inspection(
        inspection: FilesBackendPairInspection,
    ) -> FilesBackendPairInspection:
        if inspection.opensearch is None and inspection.qdrant is None:
            raise FilesGenerationError("physical_generation_missing")
        if inspection.opensearch is None or inspection.qdrant is None:
            raise FilesGenerationError("partial_physical_generation")
        return inspection

    @staticmethod
    def _reconcile(
        snapshot: FilesSourceProjectionSnapshot,
        inspection: FilesBackendPairInspection,
    ) -> None:
        for evidence in (inspection.opensearch, inspection.qdrant):
            if evidence is None:
                raise FilesGenerationError("physical_generation_missing")
            if evidence.resource_count != snapshot.resource_count:
                raise FilesGenerationError("projection_resource_count_mismatch")
            if evidence.identity_sha256 != snapshot.identity_sha256:
                raise FilesGenerationError("projection_identity_mismatch")
        assert inspection.opensearch is not None
        if inspection.opensearch.record_count != snapshot.resource_count:
            raise FilesGenerationError("opensearch_document_count_mismatch")
        if (
            snapshot.opensearch_projection_sha256 is not None
            and inspection.opensearch.projection_sha256 != snapshot.opensearch_projection_sha256
        ):
            raise FilesGenerationError("opensearch_projection_content_mismatch")
        assert inspection.qdrant is not None
        if (
            snapshot.qdrant_record_count is not None
            and inspection.qdrant.record_count != snapshot.qdrant_record_count
        ):
            raise FilesGenerationError("qdrant_point_count_mismatch")
        if snapshot.qdrant_record_count is None and (
            (snapshot.resource_count and inspection.qdrant.record_count < snapshot.resource_count)
            or (not snapshot.resource_count and inspection.qdrant.record_count)
        ):
            raise FilesGenerationError("qdrant_point_count_mismatch")
        if (
            snapshot.qdrant_projection_sha256 is not None
            and inspection.qdrant.projection_sha256 != snapshot.qdrant_projection_sha256
        ):
            raise FilesGenerationError("qdrant_projection_content_mismatch")

    def _register_pair(
        self,
        spec: FilesGenerationPairSpec,
        *,
        baseline_event_sequence: int,
    ) -> None:
        try:
            with self._session_factory.begin() as db:
                existing = self._query_pair(db, spec.generation_key)
                if existing:
                    self._require_registered_pair_matches_spec(existing, spec)
                    return
                create_projection_generation(
                    db,
                    backend=RetrievalProjectionBackend.OPENSEARCH,
                    generation_key=spec.generation_key,
                    physical_name=spec.opensearch_physical_name,
                    alias_name=spec.opensearch_alias_name,
                    schema_version=RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
                    baseline_event_sequence=baseline_event_sequence,
                )
                create_projection_generation(
                    db,
                    backend=RetrievalProjectionBackend.QDRANT,
                    generation_key=spec.generation_key,
                    physical_name=spec.qdrant_physical_name,
                    alias_name=spec.qdrant_alias_name,
                    schema_version=PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
                    baseline_event_sequence=baseline_event_sequence,
                )
        except FilesGenerationError:
            raise
        except Exception as error:
            raise FilesGenerationError("generation_registration_failed") from error

    def _read_pair(
        self,
        generation_key: str,
    ) -> tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration] | None:
        with self._session_factory() as db:
            rows = self._query_pair(db, generation_key)
            if not rows:
                return None
            if len(rows) != 2:
                raise FilesGenerationError("partial_generation_registration")
            db.expunge_all()
            return rows[0], rows[1]

    def _required_pair(
        self,
        generation_key: str,
    ) -> tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration]:
        pair = self._read_pair(generation_key)
        if pair is None:
            raise FilesGenerationError("generation_pair_missing")
        return pair

    @staticmethod
    def _query_pair(
        db: Session,
        generation_key: str,
    ) -> tuple[RetrievalProjectionGeneration, ...]:
        return tuple(
            db.scalars(
                select(RetrievalProjectionGeneration)
                .where(RetrievalProjectionGeneration.generation_key == generation_key)
                .order_by(RetrievalProjectionGeneration.backend.asc())
            ).all()
        )

    @classmethod
    def _load_pair(
        cls,
        db: Session,
        generation_key: str,
    ) -> tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration]:
        rows = cls._query_pair(db, generation_key)
        if len(rows) != 2:
            raise FilesGenerationError("generation_pair_missing")
        return rows[0], rows[1]

    @staticmethod
    def _paired_state(
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
    ) -> str:
        states = {generation.state for generation in pair}
        if len(states) != 1:
            raise FilesGenerationError("generation_pair_state_mismatch")
        return next(iter(states))

    @staticmethod
    def _backend_row(
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        backend: RetrievalProjectionBackend,
    ) -> RetrievalProjectionGeneration:
        rows = tuple(generation for generation in pair if generation.backend == backend.value)
        if len(rows) != 1:
            raise FilesGenerationError("generation_backend_pair_invalid")
        return rows[0]

    @classmethod
    def _require_registered_pair_matches_spec(
        cls,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        spec: FilesGenerationPairSpec,
    ) -> None:
        opensearch = cls._backend_row(pair, RetrievalProjectionBackend.OPENSEARCH)
        qdrant = cls._backend_row(pair, RetrievalProjectionBackend.QDRANT)
        if (
            opensearch.physical_name != spec.opensearch_physical_name
            or opensearch.alias_name != spec.opensearch_alias_name
            or opensearch.schema_version != RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION
            or qdrant.physical_name != spec.qdrant_physical_name
            or qdrant.alias_name != spec.qdrant_alias_name
            or qdrant.schema_version != PARTITIONED_RAG_GENERATION_SCHEMA_VERSION
        ):
            raise FilesGenerationError("generation_registration_identity_mismatch")

    def _validate_quality(
        self,
        *,
        spec: FilesGenerationPairSpec,
        snapshot: FilesSourceProjectionSnapshot,
        inspection: FilesBackendPairInspection,
        quality_artifact: RetrievalQualityGateArtifact | None,
        quality_corpus_bytes: bytes | None,
        allow_empty_non_production: bool,
        allow_empty_production_bootstrap: bool = False,
    ) -> dict[str, object]:
        if snapshot.resource_count == 0:
            if is_production_environment(self._settings.environment):
                if not allow_empty_production_bootstrap:
                    raise FilesGenerationError("empty_generation_forbidden_in_production")
                if snapshot.unsupported_count or snapshot.unavailable_count:
                    raise FilesGenerationError(
                        "empty_production_bootstrap_requires_no_active_files"
                    )
                self._require_initial_empty_production_bootstrap()
                try:
                    embedding_identity = retrieval_embedding_generation_identity(self._settings)
                except Exception as error:
                    raise FilesGenerationError(
                        "embedding_generation_identity_unavailable"
                    ) from error
                try:
                    reranker_identity = retrieval_reranker_generation_identity(self._settings)
                except Exception as error:
                    raise FilesGenerationError(
                        "reranker_generation_identity_unavailable"
                    ) from error
                return {
                    "mode": "empty_production_bootstrap",
                    "quality_status": "deferred_until_nonempty",
                    "embedding_model_identity": embedding_identity.model_identity,
                    "embedding_config_sha256": embedding_identity.config_sha256,
                    "reranker_model_identity": reranker_identity.model_identity,
                    "reranker_config_sha256": reranker_identity.config_sha256,
                }
            if not allow_empty_non_production:
                raise FilesGenerationError("empty_generation_requires_explicit_confirmation")
            return {"mode": "empty_non_production"}
        if quality_artifact is None or quality_corpus_bytes is None:
            raise FilesGenerationError("quality_evidence_required")
        if quality_artifact.artifact_version != 3:
            raise FilesGenerationError("quality_evidence_version_unsupported")
        try:
            corpus = RetrievalQualityCorpus.model_validate_json(quality_corpus_bytes)
            gate = validate_quality_gate_artifact(
                quality_artifact,
                expected_index_generation=spec.generation_key,
                expected_corpus_id=corpus.corpus_id,
                expected_corpus_sha256=retrieval_quality_corpus_sha256(quality_corpus_bytes),
            )
        except Exception as error:
            raise FilesGenerationError("quality_evidence_invalid") from error
        if not gate.passed:
            raise FilesGenerationError("quality_gate_failed")
        judgment = self._current_quality_judgments(corpus)
        opensearch = inspection.opensearch
        qdrant = inspection.qdrant
        if opensearch is None or qdrant is None:
            raise FilesGenerationError("physical_generation_missing")
        try:
            embedding_identity = retrieval_embedding_generation_identity(self._settings)
        except Exception as error:
            raise FilesGenerationError("embedding_generation_identity_unavailable") from error
        try:
            reranker_identity = retrieval_reranker_generation_identity(self._settings)
        except Exception as error:
            raise FilesGenerationError("reranker_generation_identity_unavailable") from error
        if (
            quality_artifact.keyword_index_uuid != opensearch.physical_id
            or quality_artifact.keyword_index_config_sha256 != opensearch.config_sha256
            or quality_artifact.keyword_index_sha256 != opensearch.content_sha256
            or quality_artifact.qdrant_physical_id != qdrant.physical_id
            or quality_artifact.qdrant_config_sha256 != qdrant.config_sha256
            or quality_artifact.qdrant_content_sha256 != qdrant.content_sha256
            or quality_artifact.embedding_model_identity != embedding_identity.model_identity
            or quality_artifact.embedding_config_sha256 != embedding_identity.config_sha256
            or quality_artifact.reranker_model_identity != reranker_identity.model_identity
            or quality_artifact.reranker_config_sha256 != reranker_identity.config_sha256
        ):
            raise FilesGenerationError("quality_evidence_backend_mismatch")
        if (
            quality_artifact.source_files_event_watermark != snapshot.files_event_watermark
            or quality_artifact.source_resource_count != snapshot.resource_count
            or quality_artifact.source_identity_sha256 != snapshot.identity_sha256
            or quality_artifact.source_artifact_sha256 != snapshot.artifact_sha256
            or quality_artifact.source_acl_envelope_sha256 != snapshot.acl_envelope_sha256
            or quality_artifact.judgment_acl_sha256 != judgment.acl_sha256
        ):
            raise FilesGenerationError("quality_evidence_source_mismatch")
        return {
            "mode": "judged_corpus",
            "artifact_version": quality_artifact.artifact_version,
            "index_generation": quality_artifact.index_generation,
            "corpus_id": quality_artifact.corpus_id,
            "corpus_sha256": quality_artifact.corpus_sha256,
            "query_count": quality_artifact.hybrid.query_count,
            "keyword_index_uuid": quality_artifact.keyword_index_uuid,
            "keyword_index_config_sha256": quality_artifact.keyword_index_config_sha256,
            "keyword_index_sha256": quality_artifact.keyword_index_sha256,
            "qdrant_physical_id": quality_artifact.qdrant_physical_id,
            "qdrant_config_sha256": quality_artifact.qdrant_config_sha256,
            "qdrant_content_sha256": quality_artifact.qdrant_content_sha256,
            "embedding_model_identity": quality_artifact.embedding_model_identity,
            "embedding_config_sha256": quality_artifact.embedding_config_sha256,
            "reranker_model_identity": quality_artifact.reranker_model_identity,
            "reranker_config_sha256": quality_artifact.reranker_config_sha256,
            "source_files_event_watermark": quality_artifact.source_files_event_watermark,
            "source_resource_count": quality_artifact.source_resource_count,
            "source_identity_sha256": quality_artifact.source_identity_sha256,
            "source_artifact_sha256": quality_artifact.source_artifact_sha256,
            "source_acl_envelope_sha256": quality_artifact.source_acl_envelope_sha256,
            "judgment_acl_sha256": quality_artifact.judgment_acl_sha256,
        }

    def _require_initial_empty_production_bootstrap(self) -> None:
        try:
            with self._session_factory() as db:
                active_generation_count = int(
                    db.scalar(
                        select(func.count())
                        .select_from(RetrievalProjectionGeneration)
                        .where(
                            RetrievalProjectionGeneration.state
                            == RetrievalProjectionGenerationState.ACTIVE.value
                        )
                    )
                    or 0
                )
        except Exception as error:
            raise FilesGenerationError(
                "empty_production_bootstrap_initial_state_check_failed"
            ) from error
        if active_generation_count:
            raise FilesGenerationError("empty_production_bootstrap_requires_initial_activation")

    def _active_source_scope_kinds(self) -> tuple[str, ...]:
        try:
            with self._session_factory() as db:
                rows = db.execute(
                    select(
                        FileManagerFile.corpus_id,
                        FileManagerCorpus.access_scope_kind,
                    )
                    .select_from(RetrievalProjectionHead)
                    .join(
                        FileManagerFile,
                        (RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE)
                        & (RetrievalProjectionHead.resource_id == FileManagerFile.id),
                    )
                    .outerjoin(
                        FileManagerCorpus,
                        FileManagerCorpus.id == FileManagerFile.corpus_id,
                    )
                    .where(
                        RetrievalProjectionHead.desired_state
                        == RetrievalProjectionDesiredState.ACTIVE.value,
                        FileManagerFile.deleted_at.is_(None),
                        FileManagerFile.extraction_status == "ready",
                    )
                )
                scopes = {
                    (
                        str(row.access_scope_kind).strip().lower()
                        if row.corpus_id is not None
                        else "company"
                    )
                    for row in rows
                }
        except Exception as error:
            raise FilesGenerationError("attestation_scope_inspection_failed") from error
        if not scopes or any(scope not in {"company", "company", "personal"} for scope in scopes):
            raise FilesGenerationError("attestation_scope_inspection_failed")
        return tuple(sorted(scopes))

    def _read_quality_attestation(
        self,
        *,
        generation_key: str,
        files_event_watermark: int,
    ) -> RetrievalProjectionGenerationAttestation | None:
        try:
            with self._session_factory() as db:
                row = db.scalar(
                    select(RetrievalProjectionGenerationAttestation).where(
                        RetrievalProjectionGenerationAttestation.generation_key == generation_key,
                        RetrievalProjectionGenerationAttestation.source_files_event_watermark
                        == files_event_watermark,
                    )
                )
                if row is not None:
                    db.expunge(row)
                return row
        except Exception as error:
            raise FilesGenerationError("quality_attestation_read_failed") from error

    @classmethod
    def _require_matching_quality_attestation(
        cls,
        attestation: RetrievalProjectionGenerationAttestation,
        *,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        artifact_sha256: str,
        quality_details: dict[str, object],
        scope_coverage: Sequence[str],
    ) -> None:
        if (
            attestation.opensearch_generation_id
            != cls._backend_row(pair, RetrievalProjectionBackend.OPENSEARCH).id
            or attestation.qdrant_generation_id
            != cls._backend_row(pair, RetrievalProjectionBackend.QDRANT).id
            or attestation.quality_artifact_sha256 != artifact_sha256
            or attestation.quality_corpus_id != quality_details.get("corpus_id")
            or attestation.quality_corpus_sha256 != quality_details.get("corpus_sha256")
            or attestation.scope_coverage != list(scope_coverage)
            or attestation.quality_details != quality_details
        ):
            raise FilesGenerationError("quality_attestation_conflict")

    def _current_quality_judgments(
        self,
        corpus: RetrievalQualityCorpus,
    ) -> FilesQualityJudgmentSnapshot:
        try:
            return self._quality_judgment_validator(corpus)
        except FilesQualityJudgmentError as error:
            raise FilesGenerationError(error.code) from error
        except Exception as error:
            raise FilesGenerationError("quality_judgment_validation_failed") from error

    @staticmethod
    def _validation_details(
        *,
        spec: FilesGenerationPairSpec,
        snapshot: FilesSourceProjectionSnapshot,
        inspection: FilesBackendPairInspection,
        quality_details: dict[str, object],
        queue_details: dict[str, object],
    ) -> dict[str, object]:
        assert inspection.opensearch is not None and inspection.qdrant is not None
        return {
            "release_cohort": spec.generation_key,
            "included_resource_types": [FILE_MANAGER_FILE_RESOURCE_TYPE],
            "source": {
                "files_event_watermark": snapshot.files_event_watermark,
                "resource_count": snapshot.resource_count,
                "identity_sha256": snapshot.identity_sha256,
                "artifact_sha256": snapshot.artifact_sha256,
                "acl_envelope_sha256": snapshot.acl_envelope_sha256,
                "qdrant_record_count": snapshot.qdrant_record_count,
                "opensearch_projection_sha256": snapshot.opensearch_projection_sha256,
                "qdrant_projection_sha256": snapshot.qdrant_projection_sha256,
                "unsupported_count": snapshot.unsupported_count,
                "unavailable_count": snapshot.unavailable_count,
            },
            "opensearch": _inventory_details(inspection.opensearch),
            "qdrant": _inventory_details(inspection.qdrant),
            "queue": queue_details,
            "quality": quality_details,
        }

    def _validate_queue_evidence(
        self,
        snapshot: FilesSourceProjectionSnapshot,
    ) -> dict[str, object]:
        if snapshot.resource_count == 0:
            return {
                "files_event_watermark": snapshot.files_event_watermark,
                "keyword_remaining": 0,
                "vector_remaining": 0,
                "caught_up": True,
            }
        if self._materializer is None:
            raise FilesGenerationError("queue_drain_evidence_unavailable")
        try:
            status = self._materializer.inspect_reconciliation(
                through_event_sequence=snapshot.files_event_watermark
            )
            current = int(getattr(status, "current_event_sequence"))
            keyword_remaining = int(getattr(status, "keyword_remaining"))
            vector_remaining = int(getattr(status, "vector_remaining"))
            caught_up = bool(getattr(status, "caught_up"))
        except Exception as error:
            raise FilesGenerationError("queue_drain_evidence_failed") from error
        if (
            current != snapshot.files_event_watermark
            or keyword_remaining != 0
            or vector_remaining != 0
            or not caught_up
        ):
            raise FilesGenerationError("projection_queues_not_drained")
        return {
            "files_event_watermark": snapshot.files_event_watermark,
            "keyword_remaining": keyword_remaining,
            "vector_remaining": vector_remaining,
            "caught_up": caught_up,
        }

    def _require_stored_validation(
        self,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        *,
        snapshot: FilesSourceProjectionSnapshot,
        inspection: FilesBackendPairInspection,
        quality_corpus_bytes: bytes | None = None,
    ) -> None:
        if pair[0].validation_details != pair[1].validation_details:
            raise FilesGenerationError("stored_validation_evidence_diverged")
        details = FilesGenerationRunner._validation_contract(pair[0])
        self._require_current_quality_judgments(
            details,
            quality_corpus_bytes=quality_corpus_bytes,
        )
        evidence_by_backend = {
            RetrievalProjectionBackend.OPENSEARCH.value: inspection.opensearch,
            RetrievalProjectionBackend.QDRANT.value: inspection.qdrant,
        }
        for generation in pair:
            evidence = evidence_by_backend[generation.backend]
            if evidence is None:
                raise FilesGenerationError("physical_generation_missing")
            details = FilesGenerationRunner._validation_contract(generation)
            self._require_current_model_identities(details)
            source_details = details.get("source")
            backend_details = details.get(generation.backend)
            queue_details = details.get("queue")
            assert isinstance(source_details, dict)
            assert isinstance(backend_details, dict)
            assert isinstance(queue_details, dict)
            if (
                queue_details.get("caught_up") is not True
                or queue_details.get("keyword_remaining") != 0
                or queue_details.get("vector_remaining") != 0
            ):
                raise FilesGenerationError("stored_validation_evidence_invalid")
            if (
                source_details.get("files_event_watermark") != snapshot.files_event_watermark
                or source_details.get("resource_count") != snapshot.resource_count
                or source_details.get("identity_sha256") != snapshot.identity_sha256
                or source_details.get("artifact_sha256") != snapshot.artifact_sha256
                or source_details.get("acl_envelope_sha256") != snapshot.acl_envelope_sha256
                or source_details.get("qdrant_record_count") != snapshot.qdrant_record_count
                or source_details.get("opensearch_projection_sha256")
                != snapshot.opensearch_projection_sha256
                or source_details.get("qdrant_projection_sha256")
                != snapshot.qdrant_projection_sha256
                or source_details.get("unsupported_count") != snapshot.unsupported_count
                or source_details.get("unavailable_count") != snapshot.unavailable_count
                or backend_details != _inventory_details(evidence)
                or queue_details.get("files_event_watermark") != snapshot.files_event_watermark
                or generation.expected_projection_count != snapshot.resource_count
                or generation.replay_event_sequence != snapshot.files_event_watermark
                or generation.content_checksum != evidence.content_sha256
                or generation.config_checksum != evidence.config_sha256
            ):
                raise FilesGenerationError("stored_validation_stale")

    def _require_active_release_evidence(
        self,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        *,
        snapshot: FilesSourceProjectionSnapshot,
        inspection: FilesBackendPairInspection,
    ) -> None:
        """Validate immutable release identity without freezing mutable content.

        ACTIVE writers legitimately advance Files heads, backend content, and the
        source watermark.  Steady-state release probes therefore validate the
        current source/backend reconciliation separately and retain only the
        immutable cohort, physical identity, and backend configuration fences
        from activation evidence.
        """

        if pair[0].validation_details != pair[1].validation_details:
            raise FilesGenerationError("stored_validation_evidence_diverged")
        evidence_by_backend = {
            RetrievalProjectionBackend.OPENSEARCH.value: inspection.opensearch,
            RetrievalProjectionBackend.QDRANT.value: inspection.qdrant,
        }
        for generation in pair:
            if generation.state != RetrievalProjectionGenerationState.ACTIVE.value:
                raise FilesGenerationError("active_generation_pair_invalid")
            evidence = evidence_by_backend[generation.backend]
            if evidence is None:
                raise FilesGenerationError("physical_generation_missing")
            details = self._validation_contract(generation)
            backend_details = details.get(generation.backend)
            if not isinstance(backend_details, dict):
                raise FilesGenerationError("stored_validation_evidence_invalid")
            if (
                backend_details.get("physical_id") != evidence.physical_id
                or backend_details.get("config_sha256") != evidence.config_sha256
                or generation.config_checksum != evidence.config_sha256
            ):
                raise FilesGenerationError("active_generation_configuration_drift")
            self._require_current_model_identities(details)

    @staticmethod
    def _validation_contract(
        generation: RetrievalProjectionGeneration,
    ) -> dict[str, object]:
        details = generation.validation_details
        if not isinstance(details, dict):
            raise FilesGenerationError("stored_validation_evidence_invalid")
        source_details = details.get("source")
        backend_details = details.get(generation.backend)
        queue_details = details.get("queue")
        quality_details = details.get("quality")
        if (
            generation.validation_state != "passed"
            or details.get("release_cohort") != generation.generation_key
            or details.get("included_resource_types") != [FILE_MANAGER_FILE_RESOURCE_TYPE]
            or not isinstance(source_details, dict)
            or not isinstance(backend_details, dict)
            or not isinstance(queue_details, dict)
            or not isinstance(quality_details, dict)
        ):
            raise FilesGenerationError("stored_validation_evidence_invalid")
        activation_resource_count = source_details.get("resource_count")
        if not isinstance(activation_resource_count, int) or activation_resource_count < 0:
            raise FilesGenerationError("stored_validation_evidence_invalid")
        if activation_resource_count > 0:
            if (
                quality_details.get("mode") != "judged_corpus"
                or quality_details.get("artifact_version") != 3
                or quality_details.get("index_generation") != generation.generation_key
                or not isinstance(quality_details.get("corpus_id"), str)
                or not _is_sha256(quality_details.get("corpus_sha256"))
                or not isinstance(quality_details.get("query_count"), int)
                or int(quality_details["query_count"]) < 60
                or not isinstance(quality_details.get("keyword_index_uuid"), str)
                or not _is_sha256(quality_details.get("keyword_index_config_sha256"))
                or not _is_sha256(quality_details.get("keyword_index_sha256"))
                or not isinstance(quality_details.get("qdrant_physical_id"), str)
                or not _is_sha256(quality_details.get("qdrant_config_sha256"))
                or not _is_sha256(quality_details.get("qdrant_content_sha256"))
                or not isinstance(quality_details.get("embedding_model_identity"), str)
                or not _is_sha256(quality_details.get("embedding_config_sha256"))
                or not isinstance(quality_details.get("reranker_model_identity"), str)
                or not _is_sha256(quality_details.get("reranker_config_sha256"))
                or not isinstance(quality_details.get("source_files_event_watermark"), int)
                or not isinstance(quality_details.get("source_resource_count"), int)
                or not _is_sha256(quality_details.get("source_identity_sha256"))
                or not _is_sha256(quality_details.get("source_artifact_sha256"))
                or not _is_sha256(quality_details.get("source_acl_envelope_sha256"))
                or not _is_sha256(quality_details.get("judgment_acl_sha256"))
            ):
                raise FilesGenerationError("stored_validation_quality_invalid")
            if (
                quality_details.get("source_files_event_watermark")
                != source_details.get("files_event_watermark")
                or quality_details.get("source_resource_count")
                != source_details.get("resource_count")
                or quality_details.get("source_identity_sha256")
                != source_details.get("identity_sha256")
                or quality_details.get("source_artifact_sha256")
                != source_details.get("artifact_sha256")
                or quality_details.get("source_acl_envelope_sha256")
                != source_details.get("acl_envelope_sha256")
            ):
                raise FilesGenerationError("stored_validation_quality_source_mismatch")
            if generation.backend == RetrievalProjectionBackend.OPENSEARCH.value:
                quality_identity_matches = (
                    quality_details.get("keyword_index_uuid") == backend_details.get("physical_id")
                    and quality_details.get("keyword_index_config_sha256")
                    == backend_details.get("config_sha256")
                    == generation.config_checksum
                    and quality_details.get("keyword_index_sha256")
                    == backend_details.get("content_sha256")
                    == generation.content_checksum
                )
            elif generation.backend == RetrievalProjectionBackend.QDRANT.value:
                quality_identity_matches = (
                    quality_details.get("qdrant_physical_id") == backend_details.get("physical_id")
                    and quality_details.get("qdrant_config_sha256")
                    == backend_details.get("config_sha256")
                    == generation.config_checksum
                    and quality_details.get("qdrant_content_sha256")
                    == backend_details.get("content_sha256")
                    == generation.content_checksum
                )
            else:
                quality_identity_matches = False
            if not quality_identity_matches:
                raise FilesGenerationError("stored_validation_quality_identity_mismatch")
        elif quality_details.get("mode") == "empty_production_bootstrap":
            if (
                quality_details.get("quality_status") != "deferred_until_nonempty"
                or not isinstance(quality_details.get("embedding_model_identity"), str)
                or not _is_sha256(quality_details.get("embedding_config_sha256"))
                or not isinstance(quality_details.get("reranker_model_identity"), str)
                or not _is_sha256(quality_details.get("reranker_config_sha256"))
            ):
                raise FilesGenerationError("stored_validation_quality_invalid")
        elif quality_details.get("mode") != "empty_non_production":
            raise FilesGenerationError("stored_validation_quality_invalid")
        return details

    def _require_current_model_identities(self, details: dict[str, object]) -> None:
        source_details = details.get("source")
        quality_details = details.get("quality")
        if not isinstance(source_details, dict) or not isinstance(quality_details, dict):
            raise FilesGenerationError("stored_validation_evidence_invalid")
        if (
            source_details.get("resource_count") == 0
            and quality_details.get("mode") != "empty_production_bootstrap"
        ):
            return
        try:
            embedding_identity = retrieval_embedding_generation_identity(self._settings)
        except Exception as error:
            raise FilesGenerationError("embedding_generation_identity_unavailable") from error
        try:
            reranker_identity = retrieval_reranker_generation_identity(self._settings)
        except Exception as error:
            raise FilesGenerationError("reranker_generation_identity_unavailable") from error
        if (
            quality_details.get("embedding_model_identity") != embedding_identity.model_identity
            or quality_details.get("embedding_config_sha256") != embedding_identity.config_sha256
        ):
            raise FilesGenerationError("embedding_generation_configuration_drift")
        if (
            quality_details.get("reranker_model_identity") != reranker_identity.model_identity
            or quality_details.get("reranker_config_sha256") != reranker_identity.config_sha256
        ):
            raise FilesGenerationError("reranker_generation_configuration_drift")

    def _require_current_quality_judgments(
        self,
        details: dict[str, object],
        *,
        quality_corpus_bytes: bytes | None,
    ) -> None:
        source_details = details.get("source")
        quality_details = details.get("quality")
        if not isinstance(source_details, dict) or not isinstance(quality_details, dict):
            raise FilesGenerationError("stored_validation_evidence_invalid")
        if source_details.get("resource_count") == 0:
            return
        if quality_corpus_bytes is None:
            raise FilesGenerationError("quality_corpus_required_for_cutover")
        try:
            corpus = RetrievalQualityCorpus.model_validate_json(quality_corpus_bytes)
        except Exception as error:
            raise FilesGenerationError("quality_evidence_invalid") from error
        if quality_details.get("corpus_id") != corpus.corpus_id or quality_details.get(
            "corpus_sha256"
        ) != retrieval_quality_corpus_sha256(quality_corpus_bytes):
            raise FilesGenerationError("quality_evidence_invalid")
        judgment = self._current_quality_judgments(corpus)
        if quality_details.get("judgment_acl_sha256") != judgment.acl_sha256:
            raise FilesGenerationError("quality_judgment_acl_stale")

    @staticmethod
    def _files_event_watermark(db: Session) -> int:
        return int(
            db.scalar(
                select(func.max(RetrievalProjectionEvent.event_sequence)).where(
                    RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
                )
            )
            or 0
        )

    def _require_aliases_at_previous(
        self,
        plan: RetrievalProjectionGenerationPairCutoverPlan,
    ) -> None:
        for target in (plan.opensearch, plan.qdrant):
            current = self._alias_target(target)
            if current != target.previous_physical_name:
                raise FilesGenerationError("alias_precondition_mismatch")

    def _require_aliases_at_target(self, spec: FilesGenerationPairSpec) -> None:
        expected = (
            (
                RetrievalProjectionBackend.OPENSEARCH.value,
                spec.opensearch_alias_name,
                spec.opensearch_physical_name,
            ),
            (
                RetrievalProjectionBackend.QDRANT.value,
                spec.qdrant_alias_name,
                spec.qdrant_physical_name,
            ),
        )
        for backend, alias_name, physical_name in expected:
            try:
                current = self._backends.alias_target(
                    backend=backend,
                    alias_name=alias_name,
                )
            except Exception as error:
                raise FilesGenerationError("alias_probe_failed") from error
            if current != physical_name:
                raise FilesGenerationError("active_alias_mismatch")

    def _require_plan_aliases_at_target(
        self,
        plan: RetrievalProjectionGenerationPairCutoverPlan,
    ) -> None:
        for target in (plan.opensearch, plan.qdrant):
            if self._alias_target(target) != target.physical_name:
                raise FilesGenerationError("alias_switch_verification_failed")

    def _alias_target(self, target: RetrievalProjectionGenerationCutoverTarget) -> str | None:
        return self._backends.alias_target(
            backend=target.backend,
            alias_name=target.alias_name,
        )

    def _switch_alias(self, target: RetrievalProjectionGenerationCutoverTarget) -> None:
        self._backends.set_alias(
            backend=target.backend,
            alias_name=target.alias_name,
            physical_name=target.physical_name,
        )

    def _restore_plan_aliases(
        self,
        plan: RetrievalProjectionGenerationPairCutoverPlan,
        *,
        moved_targets: tuple[RetrievalProjectionGenerationCutoverTarget, ...],
    ) -> bool:
        restored = True
        moved_ids = {target.generation_id for target in moved_targets}
        for target in (plan.qdrant, plan.opensearch):
            if target.generation_id not in moved_ids:
                continue
            try:
                if target.previous_physical_name is None:
                    self._backends.remove_alias(
                        backend=target.backend,
                        alias_name=target.alias_name,
                    )
                else:
                    self._backends.set_alias(
                        backend=target.backend,
                        alias_name=target.alias_name,
                        physical_name=target.previous_physical_name,
                    )
            except Exception:
                restored = False
        for target in (plan.opensearch, plan.qdrant):
            try:
                if self._alias_target(target) != target.previous_physical_name:
                    restored = False
            except Exception:
                restored = False
        return restored

    def _alias_is_at_target(
        self,
        target: RetrievalProjectionGenerationCutoverTarget,
    ) -> bool:
        try:
            return self._alias_target(target) == target.physical_name
        except Exception:
            return False

    def _persist_compensation(
        self,
        plan: RetrievalProjectionGenerationPairCutoverPlan,
        *,
        aliases_restored: bool,
        reason: str = "external_alias_switch_failed",
    ) -> None:
        try:
            with self._session_factory.begin() as db:
                compensate_generation_pair_cutover(
                    db,
                    plan=plan,
                    reason=reason,
                    aliases_restored=aliases_restored,
                )
        except Exception as error:
            raise FilesGenerationError("cutover_compensation_persist_failed") from error

    def _recover_activating_pair(
        self,
        *,
        spec: FilesGenerationPairSpec,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
        snapshot: FilesSourceProjectionSnapshot,
        rollback_window: timedelta,
        quality_corpus_bytes: bytes | None,
    ) -> FilesGenerationRunResult:
        plan = self._rebuild_cutover_plan(pair)
        targets = tuple(self._alias_target(target) for target in (plan.opensearch, plan.qdrant))
        if targets == (plan.opensearch.physical_name, plan.qdrant.physical_name):
            try:
                final_snapshot = self._source_snapshot()
                if final_snapshot != snapshot:
                    raise FilesGenerationError("source_changed_during_cutover")
                self._require_current_quality_judgments(
                    self._validation_contract(pair[0]),
                    quality_corpus_bytes=quality_corpus_bytes,
                )
                with self._session_factory.begin() as db:
                    if self._files_event_watermark(db) != snapshot.files_event_watermark:
                        raise FilesGenerationError("source_changed_during_cutover")
                    complete_generation_pair_cutover(
                        db,
                        plan=plan,
                        rollback_expires_at=(
                            datetime.now(UTC).replace(tzinfo=None) + rollback_window
                        ),
                        required_event_sequence=snapshot.files_event_watermark,
                    )
            except Exception as error:
                restored = self._restore_plan_aliases(
                    plan,
                    moved_targets=(plan.opensearch, plan.qdrant),
                )
                self._persist_compensation(plan, aliases_restored=restored)
                code = (
                    "activating_pair_completion_failed"
                    if restored
                    else "alias_compensation_required"
                )
                raise FilesGenerationError(code) from error
            return self._result(
                spec,
                snapshot=snapshot,
                state=RetrievalProjectionGenerationState.ACTIVE.value,
                dry_run=False,
            )
        moved_targets = tuple(
            target
            for target, current in zip(
                (plan.opensearch, plan.qdrant),
                targets,
                strict=True,
            )
            if current == target.physical_name
        )
        restored = self._restore_plan_aliases(
            plan,
            moved_targets=moved_targets,
        )
        self._persist_compensation(plan, aliases_restored=restored)
        code = "activating_pair_recovered" if restored else "alias_compensation_required"
        raise FilesGenerationError(code)

    def _rebuild_cutover_plan(
        self,
        pair: tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration],
    ) -> RetrievalProjectionGenerationPairCutoverPlan:
        by_id: dict[str, RetrievalProjectionGeneration] = {}
        previous_ids = {
            generation.previous_generation_id
            for generation in pair
            if generation.previous_generation_id
        }
        if previous_ids:
            with self._session_factory() as db:
                rows = tuple(
                    db.scalars(
                        select(RetrievalProjectionGeneration).where(
                            RetrievalProjectionGeneration.id.in_(previous_ids)
                        )
                    ).all()
                )
                by_id = {row.id: row for row in rows}

        def target(generation: RetrievalProjectionGeneration):
            previous = by_id.get(str(generation.previous_generation_id))
            return RetrievalProjectionGenerationCutoverTarget(
                backend=generation.backend,
                generation_id=generation.id,
                alias_name=generation.alias_name,
                physical_name=generation.physical_name,
                previous_generation_id=generation.previous_generation_id,
                previous_physical_name=previous.physical_name if previous is not None else None,
            )

        return RetrievalProjectionGenerationPairCutoverPlan(
            generation_key=pair[0].generation_key,
            opensearch=target(self._backend_row(pair, RetrievalProjectionBackend.OPENSEARCH)),
            qdrant=target(self._backend_row(pair, RetrievalProjectionBackend.QDRANT)),
        )

    @staticmethod
    def _result(
        spec: FilesGenerationPairSpec,
        *,
        snapshot: FilesSourceProjectionSnapshot,
        state: str,
        dry_run: bool,
        next_event_sequence: int | None = None,
        complete: bool | None = None,
    ) -> FilesGenerationRunResult:
        return FilesGenerationRunResult(
            generation_key=spec.generation_key,
            state=state,
            dry_run=dry_run,
            source_resource_count=snapshot.resource_count,
            unsupported_source_count=snapshot.unsupported_count,
            next_event_sequence=next_event_sequence,
            complete=complete,
        )


def load_files_source_snapshot(db: Session) -> FilesSourceProjectionSnapshot:
    """Build Files source, ACL-envelope, and projection-contract inventories.

    ``ready`` rows are eligible only when their cached extraction artifact and
    canonical projection head agree. Unsupported rows are explicit exclusions;
    pending or failed rows make the baseline unavailable instead of disappearing.
    Projection contracts intentionally omit mutable ACL routing hints so a
    corpus scope transition is fenced by ``acl_envelope_sha256`` but
    does not require re-indexing or embedding.
    """

    rows = db.execute(
        select(
            FileManagerFile.id,
            FileManagerFile.filename,
            FileManagerFile.content_type,
            FileManagerFile.size_bytes,
            FileManagerFile.visibility,
            FileManagerFile.folder_id,
            FileManagerFile.corpus_id,
            FileManagerFile.owner_id,
            FileManagerFile.updated_at,
            FileManagerFile.extraction_status,
            FileManagerFile.extraction_content_checksum,
            FileManagerFile.extraction_text,
            FileManagerFile.extraction_blocks,
            FileManagerFile.extraction_metadata,
            FileManagerFile.retrieval_partition_id.label("file_partition_id"),
            User.display_name.label("owner_display_name"),
            User.full_name.label("owner_full_name"),
            FileManagerCorpus.retrieval_partition_id.label("corpus_partition_id"),
            FileManagerCorpus.access_scope_kind.label("corpus_access_scope_kind"),
            FileManagerCorpus.metadata_version.label("corpus_metadata_version"),
            FileManagerCorpus.source_managed.label("corpus_source_managed"),
            FileManagerCorpus.authorization_mode.label("corpus_authorization_mode"),
            FileManagerFileSourceMetadata.source_kind.label("source_metadata_source_kind"),
            FileManagerFileSourceMetadata.source_updated_at.label(
                "source_metadata_source_updated_at"
            ),
            FileManagerFileSourceMetadata.title.label("source_metadata_title"),
            FileManagerFileSourceMetadata.author.label("source_metadata_author"),
            FileManagerFileSourceMetadata.authored_at.label("source_metadata_authored_at"),
            FileManagerFileSourceMetadata.department.label("source_metadata_department"),
            FileManagerFileSourceMetadata.document_type.label("source_metadata_document_type"),
            FileManagerFileSourceMetadata.acl_resolved.label("source_metadata_acl_resolved"),
            RetrievalPartition.source_namespace.label("partition_source_namespace"),
            RetrievalPartition.candidate_scope_kind.label("partition_candidate_scope_kind"),
            RetrievalPartition.candidate_user_id.label("partition_candidate_user_id"),
            RetrievalPartition.state.label("partition_state"),
            RetrievalPartition.metadata_version.label("partition_metadata_version"),
            RetrievalPartition.is_default_ingest.label("partition_is_default_ingest"),
            RetrievalProjectionHead.projection_version,
            RetrievalProjectionHead.retrieval_partition_id.label("head_partition_id"),
            RetrievalProjectionHead.desired_state,
            RetrievalProjectionHead.content_checksum,
        )
        .outerjoin(User, User.id == FileManagerFile.owner_id)
        .outerjoin(FileManagerCorpus, FileManagerCorpus.id == FileManagerFile.corpus_id)
        .outerjoin(
            FileManagerFileSourceMetadata,
            FileManagerFileSourceMetadata.file_id == FileManagerFile.id,
        )
        .outerjoin(
            RetrievalPartition,
            RetrievalPartition.id == FileManagerFile.retrieval_partition_id,
        )
        .outerjoin(
            RetrievalProjectionHead,
            (RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE)
            & (RetrievalProjectionHead.resource_id == FileManagerFile.id),
        )
        .where(FileManagerFile.deleted_at.is_(None))
        .order_by(FileManagerFile.id.asc())
        .execution_options(yield_per=64)
    )
    identity_digest = hashlib.sha256()
    artifact_digest = hashlib.sha256()
    acl_envelope_digest = ProjectionContractDigest()
    opensearch_projection_digest = ProjectionContractDigest()
    qdrant_projection_digest = ProjectionContractDigest()
    qdrant_record_count = 0
    resource_count = 0
    unsupported_count = 0
    unavailable_count = 0
    for row in rows:
        status = str(row.extraction_status or "")
        if status == "unsupported":
            unsupported_count += 1
            continue
        artifact_ready = (
            status == "ready"
            and bool(str(row.extraction_content_checksum or "").strip())
            and bool(str(row.extraction_text or "").strip())
            and isinstance(row.extraction_blocks, list)
            and bool(row.extraction_blocks)
        )
        acl_envelope = _source_acl_envelope(row)
        projection_ready = (
            row.file_partition_id is not None
            and row.projection_version is not None
            and int(row.projection_version) > 0
            and str(row.file_partition_id) == str(row.head_partition_id)
            and row.desired_state == RetrievalProjectionDesiredState.ACTIVE.value
            and row.content_checksum == row.extraction_content_checksum
            and acl_envelope is not None
        )
        if not artifact_ready or not projection_ready:
            unavailable_count += 1
            continue
        try:
            blocks = [EvidenceBlock(**dict(item)) for item in row.extraction_blocks]
            artifact = FileExtractionArtifact(
                content_checksum=str(row.extraction_content_checksum),
                text=str(row.extraction_text),
                blocks=blocks,
                metadata=dict(row.extraction_metadata or {}),
            )
            corpus = (
                SimpleNamespace(
                    id=str(row.corpus_id),
                    retrieval_partition_id=str(row.corpus_partition_id),
                    access_scope_kind=str(row.corpus_access_scope_kind),
                    metadata_version=int(row.corpus_metadata_version),
                )
                if row.corpus_id is not None
                else None
            )
            owner = (
                SimpleNamespace(
                    id=str(row.owner_id),
                    display_name=row.owner_display_name,
                    full_name=row.owner_full_name,
                )
                if row.owner_id is not None
                else None
            )
            source_metadata = (
                SimpleNamespace(
                    source_kind=str(row.source_metadata_source_kind),
                    source_updated_at=row.source_metadata_source_updated_at,
                    title=row.source_metadata_title,
                    author=row.source_metadata_author,
                    authored_at=row.source_metadata_authored_at,
                    department=row.source_metadata_department,
                    document_type=row.source_metadata_document_type,
                    acl_resolved=bool(row.source_metadata_acl_resolved),
                )
                if row.source_metadata_source_kind is not None
                else None
            )
            file = SimpleNamespace(
                id=str(row.id),
                filename=str(row.filename),
                content_type=str(row.content_type),
                size_bytes=int(row.size_bytes),
                visibility=str(row.visibility),
                folder_id=row.folder_id,
                corpus_id=row.corpus_id,
                owner_id=str(row.owner_id),
                updated_at=row.updated_at,
                extraction_status=str(row.extraction_status),
                extraction_content_checksum=str(row.extraction_content_checksum),
                extraction_text=str(row.extraction_text),
                extraction_metadata=dict(row.extraction_metadata or {}),
                retrieval_partition_id=str(row.file_partition_id),
                corpus=corpus,
                owner=owner,
                source_metadata=source_metadata,
            )
            projection_version = int(row.projection_version)
            search_document = dict(build_file_search_document(file=file))
            search_document.update(
                {
                    "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
                    "retrieval_partition_id": str(row.file_partition_id),
                    "projection_version": projection_version,
                }
            )
            rag_projection = build_file_rag_projection(
                file=file,
                artifact=artifact,
            ).model_copy(
                update={
                    "retrieval_partition_id": str(row.file_partition_id),
                    "projection_version": projection_version,
                }
            )
            if not rag_projection.chunks:
                raise ValueError("Files source projection has no chunks")
        except (TypeError, ValueError):
            unavailable_count += 1
            continue
        identity = _projection_identity_bytes(
            resource_id=str(row.id),
            retrieval_partition_id=str(row.file_partition_id),
            projection_version=int(row.projection_version),
        )
        identity_digest.update(identity)
        artifact_digest.update(identity)
        artifact_digest.update(str(row.extraction_content_checksum).encode("ascii"))
        artifact_digest.update(b"\n")
        assert acl_envelope is not None
        acl_envelope_digest.add(_canonical_json_bytes(acl_envelope))
        search_document_id = canonical_search_document_id(
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=str(row.id),
        )
        opensearch_projection_digest.add(
            opensearch_projection_contract_bytes(
                document_id=search_document_id,
                document=search_document,
            )
        )
        for chunk in rag_projection.chunks:
            point_id = canonical_vector_point_id(
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id=str(row.id),
                chunk_id=chunk.chunk_id,
            )
            qdrant_projection_digest.add(
                qdrant_projection_contract_bytes(
                    point_id=point_id,
                    payload=qdrant_payload_from_record(
                        RagVectorRecord(
                            chunk_id=chunk.chunk_id,
                            text=chunk.text,
                            summary=chunk.summary,
                            projection=rag_projection,
                            metadata=dict(chunk.metadata),
                        ),
                        partitioned_generation=True,
                    ),
                )
            )
            qdrant_record_count += 1
        resource_count += 1
    return FilesSourceProjectionSnapshot(
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
        resource_count=resource_count,
        identity_sha256=identity_digest.hexdigest(),
        artifact_sha256=artifact_digest.hexdigest(),
        unsupported_count=unsupported_count,
        unavailable_count=unavailable_count,
        acl_envelope_sha256=acl_envelope_digest.hexdigest(),
        qdrant_record_count=qdrant_record_count,
        opensearch_projection_sha256=opensearch_projection_digest.hexdigest(),
        qdrant_projection_sha256=qdrant_projection_digest.hexdigest(),
    )


def _source_acl_envelope(row: SimpleNamespace) -> dict[str, object] | None:
    try:
        partition_id = str(row.file_partition_id or "").strip()
        partition_metadata_version = int(row.partition_metadata_version)
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        not partition_id
        or str(row.partition_source_namespace or "") != "files"
        or str(row.partition_state or "") != RetrievalPartitionState.ACTIVE.value
        or partition_metadata_version < 1
        or row.partition_candidate_user_id is not None
    ):
        return None

    corpus_id = str(row.corpus_id or "").strip() or None
    if corpus_id is None:
        if (
            not bool(row.partition_is_default_ingest)
            or str(row.partition_candidate_scope_kind or "") != "company"
        ):
            return None
        corpus_envelope: dict[str, object] | None = None
    else:
        try:
            corpus_metadata_version = int(row.corpus_metadata_version)
        except (TypeError, ValueError):
            return None
        scope_kind = str(row.corpus_access_scope_kind or "")
        if (
            scope_kind not in {"company"}
            or corpus_metadata_version < 1
            or corpus_metadata_version != partition_metadata_version
            or str(row.corpus_partition_id or "") != partition_id
            or bool(row.partition_is_default_ingest)
            or str(row.partition_candidate_scope_kind or "") != scope_kind
        ):
            return None
        corpus_envelope = {
            "corpus_id": corpus_id,
            "metadata_version": corpus_metadata_version,
            "access_scope_kind": scope_kind,
            "source_managed": bool(row.corpus_source_managed),
            "authorization_mode": str(row.corpus_authorization_mode or "cohort"),
            "source_acl_resolved": (
                bool(row.source_metadata_acl_resolved)
                if row.source_metadata_source_kind is not None
                else None
            ),
        }

    return {
        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
        "resource_id": str(row.id),
        "retrieval_partition_id": partition_id,
        "source": {
            "owner_id": str(row.owner_id or ""),
            "visibility": str(row.visibility or ""),
        },
        "corpus": corpus_envelope,
        "partition": {
            "metadata_version": partition_metadata_version,
            "candidate_scope_kind": str(row.partition_candidate_scope_kind),
            "candidate_user_id": row.partition_candidate_user_id,
            "state": str(row.partition_state),
            "is_default_ingest": bool(row.partition_is_default_ingest),
        },
    }


def projection_inventory_identity_sha256(
    identities: set[tuple[str, str, int]],
) -> str:
    digest = hashlib.sha256()
    for resource_id, partition_id, version in sorted(identities):
        digest.update(
            _projection_identity_bytes(
                resource_id=resource_id,
                retrieval_partition_id=partition_id,
                projection_version=version,
            )
        )
    return digest.hexdigest()


def _projection_identity_bytes(
    *,
    resource_id: str,
    retrieval_partition_id: str,
    projection_version: int,
) -> bytes:
    return (
        json.dumps(
            [
                FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id,
                retrieval_partition_id,
                projection_version,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _inventory_details(inventory: FilesPhysicalProjectionInventory) -> dict[str, object]:
    return {
        "resource_count": inventory.resource_count,
        "record_count": inventory.record_count,
        "identity_sha256": inventory.identity_sha256,
        "content_sha256": inventory.content_sha256,
        "config_sha256": inventory.config_sha256,
        "physical_id": inventory.physical_id,
        "projection_sha256": inventory.projection_sha256,
    }


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "FilesBackendPairInspection",
    "FilesGenerationBackends",
    "FilesGenerationBaselineMode",
    "FilesGenerationError",
    "FilesGenerationPairSpec",
    "FilesGenerationRunResult",
    "FilesGenerationRunner",
    "FilesPhysicalProjectionInventory",
    "FilesSourceProjectionSnapshot",
    "ProjectionContractDigest",
    "load_files_source_snapshot",
    "opensearch_projection_contract_bytes",
    "projection_inventory_identity_sha256",
    "qdrant_projection_contract_bytes",
]
