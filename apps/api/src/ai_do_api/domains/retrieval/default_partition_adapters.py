from __future__ import annotations

from ai_do_api.domains.retrieval.partition_adapter_registry import (
    has_retrieval_partition_adapter,
    register_retrieval_partition_adapter,
)


def ensure_retrieval_partition_adapters_registered() -> None:
    from ai_do_api.domains.docs.source_access import NativeDocSourceAccessAdapter
    from ai_do_api.domains.files.source_access import FileManagerSourceAccessAdapter
    from ai_do_api.domains.legacy_issues.source_access import (
        LegacyIssueRecordSourceAccessAdapter,
    )
    from ai_do_api.domains.meeting.source_access import MeetingSourceAccessAdapter
    from ai_do_api.domains.planner.source_access import PlannerEventSourceAccessAdapter
    from ai_do_api.domains.pms.source_access import PmsTaskSourceAccessAdapter
    from ai_do_api.domains.qna.source_access import QnaDocumentSourceAccessAdapter

    for adapter in (
        NativeDocSourceAccessAdapter(),
        FileManagerSourceAccessAdapter(),
        LegacyIssueRecordSourceAccessAdapter(),
        MeetingSourceAccessAdapter(),
        PlannerEventSourceAccessAdapter(),
        PmsTaskSourceAccessAdapter(),
        QnaDocumentSourceAccessAdapter(),
    ):
        if has_retrieval_partition_adapter(adapter.adapter_id):
            continue
        register_retrieval_partition_adapter(adapter)


__all__ = ["ensure_retrieval_partition_adapters_registered"]
