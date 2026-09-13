from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.external_gateway import (
    AiExternalCapabilityExecution,
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    begin_external_capability,
)
from open_work_hub_api.domains.ai.gateway import (
    resolve_llm_workload_route,
    stream_llm,
    LlmWorkloadContext,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    ResolvedLlmWorkloadRoute,
)
from open_work_hub_api.domains.web_search import WEB_SEARCH_WORKLOAD_IDS
from open_work_hub_api.domains.web_search.schemas import (
    WebSearchAnswerResponse,
    WebSearchUsage,
    WebSearchResult,
)

SYSTEM_PROMPT = """\
You are a web search assistant for Open Work Hub.

Use the Hermes web_search and web_extract tools whenever the user's request needs current,
changing, or externally verifiable public information. Answer in the user's
language. Be concise, but include enough context to make the answer useful.
When search results support the answer, preserve source attribution through
citations.
"""

SYSTEM_PROMPTS_BY_PROFILE = {
    "general": SYSTEM_PROMPT,
}


class WebSearchConfigurationError(RuntimeError):
    pass


class WebSearchGenerationError(RuntimeError):
    pass


class WebSearchPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebSearchAnswerDelta:
    text: str


@dataclass(frozen=True)
class WebSearchAnswerComplete:
    response: WebSearchAnswerResponse


@dataclass(frozen=True)
class WebSearchExternalAppProfile:
    app_id: str
    profile_id: str
    task_kind: str = "web_search"
    capability: str = "web_search"
    provider: str = "anthropic"


@dataclass(frozen=True)
class PreparedWebSearchExecution:
    settings: Settings
    workload_id: str
    route: ResolvedLlmWorkloadRoute
    external_execution: AiExternalCapabilityExecution
    provider_question: str
    conversation_id: str | None = None


WEB_SEARCH_EXTERNAL_APP_PROFILES: tuple[WebSearchExternalAppProfile, ...] = (
    WebSearchExternalAppProfile(app_id="web-search", profile_id="general"),
)


def iter_web_search_external_app_profiles() -> tuple[WebSearchExternalAppProfile, ...]:
    return WEB_SEARCH_EXTERNAL_APP_PROFILES


def prepare_web_search_execution(
    *,
    question: str,
    max_uses: int = 5,
    profile_id: str = "general",
    settings: Settings | None = None,
    app_id: str,
    actor_user_id: str | None,
    principal_kind: str = "user",
    principal_id: str | None = None,
    source: str = "api.web_search",
    conversation_id: str | None = None,
    db: Session,
) -> PreparedWebSearchExecution:
    resolved_settings = settings or get_settings()
    workload_id = WEB_SEARCH_WORKLOAD_IDS.get(profile_id, WEB_SEARCH_WORKLOAD_IDS["general"])
    try:
        route = resolve_llm_workload_route(workload_id, db)
    except AiModelSettingsError as exc:
        raise WebSearchConfigurationError("Web search LLM route is not configured.") from exc
    _validate_web_search_route(route)
    try:
        external_execution = begin_external_capability(
            AiExternalCapabilityRequest(
                source=source,
                actor_user_id=actor_user_id,
                principal_kind=principal_kind,
                principal_id=principal_id,
                task_kind=route.workload.task_kind,
                capability="web_search",
                provider="anthropic",
                app=app_id,
                input_texts=[question],
                metadata={
                    "app_id": app_id,
                    "profile_id": profile_id,
                    "max_uses": max_uses,
                    "workload_id": workload_id,
                    "route": route.route,
                },
                conversation_id=conversation_id,
            ),
            settings=resolved_settings,
            db=db,
        )
    except AiExternalCapabilityPolicyViolation as exc:
        raise WebSearchPolicyError(exc.reason_code) from exc
    provider_question = external_execution.sanitized_text(fallback=question)
    return PreparedWebSearchExecution(
        settings=resolved_settings,
        workload_id=workload_id,
        route=route,
        external_execution=external_execution,
        provider_question=provider_question,
        conversation_id=conversation_id,
    )


