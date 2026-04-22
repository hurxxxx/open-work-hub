"""RAG domain scaffolding for Phase 5."""

from aidoo_api.domains.rag.contracts import (
    RagAnswerMode,
    RagGroundedAnswer,
    RagJobStatus,
    RagProjection,
    RagQueryHit,
    RagQueryRequest,
    RagQueryResponse,
    RagSyncLane,
    RagSyncOperation,
)
from aidoo_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from aidoo_api.domains.rag.outbox import (
    enqueue_rag_sync_job,
    enqueue_rag_visibility_recompute_job,
)
from aidoo_api.domains.rag.query_service import RagGroundedAnswerSynthesizer, RagQueryService
from aidoo_api.domains.rag.service import RagService

__all__ = [
    "RagAnswerMode",
    "RagGroundedAnswer",
    "RagGroundedAnswerSynthesizer",
    "RagJobStatus",
    "RagProjection",
    "RagQueryHit",
    "RagQueryRequest",
    "RagQueryResponse",
    "RagService",
    "RagSyncJob",
    "RagSyncLane",
    "RagSyncOperation",
    "RagVisibilityRecomputeJob",
    "RagQueryService",
    "enqueue_rag_sync_job",
    "enqueue_rag_visibility_recompute_job",
]
