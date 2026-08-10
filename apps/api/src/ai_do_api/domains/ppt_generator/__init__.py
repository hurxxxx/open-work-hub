"""PPT generation workload registrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_do_api.domains.ai.registry import AiCapabilityRegistry


PPT_RESEARCH_WORKLOAD_ID = "ppt.research"
PPT_DESIGN_WORKLOAD_ID = "ppt.design"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_workload(
        workload_id=PPT_DESIGN_WORKLOAD_ID,
        task_kind="ppt_design",
        owner_domain="ppt-generator",
        app_id="ppt-assistant",
        description="PPT deck layout and content design.",
        default_route="local",
        allowed_routes=("local", "external"),
        allowed_providers=("anthropic",),
        required_capabilities=("chat",),
        label_key=("admin.console.aiSecurity.modelSettings.workloadCatalog.pptDesign.label"),
        description_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog.pptDesign.description"
        ),
        external_data=True,
    )
    registry.register_llm_workload(
        workload_id=PPT_RESEARCH_WORKLOAD_ID,
        task_kind="ppt_research",
        owner_domain="ppt-generator",
        app_id="ppt-assistant",
        description="Public web research used to enrich PPT content.",
        default_route="external",
        allowed_routes=("external",),
        allowed_providers=("anthropic",),
        required_capabilities=("chat",),
        label_key=("admin.console.aiSecurity.modelSettings.workloadCatalog.pptResearch.label"),
        description_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog.pptResearch.description"
        ),
        external_data=True,
    )


__all__ = [
    "PPT_DESIGN_WORKLOAD_ID",
    "PPT_RESEARCH_WORKLOAD_ID",
    "register_ai_capabilities",
]
