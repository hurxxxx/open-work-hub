from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.retrieval.models import RetrievalPartition, RetrievalPartitionState
from open_work_hub_api.domains.retrieval.partitioning import (
    RetrievalPartitionConflict,
    RetrievalPartitionId,
    ensure_default_partition,
)


def ensure_native_doc_partition(db: Session, *, doc: NativeDoc) -> RetrievalPartitionId:
    """Stable search candidates for Docs; personal ownership and sharing remain source ACLs.

    Keeping the candidate partition stable makes a newly shared personal document
    discoverable without re-embedding and never grants company ownership or access.
    """
    if doc.retrieval_partition_id:
        partition = db.get(RetrievalPartition, doc.retrieval_partition_id)
        if (
            partition is None
            or partition.source_namespace != "docs"
            or not partition.is_default_ingest
            or partition.candidate_scope_kind != "company"
            or partition.candidate_user_id is not None
            or partition.state != RetrievalPartitionState.ACTIVE.value
        ):
            raise RetrievalPartitionConflict("invalid Docs retrieval partition binding")
        return RetrievalPartitionId(partition.id)
    partition = ensure_default_partition(
        db, source_namespace="docs", candidate_scope_kind="company"
    )
    doc.retrieval_partition_id = partition.id
    db.add(doc)
    return RetrievalPartitionId(partition.id)
