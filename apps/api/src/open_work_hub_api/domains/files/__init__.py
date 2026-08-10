"""Simple workspace file drive domain and its registered LLM workloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


FILES_APP_ID = "files"
FILES_GROUNDED_CHAT_WORKLOAD_ID = "files.grounded_chat"
FILES_GROUNDED_CHAT_TASK_KIND = "files_grounded_chat"
FILES_RAG_QUERY_REWRITE_WORKLOAD_ID = "files.rag_query_rewrite"
FILES_RAG_QUERY_REWRITE_TASK_KIND = "files_rag_query_rewrite"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registrations = (
        (
            FILES_GROUNDED_CHAT_WORKLOAD_ID,
            FILES_GROUNDED_CHAT_TASK_KIND,
            "Answer questions using evidence retrieved from accessible Files documents.",
            8_192,
        ),
        (
            FILES_RAG_QUERY_REWRITE_WORKLOAD_ID,
            FILES_RAG_QUERY_REWRITE_TASK_KIND,
            "Rewrite a Files conversation turn into a standalone retrieval query.",
            1_024,
        ),
    )
    for workload_id, task_kind, description, max_output_tokens in registrations:
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain=FILES_APP_ID,
            app_id=FILES_APP_ID,
            description=description,
            default_route="local",
            execution_kind="chat",
            allowed_routes=("local", "external"),
            required_capabilities=("chat",),
            model_roles=("default",),
            external_data=True,
            local_max_output_tokens=max_output_tokens,
            external_max_output_tokens=max_output_tokens,
        )


__all__ = [
    "FILES_APP_ID",
    "FILES_GROUNDED_CHAT_TASK_KIND",
    "FILES_GROUNDED_CHAT_WORKLOAD_ID",
    "FILES_RAG_QUERY_REWRITE_TASK_KIND",
    "FILES_RAG_QUERY_REWRITE_WORKLOAD_ID",
    "register_ai_capabilities",
]
