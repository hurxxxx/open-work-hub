from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ai_do_api.domains.ai.gateway import AiGatewayContextPack, LlmWorkloadContext


@dataclass(frozen=True)
class LegacyIssueAssistantContextRequest:
    workspace_id: str
    actor_user_id: str
    dataset_key: str
    issue_id: str
    question: str
    revision_id: str | None = None
    audit_entity_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class LegacyIssueAssistantContextBuilder(Protocol):
    def build_context_pack(
        self,
        request: LegacyIssueAssistantContextRequest,
    ) -> AiGatewayContextPack: ...


def build_legacy_issue_assistant_workload_context(
    *,
    context_request: LegacyIssueAssistantContextRequest,
    source: str = "legacy_issues.assistant",
) -> LlmWorkloadContext:
    return LlmWorkloadContext(
        workspace_id=context_request.workspace_id,
        actor_user_id=context_request.actor_user_id,
        source=source,
        app_id="legacy-issues",
    )


__all__ = [
    "LegacyIssueAssistantContextBuilder",
    "LegacyIssueAssistantContextRequest",
    "build_legacy_issue_assistant_workload_context",
]
