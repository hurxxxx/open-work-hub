from __future__ import annotations

from ai_do_api.domains.source_access.targets import (
    TargetAccessAdapter,
    TargetAccessProjection,
    TargetRef,
    ensure_builtin_target_access_adapters_registered,
    get_target_access_adapter,
    has_target_access_adapter,
    project_target_access,
    register_target_access_adapter,
    reset_target_access_adapters,
    resolve_target_label,
    target_access_allowed,
    target_access_app_ids,
)
from ai_do_api.domains.source_access.policy import (
    SourceAclPolicy,
    can_read_meeting,
    can_read_native_doc,
    can_read_planner_event,
    can_read_pms_task,
    can_read_resource,
)
from ai_do_api.domains.source_access.registry import (
    SourceAccessAdapter,
    get_source_access_adapter,
    get_source_access_adapters,
    register_source_access_adapter,
)

__all__ = [
    "SourceAclPolicy",
    "SourceAccessAdapter",
    "TargetAccessAdapter",
    "TargetAccessProjection",
    "TargetRef",
    "can_read_meeting",
    "can_read_native_doc",
    "can_read_planner_event",
    "can_read_pms_task",
    "can_read_resource",
    "ensure_builtin_target_access_adapters_registered",
    "get_target_access_adapter",
    "project_target_access",
    "get_source_access_adapter",
    "get_source_access_adapters",
    "has_target_access_adapter",
    "register_target_access_adapter",
    "register_source_access_adapter",
    "reset_target_access_adapters",
    "resolve_target_label",
    "target_access_app_ids",
    "target_access_allowed",
]
