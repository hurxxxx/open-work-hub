from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
    resolve_partitioned_files_query_runtime,
)


_SAFE_RUNTIME_FAILURE_REASONS = frozenset(
    {
        "alias_identity_mismatch",
        "backend_binding_failed",
        "generation_checkpoint_invalid",
        "generation_identity_missing",
        "generation_not_validated",
        "missing_active_generation",
        "multiple_active_generations",
        "physical_identity_mismatch",
        "release_cohort_mismatch",
        "runtime_configuration_invalid",
        "schema_version_mismatch",
        "validation_evidence_invalid",
        "validation_evidence_mismatch",
        "validation_scope_mismatch",
    }
)


class FilesRetrievalCutoverError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FilesRetrievalCutoverStatus:
    deployment_enabled: bool
    ready: bool
    release_cohort: str | None = None
    opensearch_index_present: bool = False
    qdrant_collection_present: bool = False

    def status_line(self) -> str:
        status = (
            f"status=ok deployment_enabled={int(self.deployment_enabled)} ready={int(self.ready)}"
        )
        if not self.ready:
            return status
        return (
            f"{status} release_cohort={self.release_cohort}"
            f" opensearch_index_present={int(self.opensearch_index_present)}"
            f" qdrant_collection_present={int(self.qdrant_collection_present)}"
        )


def check_files_retrieval_cutover(
    db: Session,
    *,
    settings: Settings | None = None,
    qdrant_collection_exists: Callable[[Settings, str], bool] | None = None,
) -> FilesRetrievalCutoverStatus:
    resolved_settings = settings if settings is not None else get_settings()
    if not resolved_settings.files_retrieval_enabled:
        return FilesRetrievalCutoverStatus(
            deployment_enabled=False,
            ready=False,
        )
    try:
        runtime = resolve_partitioned_files_query_runtime(
            db,
            settings=resolved_settings,
        )
    except PartitionedRetrievalRuntimeUnavailable as error:
        reason = (
            f"runtime_{error.reason}"
            if error.reason in _SAFE_RUNTIME_FAILURE_REASONS
            else "runtime_unavailable"
        )
        raise FilesRetrievalCutoverError(reason) from error
    except Exception as error:
        raise FilesRetrievalCutoverError("runtime_resolution_failed") from error

    try:
        opensearch_index_present = bool(runtime.keyword_search_client.index_exists())
    except Exception as error:
        raise FilesRetrievalCutoverError("opensearch_probe_failed") from error
    if not opensearch_index_present:
        raise FilesRetrievalCutoverError("opensearch_index_missing")

    qdrant_probe = qdrant_collection_exists or _qdrant_collection_exists
    try:
        qdrant_collection_present = bool(qdrant_probe(resolved_settings, runtime.rag_collection))
    except Exception as error:
        raise FilesRetrievalCutoverError("qdrant_probe_failed") from error
    if not qdrant_collection_present:
        raise FilesRetrievalCutoverError("qdrant_collection_missing")

    return FilesRetrievalCutoverStatus(
        deployment_enabled=True,
        ready=True,
        release_cohort=runtime.release_cohort,
        opensearch_index_present=True,
        qdrant_collection_present=True,
    )


def _qdrant_collection_exists(settings: Settings, collection: str) -> bool:
    provider = str(settings.rag_vector_index_provider or "").strip().lower()
    if provider != "qdrant":
        raise ValueError("Files retrieval cutover requires the Qdrant vector backend")
    url = str(settings.rag_qdrant_url or "").strip()
    if not url:
        raise ValueError("Files retrieval cutover requires a Qdrant URL")
    api_key = str(settings.rag_qdrant_api_key or "").strip() or None
    client = QdrantClient(url=url, api_key=api_key, timeout=5)
    try:
        return bool(client.collection_exists(collection_name=collection))
    finally:
        client.close()


__all__ = [
    "FilesRetrievalCutoverError",
    "FilesRetrievalCutoverStatus",
    "check_files_retrieval_cutover",
]
