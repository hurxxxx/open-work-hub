from __future__ import annotations

from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="chatbot",
        default_policy="local_only",
        description="Interactive chat — user-facing",
        app_ids=("chatbot",),
    )
    registry.register_llm_task(
        task_kind="document_translate",
        default_policy="local_only",
        description="Document translation, summarization and key extraction",
        app_ids=("document-translate",),
    )
    registry.register_llm_task(
        task_kind="draft_assist",
        default_policy="local_only",
        description="Business draft/proposal drafting assistant",
        app_ids=("drafting",),
    )
    registry.register_llm_task(
        task_kind="mail_compose",
        default_policy="local_only",
        description="Business email composition assistant",
        app_ids=("email-assistant",),
    )
    registry.register_llm_task(
        task_kind="writing_translate",
        default_policy="local_only",
        description="Re-translate edited Korean reference back to the target language",
        app_ids=("drafting",),
    )
