"""External Anthropic-backed web search assistants."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


WEB_SEARCH_WORKLOAD_IDS = {
    "general": "web_search.answer",
}


def register_ai_capabilities(registry: "AiCapabilityRegistry") -> None:
    registrations = (
        (
            "web_search.answer",
            "web_search_answer",
            "web-search",
            "Public web search answer synthesis.",
        ),
    )
    for workload_id, task_kind, app_id, description in registrations:
        catalog_key = "webSearchAnswer"
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain=app_id,
            app_id=app_id,
            description=description,
            default_route="external",
            execution_kind="chat",
            allowed_routes=("external",),
            allowed_providers=("anthropic",),
            required_capabilities=("chat",),
            model_roles=("default",),
            label_key=(
                f"admin.console.aiSecurity.modelSettings.workloadCatalog.{catalog_key}.label"
            ),
            description_key=(
                f"admin.console.aiSecurity.modelSettings.workloadCatalog.{catalog_key}.description"
            ),
            external_data=True,
        )


__all__ = ["WEB_SEARCH_WORKLOAD_IDS", "register_ai_capabilities"]
