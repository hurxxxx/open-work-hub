from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalPartitionCandidateScope,
    RetrievalPartitionState,
)
from open_work_hub_api.domains.retrieval.partitioning import (
    RetrievalPartitionConflict,
    RetrievalPartitionId,
    RetrievalPartitionUnbound,
    ensure_default_partition,
)


def ensure_native_doc_partition(
    db: Session,
    *,
    doc: NativeDoc,
) -> RetrievalPartitionId:
    """Bind a native doc once to its workspace-owned default partition."""

    current_partition_id = str(doc.retrieval_partition_id or "").strip()
    if current_partition_id:
        partition = db.get(RetrievalPartition, current_partition_id)
        if partition is None:
            raise RetrievalPartitionUnbound(
                "native doc retrieval partition binding points to a missing partition: "
                f"{current_partition_id}"
            )
        if not _is_workspace_default_partition_for_doc(partition, doc=doc):
            raise RetrievalPartitionConflict(
                "native doc retrieval partition binding is not the active Docs workspace "
                f"default for workspace {doc.workspace_id}: {current_partition_id}"
            )
        return RetrievalPartitionId(current_partition_id)

    partition = ensure_default_partition(
        db,
        source_namespace="docs",
        candidate_scope_kind="workspace",
        workspace_id=doc.workspace_id,
    )
    doc.retrieval_partition_id = partition.id
    db.add(doc)
    return RetrievalPartitionId(partition.id)


def _is_workspace_default_partition_for_doc(
    partition: RetrievalPartition,
    *,
    doc: NativeDoc,
) -> bool:
    return (
        partition.source_namespace == "docs"
        and partition.managed_workspace_id == doc.workspace_id
        and partition.candidate_scope_kind == RetrievalPartitionCandidateScope.WORKSPACE.value
        and partition.candidate_workspace_id == doc.workspace_id
        and partition.candidate_user_id is None
        and partition.state == RetrievalPartitionState.ACTIVE.value
        and partition.is_default_ingest is True
    )


__all__ = ["ensure_native_doc_partition"]
