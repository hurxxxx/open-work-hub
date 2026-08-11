from __future__ import annotations

from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="chatbot",
        default_policy="local_only",
        description="Interactive chat — user-facing",
        app_ids=("chatbot",),
    )
