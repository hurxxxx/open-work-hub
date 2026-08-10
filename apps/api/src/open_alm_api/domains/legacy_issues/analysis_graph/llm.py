from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from open_alm_api.domains.ai_graph.contracts import AiGraphLlmRequest
from open_alm_api.domains.ai_graph.gateway_adapter import AiGatewayGraphAdapter
from open_alm_api.domains.ai_graph.runtime import AiGraphRuntimeContext


_JsonModel = TypeVar("_JsonModel", bound=BaseModel)
_FENCED_JSON = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)


class GraphStructuredOutputError(ValueError):
    """The model responded, but its text did not satisfy the requested schema."""


async def invoke_graph_text(
    gateway: AiGatewayGraphAdapter,
    context: AiGraphRuntimeContext,
    *,
    workload_id: str,
    messages: Sequence[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0,
) -> str:
    result = await asyncio.to_thread(
        gateway.invoke,
        AiGraphLlmRequest(
            workload_id=workload_id,
            app_id=context.app_id,
            workspace_id=context.workspace_id,
            source="worker.legacy_issues.analysis_graph",
            messages=list(messages),
            actor_user_id=context.requested_by_user_id,
            principal_kind="user",
            principal_id=context.requested_by_user_id,
            graph_run_id=context.run_id,
            conversation_id=context.conversation_id,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort="none",
            stream_reasoning=False,
        ),
    )
    return result.text.strip()


async def invoke_graph_json(
    gateway: AiGatewayGraphAdapter,
    context: AiGraphRuntimeContext,
    *,
    workload_id: str,
    messages: Sequence[dict[str, Any]],
    response_model: type[_JsonModel],
    max_tokens: int = 1_500,
) -> _JsonModel:
    text = await invoke_graph_text(
        gateway,
        context,
        workload_id=workload_id,
        messages=messages,
        max_tokens=max_tokens,
    )
    try:
        return response_model.model_validate(parse_json_object(text))
    except (TypeError, ValueError) as error:
        raise GraphStructuredOutputError(
            f"{response_model.__name__} structured output is invalid"
        ) from error


def parse_json_object(text: str) -> dict[str, Any]:
    normalized = str(text or "").strip()
    fenced = _FENCED_JSON.match(normalized)
    if fenced is not None:
        normalized = fenced.group("body").strip()
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as error:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response does not contain a JSON object") from error
        try:
            value = json.loads(normalized[start : end + 1])
        except json.JSONDecodeError as nested_error:
            raise ValueError("model response contains invalid JSON") from nested_error
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value


__all__ = [
    "GraphStructuredOutputError",
    "invoke_graph_json",
    "invoke_graph_text",
    "parse_json_object",
]
