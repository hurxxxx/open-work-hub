from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.conversations.scope_registry import ConversationExperience
from open_work_hub_api.domains.meeting import service as meeting_service


class MeetingConversationScopeAdapter:
    scope_ref = "meeting"
    experience = ConversationExperience(
        owner_app_id="chatbot",
        chat_workload_id="chatbot",
    )

    def validate(
        self,
        *,
        db: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> None:
        meeting_service.load_meeting_for_participant(
            db,
            principal=principal,
            user=user,
            meeting_id=scope_resource_id,
        )

    def system_prompt(
        self,
        *,
        db: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> str:
        return meeting_service.build_meeting_scope_prompt(
            db,
            principal=principal,
            user=user,
            meeting_id=scope_resource_id,
        )


__all__ = ["MeetingConversationScopeAdapter"]
