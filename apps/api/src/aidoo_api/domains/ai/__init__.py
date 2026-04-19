from __future__ import annotations

from aidoo_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_task(
        task_kind="chatbot",
        default_policy="local_only",
        description="Interactive chat — user-facing",
    )
    registry.register_llm_task(
        task_kind="batch_generation",
        default_policy="local_only",
        description="Long-form batch generation (reports etc.)",
    )
