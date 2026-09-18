from __future__ import annotations

from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_workload(
        workload_id="chatbot",
        owner_domain="ai",
        required_capabilities=("chat", "tool_calling"),
        task_kind="chatbot",
        default_route="local",
        description="Interactive chat — user-facing",
        app_ids=("chatbot",),
    )
