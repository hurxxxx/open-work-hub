"""User-owned bento/slides documents and AI workload registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


BENTO_APP_ID = "bento"
BENTO_EDIT_WORKLOAD_ID = "bento.edit_presentation"
BENTO_EDIT_TASK_KIND = "bento_edit_presentation"
BENTO_GENERATE_WORKLOAD_ID = "bento.generate_presentation"
BENTO_GENERATE_TASK_KIND = "bento_generate_presentation"
BENTO_MAX_OUTPUT_TOKENS = 32_768
BENTO_PLAN_WORKLOAD_ID = "bento.plan_presentation"
BENTO_PLAN_TASK_KIND = "bento_plan_presentation"
BENTO_PLAN_MAX_OUTPUT_TOKENS = 16_384
BENTO_FIXED_RUNTIME_ADAPTER_ID = "fixed_bento_pipeline"
BENTO_CODEX_RUNTIME_ADAPTER_ID = "codex_sdk"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_workload(
        workload_id=BENTO_EDIT_WORKLOAD_ID,
        task_kind=BENTO_EDIT_TASK_KIND,
        owner_domain=BENTO_APP_ID,
        app_id=BENTO_APP_ID,
        description="Revise an existing editable bento/slides presentation from an instruction.",
        default_route="local",
        execution_kind="agent",
        allowed_routes=("local", "external"),
        allowed_providers=("openai",),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=True,
        local_max_output_tokens=BENTO_MAX_OUTPUT_TOKENS,
        external_max_output_tokens=BENTO_MAX_OUTPUT_TOKENS,
        default_runtime_adapter=BENTO_FIXED_RUNTIME_ADAPTER_ID,
        allowed_runtime_adapters=(
            BENTO_FIXED_RUNTIME_ADAPTER_ID,
            BENTO_CODEX_RUNTIME_ADAPTER_ID,
        ),
    )
    registry.register_llm_workload(
        workload_id=BENTO_GENERATE_WORKLOAD_ID,
        task_kind=BENTO_GENERATE_TASK_KIND,
        owner_domain=BENTO_APP_ID,
        app_id=BENTO_APP_ID,
        description="Generate a new editable bento/slides presentation from a user brief.",
        default_route="local",
        execution_kind="agent",
        allowed_routes=("local", "external"),
        allowed_providers=("openai",),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=True,
        local_max_output_tokens=BENTO_MAX_OUTPUT_TOKENS,
        external_max_output_tokens=BENTO_MAX_OUTPUT_TOKENS,
        default_runtime_adapter=BENTO_FIXED_RUNTIME_ADAPTER_ID,
        allowed_runtime_adapters=(
            BENTO_FIXED_RUNTIME_ADAPTER_ID,
            BENTO_CODEX_RUNTIME_ADAPTER_ID,
        ),
    )
    registry.register_llm_workload(
        workload_id=BENTO_PLAN_WORKLOAD_ID,
        task_kind=BENTO_PLAN_TASK_KIND,
        owner_domain=BENTO_APP_ID,
        app_id=BENTO_APP_ID,
        description=(
            "Plan the narrative, visual system, and slide compositions for a Bento presentation."
        ),
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local",),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=False,
        local_max_output_tokens=BENTO_PLAN_MAX_OUTPUT_TOKENS,
        external_max_output_tokens=BENTO_PLAN_MAX_OUTPUT_TOKENS,
    )


__all__ = [
    "BENTO_APP_ID",
    "BENTO_EDIT_TASK_KIND",
    "BENTO_EDIT_WORKLOAD_ID",
    "BENTO_GENERATE_TASK_KIND",
    "BENTO_GENERATE_WORKLOAD_ID",
    "BENTO_MAX_OUTPUT_TOKENS",
    "BENTO_PLAN_MAX_OUTPUT_TOKENS",
    "BENTO_PLAN_TASK_KIND",
    "BENTO_PLAN_WORKLOAD_ID",
    "register_ai_capabilities",
]
