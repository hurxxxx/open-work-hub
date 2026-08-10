from __future__ import annotations

from open_work_hub_api.domains.source_access.registry import (
    has_source_access_adapter,
    register_source_access_adapter,
)


def ensure_builtin_source_access_adapters_registered() -> None:
    from open_work_hub_api.domains.docs.source_access import NativeDocSourceAccessAdapter
    from open_work_hub_api.domains.files.source_access import FileManagerSourceAccessAdapter
    from open_work_hub_api.domains.meeting.source_access import MeetingSourceAccessAdapter
    from open_work_hub_api.domains.planner.source_access import PlannerEventSourceAccessAdapter
    from open_work_hub_api.domains.pms.source_access import PmsTaskSourceAccessAdapter

    for adapter in (
        NativeDocSourceAccessAdapter(),
        FileManagerSourceAccessAdapter(),
        MeetingSourceAccessAdapter(),
        PmsTaskSourceAccessAdapter(),
        PlannerEventSourceAccessAdapter(),
    ):
        if all(
            has_source_access_adapter(resource_type) for resource_type in adapter.resource_types
        ):
            continue
        register_source_access_adapter(adapter)


__all__ = ["ensure_builtin_source_access_adapters_registered"]
