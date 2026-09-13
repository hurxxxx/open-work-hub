"""Bento stage orchestration with Hermes as the sole generative runtime."""

from __future__ import annotations

from open_work_hub_api.domains.ai.agent_runtime import (
    AgentRuntimeRequest,
    AgentRuntimeResult,
    register_agent_runtime_adapter,
)
from open_work_hub_api.domains.bento import BENTO_RUNTIME_ADAPTER_ID
from open_work_hub_api.domains.bento.generation import (
    generate_bento_document_json,
    revise_bento_document_json,
)


class AgentRuntimeCancelled(RuntimeError):
    pass


class HermesBentoPipelineAdapter:
    adapter_id = BENTO_RUNTIME_ADAPTER_ID
    display_name = "Hermes"
    allowed_routes = ("local", "external")
    allowed_providers: tuple[str, ...] = ()

    def run(self, request: AgentRuntimeRequest) -> AgentRuntimeResult:
        payload = request.input_payload
        request.progress("bento.ai.planning", 20)
        if request.cancelled():
            raise AgentRuntimeCancelled()
        if payload["kind"] == "create":
            document_json, _document = generate_bento_document_json(
                payload["db"],
                actor_user_id=request.actor_user_id,
                prompt=str(payload["prompt"]),
                slide_count=int(payload["slide_count"]),
                language=payload["language"],
            )
        else:
            document_json, _document = revise_bento_document_json(
                payload["db"],
                actor_user_id=request.actor_user_id,
                prompt=str(payload["prompt"]),
                current_document_json=str(payload["current_document_json"]),
                language=payload["language"],
            )
        request.progress("bento.ai.validating", 85)
        if request.cancelled():
            raise AgentRuntimeCancelled()
        return AgentRuntimeResult(output_payload={"document_json": document_json})


_ADAPTER = HermesBentoPipelineAdapter()


def ensure_bento_agent_runtime_adapters_registered() -> None:
    register_agent_runtime_adapter(_ADAPTER)
