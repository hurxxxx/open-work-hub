from __future__ import annotations

from collections.abc import Iterable

from aidoo_api.domains.ai.internal_agent_contracts import LocalAgentResult, LocalAgentTask
from aidoo_api.domains.ai.internal_agents import (
    LocalAgentRunner,
    LocalAgentRuntimeContext,
    LocalModelAgentRunner,
    StaticLocalAgentRunner,
    ToolGatewayLocalAgentRunner,
    build_local_agent_runtime_context,
    run_local_agent_task,
    validate_local_agent_task,
)
from aidoo_api.domains.ai.runtime.agent_definitions import AgentDefinitionResolver


RUN_LOCAL_SPECIALIST_TOOL_NAME = "run_local_specialist"

LocalSpecialistRunner = LocalAgentRunner
LocalSpecialistToolContext = LocalAgentRuntimeContext
LocalLlmSpecialistRunner = LocalModelAgentRunner
LocalToolGatewaySpecialistRunner = ToolGatewayLocalAgentRunner
StaticLocalSpecialistRunner = StaticLocalAgentRunner


def build_local_specialist_tool_context(
    *,
    enabled_app_ids: Iterable[str],
    allowed_app_ids: Iterable[str] | None = None,
    available_tool_names: Iterable[str] = (),
    approval_required_tool_names: Iterable[str] = (),
    agent_definition_resolver: AgentDefinitionResolver | None = None,
) -> LocalSpecialistToolContext:
    return build_local_agent_runtime_context(
        enabled_app_ids=enabled_app_ids,
        allowed_app_ids=allowed_app_ids,
        available_tool_names=available_tool_names,
        approval_required_tool_names=approval_required_tool_names,
        agent_definition_resolver=agent_definition_resolver,
    )


def run_local_specialist(
    *,
    task: LocalAgentTask,
    context: LocalSpecialistToolContext,
    runner: LocalSpecialistRunner,
) -> LocalAgentResult:
    return run_local_agent_task(task=task, context=context, runner=runner)


def validate_local_specialist_task(
    *,
    task: LocalAgentTask,
    context: LocalSpecialistToolContext,
) -> str | None:
    return validate_local_agent_task(task=task, context=context)
