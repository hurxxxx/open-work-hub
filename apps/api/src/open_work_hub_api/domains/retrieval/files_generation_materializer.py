from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, sessionmaker, undefer

from open_work_hub_api.domains.document_processing.contracts import EvidenceBlock
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.rag_projection import (
    FileExtractionArtifact,
    build_file_rag_projection,
)
from open_work_hub_api.domains.files.rag_sync import capture_file_retrieval_event_watermark
from open_work_hub_api.domains.files.search_projection import load_file_search_document
from open_work_hub_api.domains.rag.contracts import RagScopeKind
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.rag.runtime import build_partitioned_rag_projection_service
from open_work_hub_api.domains.rag.service import RagService
from open_work_hub_api.domains.retrieval.files_generation_runner import (
    FilesGenerationMaterializationBatch,
    FilesGenerationPairSpec,
    FilesGenerationRuntimeSettings,
)
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionChangeKind,
    RetrievalProjectionDesiredState,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.search.backend_contracts import PartitionedKeywordGenerationClient
from open_work_hub_api.domains.search.backend_factory import (
    build_partitioned_keyword_search_client,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.search.schemas import SearchEntityType
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)

KeywordClientFactory = Callable[[str], PartitionedKeywordGenerationClient]
RagServiceFactory = Callable[[str], RagService]


