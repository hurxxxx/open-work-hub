from __future__ import annotations

from ai_do_api.domains.source_access.registry import (
    has_source_access_adapter,
    register_source_access_adapter,
)


def ensure_builtin_source_access_adapters_registered() -> None:
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
        PmsTaskSourceAccessAdapter(),
        PlannerEventSourceAccessAdapter(),
        QnaDocumentSourceAccessAdapter(),
    ):
        if all(
            has_source_access_adapter(resource_type) for resource_type in adapter.resource_types
        ):
            continue
        register_source_access_adapter(adapter)


__all__ = ["ensure_builtin_source_access_adapters_registered"]
