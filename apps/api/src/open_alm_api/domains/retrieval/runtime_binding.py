from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.rag.provider_factory import RagRuntimeSettings
from open_alm_api.domains.rag.providers import RagProviderBundle
from open_alm_api.domains.rag.query_service import RagQueryService
from open_alm_api.domains.rag.runtime import (
    PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
    build_partitioned_retrieval_candidate_query_service,
    get_partitioned_retrieval_candidate_query_service,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_alm_api.domains.retrieval.models import (
    RetrievalProjectionBackend,
    RetrievalProjectionGeneration,
    RetrievalProjectionGenerationState,
    RetrievalProjectionValidationState,
)
from open_alm_api.domains.search.backend_contracts import (
    KeywordSearchBackendSettings,
    KeywordSearchClient,
)
from open_alm_api.domains.search.backend_factory import (
    build_partitioned_keyword_search_client,
)
from open_alm_api.domains.search.index_gateway import (
    RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
)
from open_alm_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


class PartitionedRetrievalRuntimeSettings(
    KeywordSearchBackendSettings,
    RagRuntimeSettings,
    Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class PartitionedRetrievalGenerationPair:
    """Validated physical identities shared by query and realtime writers."""

    release_cohort: str
    opensearch_generation_id: str
    qdrant_generation_id: str
    opensearch_physical_name: str
    qdrant_physical_name: str
    opensearch_replay_event_sequence: int
    qdrant_replay_event_sequence: int


@dataclass(frozen=True, slots=True)
class PartitionedFilesQueryRuntime:
    """Query-only runtime bound to one validated cross-backend release cohort."""

    release_cohort: str
    opensearch_generation_id: str
    qdrant_generation_id: str
    keyword_search_client: KeywordSearchClient
    rag_query_service: RagQueryService
    rag_collection: str


class PartitionedRetrievalRuntimeUnavailable(RuntimeError):
    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Partitioned retrieval runtime is unavailable: {reason}")


def resolve_partitioned_files_query_runtime(
    db: Session,
    *,
    settings: PartitionedRetrievalRuntimeSettings | None = None,
    rag_providers: RagProviderBundle | None = None,
) -> PartitionedFilesQueryRuntime:
    """Resolve and bind the complete Files query runtime, or fail closed.

    ``generation_key`` is the shared release cohort. Both backend rows must be
    active, independently validated for that cohort, and match the physical
    identities derived from the current runtime settings. No alias or legacy
    fallback is used for query traffic.
    """

    resolved_settings = settings if settings is not None else get_settings()
    pair = resolve_active_partitioned_generation_pair(
        db,
        settings=resolved_settings,
    )
    try:
        keyword_search_client = build_partitioned_keyword_search_client(
            resolved_settings,
            physical_index_name=pair.opensearch_physical_name,
        )
        if settings is None and rag_providers is None:
            rag_query_service = get_partitioned_retrieval_candidate_query_service(
                pair.qdrant_physical_name
            )
        else:
            rag_query_service = build_partitioned_retrieval_candidate_query_service(
                resolved_settings,
                collection=pair.qdrant_physical_name,
                providers=rag_providers,
            )
    except Exception as error:
        raise PartitionedRetrievalRuntimeUnavailable(reason="backend_binding_failed") from error

    return PartitionedFilesQueryRuntime(
        release_cohort=pair.release_cohort,
        opensearch_generation_id=pair.opensearch_generation_id,
        qdrant_generation_id=pair.qdrant_generation_id,
        keyword_search_client=keyword_search_client,
        rag_query_service=rag_query_service,
        rag_collection=pair.qdrant_physical_name,
    )


def resolve_active_partitioned_generation_pair(
    db: Session,
    *,
    settings: PartitionedRetrievalRuntimeSettings | None = None,
) -> PartitionedRetrievalGenerationPair:
    """Resolve the sole validated active cross-backend physical generation.

    This function performs no backend construction. Realtime writers reuse it
    so their physical identity and schema checks cannot drift from query
    traffic. Baseline/replay tooling must bind an explicit non-active
    generation instead of calling this active selector.
    """

    resolved_settings = settings if settings is not None else get_settings()
    rows = tuple(
        db.scalars(
            select(RetrievalProjectionGeneration).where(
                RetrievalProjectionGeneration.backend.in_(
                    (
                        RetrievalProjectionBackend.OPENSEARCH.value,
                        RetrievalProjectionBackend.QDRANT.value,
                    )
                ),
                RetrievalProjectionGeneration.state
                == RetrievalProjectionGenerationState.ACTIVE.value,
            )
        ).all()
    )
    by_backend = {
        backend.value: tuple(row for row in rows if row.backend == backend.value)
        for backend in RetrievalProjectionBackend
    }
    opensearch = _exact_generation(by_backend[RetrievalProjectionBackend.OPENSEARCH.value])
    qdrant = _exact_generation(by_backend[RetrievalProjectionBackend.QDRANT.value])
    opensearch_generation_id = _required_generation_id(opensearch)
    qdrant_generation_id = _required_generation_id(qdrant)

    opensearch_cohort = _validated_release_cohort(opensearch)
    qdrant_cohort = _validated_release_cohort(qdrant)
    if opensearch_cohort != qdrant_cohort:
        raise PartitionedRetrievalRuntimeUnavailable(reason="release_cohort_mismatch")
    release_cohort = opensearch_cohort
    _require_matching_files_validation_evidence(opensearch, qdrant)

    if opensearch.schema_version != RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION:
        raise PartitionedRetrievalRuntimeUnavailable(reason="schema_version_mismatch")
    if qdrant.schema_version != PARTITIONED_RAG_GENERATION_SCHEMA_VERSION:
        raise PartitionedRetrievalRuntimeUnavailable(reason="schema_version_mismatch")

    try:
        expected_opensearch_alias = keyword_search_partitioned_index_alias(
            resolved_settings.opensearch_index_prefix
        )
        expected_qdrant_alias = resolve_partitioned_rag_collection_alias(resolved_settings)
        expected_opensearch_physical = keyword_search_partitioned_index_name(
            resolved_settings.opensearch_index_prefix,
            generation=release_cohort,
        )
        expected_qdrant_physical = resolve_partitioned_rag_collection_name(
            resolved_settings,
            generation=release_cohort,
        )
    except Exception as error:
        raise PartitionedRetrievalRuntimeUnavailable(
            reason="runtime_configuration_invalid"
        ) from error
    if (
        opensearch.alias_name != expected_opensearch_alias
        or qdrant.alias_name != expected_qdrant_alias
    ):
        raise PartitionedRetrievalRuntimeUnavailable(reason="alias_identity_mismatch")
    if (
        opensearch.physical_name != expected_opensearch_physical
        or qdrant.physical_name != expected_qdrant_physical
    ):
        raise PartitionedRetrievalRuntimeUnavailable(reason="physical_identity_mismatch")

    return PartitionedRetrievalGenerationPair(
        release_cohort=release_cohort,
        opensearch_generation_id=opensearch_generation_id,
        qdrant_generation_id=qdrant_generation_id,
        opensearch_physical_name=opensearch.physical_name,
        qdrant_physical_name=qdrant.physical_name,
        opensearch_replay_event_sequence=_required_replay_event_sequence(opensearch),
        qdrant_replay_event_sequence=_required_replay_event_sequence(qdrant),
    )


def _exact_generation(
    rows: tuple[RetrievalProjectionGeneration, ...],
) -> RetrievalProjectionGeneration:
    if not rows:
        raise PartitionedRetrievalRuntimeUnavailable(reason="missing_active_generation")
    if len(rows) != 1:
        raise PartitionedRetrievalRuntimeUnavailable(reason="multiple_active_generations")
    return rows[0]


def _validated_release_cohort(generation: RetrievalProjectionGeneration) -> str:
    if (
        generation.state != RetrievalProjectionGenerationState.ACTIVE.value
        or generation.validation_state != RetrievalProjectionValidationState.PASSED.value
        or generation.validated_at is None
    ):
        raise PartitionedRetrievalRuntimeUnavailable(reason="generation_not_validated")
    generation_key = str(generation.generation_key or "").strip()
    details = generation.validation_details
    validated_cohort = (
        str(details.get("release_cohort") or "").strip() if isinstance(details, Mapping) else ""
    )
    if not generation_key or validated_cohort != generation_key:
        raise PartitionedRetrievalRuntimeUnavailable(reason="release_cohort_mismatch")
    return generation_key


def _required_generation_id(generation: RetrievalProjectionGeneration) -> str:
    generation_id = str(generation.id or "").strip()
    if not generation_id:
        raise PartitionedRetrievalRuntimeUnavailable(reason="generation_identity_missing")
    return generation_id


def _require_matching_files_validation_evidence(
    opensearch: RetrievalProjectionGeneration,
    qdrant: RetrievalProjectionGeneration,
) -> None:
    opensearch_details = opensearch.validation_details
    qdrant_details = qdrant.validation_details
    if not isinstance(opensearch_details, Mapping) or not isinstance(
        qdrant_details, Mapping
    ):
        raise PartitionedRetrievalRuntimeUnavailable(reason="validation_evidence_invalid")
    if dict(opensearch_details) != dict(qdrant_details):
        raise PartitionedRetrievalRuntimeUnavailable(reason="validation_evidence_mismatch")
    if opensearch_details.get("included_resource_types") != [
        FILE_MANAGER_FILE_RESOURCE_TYPE
    ]:
        raise PartitionedRetrievalRuntimeUnavailable(reason="validation_scope_mismatch")


def _required_replay_event_sequence(
    generation: RetrievalProjectionGeneration,
) -> int:
    try:
        replay_event_sequence = int(generation.replay_event_sequence)
    except (TypeError, ValueError) as error:
        raise PartitionedRetrievalRuntimeUnavailable(
            reason="generation_checkpoint_invalid"
        ) from error
    if replay_event_sequence < 0:
        raise PartitionedRetrievalRuntimeUnavailable(reason="generation_checkpoint_invalid")
    return replay_event_sequence


__all__ = [
    "PartitionedFilesQueryRuntime",
    "PartitionedRetrievalGenerationPair",
    "PartitionedRetrievalRuntimeUnavailable",
    "resolve_active_partitioned_generation_pair",
    "resolve_partitioned_files_query_runtime",
]