class FilesCachedProjectionMaterializer:
    """Populate a non-active generation from persisted extraction artifacts.

    It never opens object storage and never invokes parser or OCR code. Dense
    vectors are embedded once when the target collection does not already have
    the current projection. Every write is fenced by the current source head;
    the caller must additionally keep source writers and normal workers stopped.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: FilesGenerationRuntimeSettings,
        keyword_client_factory: KeywordClientFactory | None = None,
        rag_service_factory: RagServiceFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._keyword_client_factory: KeywordClientFactory = keyword_client_factory or (
            lambda physical_name: _require_partitioned_keyword_generation_client(
                build_partitioned_keyword_search_client(
                    settings,
                    physical_index_name=physical_name,
                )
            )
        )
        self._rag_service_factory = rag_service_factory or (
            lambda collection: build_partitioned_rag_projection_service(
                settings,
                collection=collection,
            )
        )

    def materialize_batch(
        self,
        *,
        spec: FilesGenerationPairSpec,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
    ) -> FilesGenerationMaterializationBatch:
        events, has_more = self._events(
            after_event_sequence=after_event_sequence,
            through_event_sequence=through_event_sequence,
            limit=limit,
        )
        keyword_client = _require_partitioned_keyword_generation_client(
            self._keyword_client_factory(spec.opensearch_physical_name)
        )
        rag_service = self._rag_service_factory(spec.qdrant_physical_name)
        keyword_succeeded = 0
        vector_succeeded = 0
        for event_sequence in events:
            outcome = self._materialize_event(
                event_sequence=event_sequence,
                keyword_client=keyword_client,
                rag_service=rag_service,
                spec=spec,
            )
            if outcome is None:
                continue
            keyword_succeeded += 1
            vector_succeeded += 1

        complete = not has_more
        if complete:
            keyword_client.refresh_partitioned_index()
        next_event_sequence = events[-1] if events else through_event_sequence
        with self._session_factory() as db:
            current = capture_file_retrieval_event_watermark(db)
            keyword_remaining, vector_remaining = _outstanding_file_projection_jobs(db)
        return FilesGenerationMaterializationBatch(
            target_event_sequence=through_event_sequence,
            next_event_sequence=next_event_sequence,
            scanned_events=len(events),
            keyword_succeeded=keyword_succeeded,
            vector_succeeded=vector_succeeded,
            complete=complete,
            caught_up=(
                complete
                and current == through_event_sequence
                and keyword_remaining == 0
                and vector_remaining == 0
            ),
            keyword_remaining=keyword_remaining,
            vector_remaining=vector_remaining,
        )

    def inspect_reconciliation(self, *, through_event_sequence: int) -> object:
        with self._session_factory() as db:
            current = capture_file_retrieval_event_watermark(db)
            keyword_remaining, vector_remaining = _outstanding_file_projection_jobs(db)
        return _MaterializationReconciliationStatus(
            target_event_sequence=through_event_sequence,
            current_event_sequence=current,
            keyword_remaining=keyword_remaining,
            vector_remaining=vector_remaining,
            caught_up=(
                current == through_event_sequence
                and keyword_remaining == 0
                and vector_remaining == 0
            ),
        )

    def _events(
        self,
        *,
        after_event_sequence: int,
        through_event_sequence: int,
        limit: int,
    ) -> tuple[list[int], bool]:
        with self._session_factory() as db:
            rows = list(
                db.scalars(
                    select(RetrievalProjectionEvent.event_sequence)
                    .where(
                        RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RetrievalProjectionEvent.event_sequence > after_event_sequence,
                        RetrievalProjectionEvent.event_sequence <= through_event_sequence,
                    )
                    .order_by(RetrievalProjectionEvent.event_sequence.asc())
                    .limit(limit + 1)
                )
            )
        return [int(value) for value in rows[:limit]], len(rows) > limit

    def _materialize_event(
        self,
        *,
        event_sequence: int,
        keyword_client: PartitionedKeywordGenerationClient,
        rag_service: RagService,
        spec: FilesGenerationPairSpec,
    ) -> str | None:
        with self._session_factory() as db:
            event = db.get(RetrievalProjectionEvent, event_sequence)
            if event is None or event.resource_type != FILE_MANAGER_FILE_RESOURCE_TYPE:
                raise RuntimeError("Files materialization event is missing")
            head = db.get(
                RetrievalProjectionHead,
                (FILE_MANAGER_FILE_RESOURCE_TYPE, event.resource_id),
            )
            if not _event_matches_head(event=event, head=head):
                return None
            if event.desired_state == RetrievalProjectionDesiredState.DELETED.value:
                self._delete_projection(
                    db,
                    event=event,
                    keyword_client=keyword_client,
                    rag_service=rag_service,
                    spec=spec,
                )
                _resolve_fenced_projection_jobs(db, event=event)
                db.commit()
                return "deleted"
            file, artifact = _load_cached_file_artifact(db, event=event)
            document = load_file_search_document(db, event.resource_id)
            if document is None:
                raise RuntimeError("Cached Files keyword projection is unavailable")
            projection = build_file_rag_projection(
                file=file,
                artifact=artifact,
            ).model_copy(
                update={
                    "retrieval_partition_id": str(event.retrieval_partition_id),
                    "projection_version": int(event.projection_version),
                }
            )
            outcome = str(
                keyword_client.upsert_partitioned_document(
                    {
                        **document,
                        "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
                        "retrieval_partition_id": str(event.retrieval_partition_id),
                        "projection_version": int(event.projection_version),
                    }
                )
            )
            if outcome == "superseded":
                raise RuntimeError("Physical keyword generation is ahead of the source head")

            def require_current_head() -> None:
                db.expire_all()
                current = db.scalar(
                    select(RetrievalProjectionHead)
                    .where(
                        RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                        RetrievalProjectionHead.resource_id == event.resource_id,
                    )
                    .with_for_update()
                )
                if not _event_matches_head(event=event, head=current):
                    raise RuntimeError("Files projection head changed during materialization")

            rag_service.sync_projection_with_fence(
                projection,
                collection=spec.qdrant_physical_name,
                before_vector_write=require_current_head,
            )
            _resolve_fenced_projection_jobs(db, event=event)
            db.commit()
            return "upserted"

    @staticmethod
    def _delete_projection(
        db: Session,
        *,
        event: RetrievalProjectionEvent,
        keyword_client: PartitionedKeywordGenerationClient,
        rag_service: RagService,
        spec: FilesGenerationPairSpec,
    ) -> None:
        outcome = str(
            keyword_client.delete_partitioned_document(
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id=event.resource_id,
                projection_version=int(event.projection_version),
            )
        )
        if outcome == "superseded":
            raise RuntimeError("Physical keyword generation is ahead of the source head")
        partition = db.get(RetrievalPartition, event.retrieval_partition_id)
        if partition is None or partition.source_namespace != "files":
            raise RuntimeError("Files materialization partition is unavailable")
        scope_kind = RagScopeKind(partition.candidate_scope_kind)
        rag_service.delete_projection(
            scope_kind=scope_kind,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=event.resource_id,
            collection=spec.qdrant_physical_name,
            retrieval_partition_id=str(event.retrieval_partition_id),
        )


@dataclass(frozen=True, slots=True)
class _MaterializationReconciliationStatus:
    target_event_sequence: int
    current_event_sequence: int
    keyword_remaining: int
    vector_remaining: int
    caught_up: bool


def _require_partitioned_keyword_generation_client(
    candidate: object,
) -> PartitionedKeywordGenerationClient:
    if not isinstance(candidate, PartitionedKeywordGenerationClient):
        raise RuntimeError(
            "Files materialization requires a complete partitioned keyword generation client"
        )
    if not all(
        callable(method)
        for method in (
            candidate.upsert_partitioned_document,
            candidate.delete_partitioned_document,
            candidate.refresh_partitioned_index,
        )
    ):
        raise RuntimeError(
            "Files materialization requires a complete partitioned keyword generation client"
        )
    return candidate


def _event_matches_head(
    *,
    event: RetrievalProjectionEvent,
    head: RetrievalProjectionHead | None,
) -> bool:
    return bool(
        head is not None
        and head.projection_version == event.projection_version
        and head.retrieval_partition_id == event.retrieval_partition_id
        and head.desired_state == event.desired_state
    )


def _load_cached_file_artifact(
    db: Session,
    *,
    event: RetrievalProjectionEvent,
) -> tuple[FileManagerFile, FileExtractionArtifact]:
    file = db.scalar(
        select(FileManagerFile)
        .options(
            joinedload(FileManagerFile.owner),
            joinedload(FileManagerFile.corpus),
            undefer(FileManagerFile.extraction_text),
            undefer(FileManagerFile.extraction_blocks),
            undefer(FileManagerFile.extraction_metadata),
        )
        .where(
            FileManagerFile.id == event.resource_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if (
        file is None
        or file.extraction_status != "ready"
        or not file.extraction_content_checksum
        or not file.extraction_text
        or not file.extraction_blocks
        or str(file.retrieval_partition_id) != str(event.retrieval_partition_id)
        or file.extraction_content_checksum != event.content_checksum
    ):
        raise RuntimeError("Cached Files extraction artifact is unavailable")
    try:
        blocks = [EvidenceBlock(**dict(item)) for item in file.extraction_blocks]
    except (TypeError, ValueError) as error:
        raise RuntimeError("Cached Files extraction blocks are invalid") from error
    return file, FileExtractionArtifact(
        content_checksum=file.extraction_content_checksum,
        text=file.extraction_text,
        blocks=blocks,
        metadata=dict(file.extraction_metadata or {}),
    )


def _outstanding_file_projection_jobs(db: Session) -> tuple[int, int]:
    active_statuses = ("pending", "processing")
    keyword = int(
        db.scalar(
            select(func.count())
            .select_from(SearchIndexJob)
            .where(
                SearchIndexJob.status.in_(active_statuses),
                or_(
                    SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                    SearchIndexJob.entity_type == SearchEntityType.FILE.value,
                ),
            )
        )
        or 0
    )
    vector = int(
        db.scalar(
            select(func.count())
            .select_from(RagSyncJob)
            .where(
                RagSyncJob.status.in_(active_statuses),
                RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            )
        )
        or 0
    )
    return keyword, vector


def _resolve_fenced_projection_jobs(
    db: Session,
    *,
    event: RetrievalProjectionEvent,
) -> None:
    """Audit the manual physical write against paused, fenced queue rows.

    Both backends have succeeded before this function runs. Matching current
    jobs are completed together in the caller's transaction; older fenced jobs
    are cancelled. Unfenced or inconsistent same-version jobs remain visible
    and therefore keep the queue-drain gate closed.
    """

    active_statuses = ("pending", "processing")
    search_jobs = tuple(
        db.scalars(
            select(SearchIndexJob).where(
                SearchIndexJob.status.in_(active_statuses),
                SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                SearchIndexJob.entity_id == event.resource_id,
                SearchIndexJob.projection_version.is_not(None),
            )
        ).all()
    )
    rag_jobs = tuple(
        db.scalars(
            select(RagSyncJob).where(
                RagSyncJob.status.in_(active_statuses),
                RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                RagSyncJob.resource_id == event.resource_id,
                RagSyncJob.projection_version.is_not(None),
            )
        ).all()
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    for job in (*search_jobs, *rag_jobs):
        version = int(job.projection_version or 0)
        if version < int(event.projection_version):
            job.status = "cancelled"
            job.last_error = "superseded_by_projection_head:generation_materializer"
            job.next_retry_at = None
            job.updated_at = now
            db.add(job)
            continue
        if version != int(event.projection_version):
            continue
        expected_operation = "delete"
        if event.desired_state != RetrievalProjectionDesiredState.DELETED.value:
            expected_operation = (
                "visibility_update"
                if isinstance(job, RagSyncJob)
                and event.change_kind == RetrievalProjectionChangeKind.VISIBILITY.value
                else "upsert"
            )
        if (
            job.projection_event_sequence != event.event_sequence
            or str(job.retrieval_partition_id) != str(event.retrieval_partition_id)
            or job.desired_state != event.desired_state
            or job.operation != expected_operation
        ):
            continue
        job.status = "succeeded"
        job.attempts += 1
        job.last_error = None
        job.next_retry_at = None
        job.updated_at = now
        db.add(job)


__all__ = ["FilesCachedProjectionMaterializer"]