async def stream_web_search_answer(
    *,
    question: str,
    max_uses: int = 5,
    profile_id: str = "general",
    conversation_id: str | None = None,
    db: Session | None = None,
    prepared_execution: PreparedWebSearchExecution,
) -> AsyncIterator[WebSearchAnswerDelta | WebSearchAnswerComplete]:
    if db is None:
        raise WebSearchConfigurationError(
            "Registered Hermes execution requires a database session."
        )
    gateway_execution = prepared_execution.external_execution
    identity = gateway_execution.request
    output = None
    usage = {}
    model = prepared_execution.route.model_key
    try:
        async for chunk, _decision, config in stream_llm(
            prepared_execution.workload_id,
            LlmWorkloadContext(
                source=identity.source,
                actor_user_id=identity.actor_user_id,
                principal_kind=identity.principal_kind,
                principal_id=identity.principal_id,
                app_id=identity.app,
                native_tool_limit=max_uses,
            ),
            db,
            messages=[
                {
                    "role": "system",
                    "content": _system_prompt_for_profile(profile_id)
                    + "\nSearch/extract tool calls are bounded by the requested budget. Submit an answer with verified source URLs and citation markers.",
                },
                {"role": "user", "content": prepared_execution.provider_question},
            ],
            output_schema=WebSearchResult.model_json_schema(),
            conversation_id=prepared_execution.conversation_id or conversation_id,
        ):
            model = config.default_model
            if chunk.usage:
                usage = chunk.usage
            if chunk.structured_output is not None:
                output = WebSearchResult.model_validate(chunk.structured_output)
        if output is None:
            raise WebSearchGenerationError("Hermes did not submit a valid web search result.")
        gateway_execution.record_success(
            usage=usage, metadata={"model": model, "workload_id": prepared_execution.workload_id}
        )
    except (asyncio.CancelledError, GeneratorExit):
        gateway_execution.record_cancelled()
        raise
    except Exception as exc:
        gateway_execution.record_error(exc)
        raise WebSearchGenerationError("Hermes web search failed.") from exc
    response = WebSearchAnswerResponse(
        query=question,
        answer=output.answer,
        citations=output.citations,
        model=model,
        usage=WebSearchUsage(
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens")
        ),
        conversation_id=prepared_execution.conversation_id or conversation_id,
    )
    yield WebSearchAnswerDelta(text=response.answer)
    yield WebSearchAnswerComplete(response=response)


def format_answer_for_history(response: WebSearchAnswerResponse) -> str:
    lines = [response.answer.strip()]
    if response.citations:
        lines.extend(["", "**Sources**"])
        for index, citation in enumerate(response.citations, start=1):
            title = _escape_markdown(citation.title or citation.url)
            lines.append(f"{index}. [{title}]({citation.url})")
            if citation.cited_text:
                lines.append(f"   {_escape_markdown(citation.cited_text)}")
    return "\n".join(line for line in lines if line is not None).strip()


def _escape_markdown(value: str) -> str:
    return value.replace("`", "\\`").replace("*", "\\*").replace("_", "\\_").replace("~", "\\~")


def _validate_web_search_route(route: ResolvedLlmWorkloadRoute) -> None:
    if route.route != "external":
        raise WebSearchConfigurationError("Web search requires an external LLM route.")
    if route.provider_id != "anthropic":
        raise WebSearchConfigurationError("Web search requires the Anthropic provider.")
    if not route.model_key.strip():
        raise WebSearchConfigurationError("Anthropic model is not configured.")
    if not route.endpoint_url.strip():
        raise WebSearchConfigurationError("Anthropic endpoint is not configured.")
    api_key = route.api_key.get_secret_value() if route.api_key is not None else ""
    if not api_key.strip():
        raise WebSearchConfigurationError("Anthropic API key is not configured.")


def _system_prompt_for_profile(profile_id: str) -> str:
    return SYSTEM_PROMPTS_BY_PROFILE.get(profile_id, SYSTEM_PROMPT)
