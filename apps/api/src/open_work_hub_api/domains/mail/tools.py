from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry
from open_work_hub_api.domains.mail import service


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ListMailMessagesArgs(_ToolArgsModel):
    query: str | None = Field(default=None, max_length=200)
    unread: bool | None = None
    starred: bool | None = None
    limit: int = Field(default=10, ge=1, le=25)


class GetMailMessageArgs(_ToolArgsModel):
    message_id: str = Field(..., min_length=1)


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="mail_summarize",
        default_policy="local_only",
        description="Local-only summarization of synced mail messages.",
        app_ids=("mail",),
    )
    registry.register_llm_task(
        task_kind="mail_reply_draft",
        default_policy="local_only",
        description="Local-only business email reply drafting.",
        app_ids=("mail",),
    )
    registry.register_tool(
        name="mail.list_messages",
        description="List the caller's personal synced mail messages.",
        owner_domain="mail",
        handler=service.tool_list_messages,
        args_model=ListMailMessagesArgs,
    )
    registry.register_tool(
        name="mail.get_message",
        description="Read one synced mail message owned by the caller.",
        owner_domain="mail",
        handler=service.tool_get_message,
        args_model=GetMailMessageArgs,
    )
