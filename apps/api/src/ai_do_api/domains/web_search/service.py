from __future__ import annotations

import inspect
import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.core.settings import Settings, get_settings
from ai_do_api.domains.ai.gateway import resolve_llm_workload_route
from ai_do_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    ResolvedLlmWorkloadRoute,
)
from ai_do_api.domains.ai.external_gateway import (
    AiExternalCapabilityExecution,
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    begin_external_capability,
)
from ai_do_api.domains.web_search.schemas import (
    WebSearchAnswerResponse,
    WebSearchCitation,
    WebSearchUsage,
)
from ai_do_api.domains.web_search import WEB_SEARCH_WORKLOAD_IDS


WEB_SEARCH_TOOL_TYPE = "web_search_20250305"

SYSTEM_PROMPT = """\
You are a web search assistant for AI-DO.

Use Anthropic's web_search tool whenever the user's request needs current,
changing, or externally verifiable public information. Answer in the user's
language. Be concise, but include enough context to make the answer useful.
When search results support the answer, preserve source attribution through
citations.
"""

RESEARCH_TRENDS_SYSTEM_PROMPT = """\
You are a research and technology trend analyst for AI-DO.

Use Anthropic's web_search tool to investigate papers, preprints, academic
metadata pages, reputable technical reports, standards bodies, and vendor
engineering publications when they are relevant. Prefer primary or traceable
sources such as DOI landing pages, publisher pages, arXiv, Semantic Scholar,
OpenAlex, Crossref, official research institutes, and recognized conferences.

Answer in the user's language. Structure the response for engineering work:
1. Key takeaways
2. Important papers or technical sources
3. Technology trend and maturity
4. Potential AI-DO use cases
5. Limitations, uncertainties, and verification needs
6. Suggested next actions

Clearly distinguish facts from your inference. Preserve source attribution
through citations whenever search results support the answer.
"""

STANDARDS_MONITOR_SYSTEM_PROMPT = """\
You are a standards and regulatory monitoring analyst for AI-DO.

Use Anthropic's web_search tool to investigate official standards,
regulations, agency notices, public consultation pages, and credible legal or
technical summaries. Prefer official sources such as ISO, IEC, SAE, UNECE,
EU institutions, NHTSA, EPA, OSHA, ECHA, KATS, KS, Korean ministries, and
recognized industry bodies when they are relevant.

Answer in the user's language. Structure the response for operational use:
1. Executive summary
2. Confirmed standards or regulatory changes
3. Impact on products, engineering, quality, purchasing, or compliance
4. Required or recommended actions
5. Effective dates, deadlines, and monitoring cadence
6. Open questions and sources to verify

Do not provide legal advice. Clearly distinguish confirmed requirements from
interpretation or inference. Preserve source attribution through citations
whenever search results support the answer.
"""

SYSTEM_PROMPTS_BY_PROFILE = {
    "general": SYSTEM_PROMPT,
    "research-trends": RESEARCH_TRENDS_SYSTEM_PROMPT,
    "standards-monitor": STANDARDS_MONITOR_SYSTEM_PROMPT,
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
    WebSearchExternalAppProfile(app_id="research-trends", profile_id="research-trends"),
    WebSearchExternalAppProfile(app_id="standards-monitor", profile_id="standards-monitor"),
)


def iter_web_search_external_app_profiles() -> tuple[WebSearchExternalAppProfile, ...]:
    return WEB_SEARCH_EXTERNAL_APP_PROFILES


AnthropicClientFactory = Callable[[ResolvedLlmWorkloadRoute], Any]


def prepare_web_search_execution(
    *,
    question: str,
    max_uses: int = 5,
    profile_id: str = "general",
    settings: Settings | None = None,
    workspace_id: str,
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
                workspace_id=workspace_id,
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
    client_factory: AnthropicClientFactory | None = None,
    conversation_id: str | None = None,
    db: Session | None = None,
    prepared_execution: PreparedWebSearchExecution,
) -> AsyncIterator[WebSearchAnswerDelta | WebSearchAnswerComplete]:
    del db  # The database route has already been resolved by prepare_web_search_execution.
    _validate_web_search_route(prepared_execution.route)
    resolved_settings = prepared_execution.settings
    gateway_execution = prepared_execution.external_execution
    route = prepared_execution.route
    client = (
        client_factory(route)
        if client_factory is not None
        else _anthropic_client_for_route(route, settings=resolved_settings)
    )
    request = _anthropic_web_search_request(
        question=prepared_execution.provider_question,
        max_uses=max_uses,
        profile_id=profile_id,
        model=route.model_key,
        max_tokens=route.max_output_tokens,
    )
    final_message: Any | None = None
    try:
        async with client.messages.stream(**request) as stream:
            async for text in stream.text_stream:
                if isinstance(text, str) and text:
                    yield WebSearchAnswerDelta(text=text)
            final_message = await _maybe_await(stream.get_final_message())
        gateway_execution.record_success(
            usage=_usage_dict(getattr(final_message, "usage", None)),
            metadata={
                "model": str(getattr(final_message, "model", "") or ""),
                "workload_id": prepared_execution.workload_id,
            },
        )
    except (asyncio.CancelledError, GeneratorExit):
        gateway_execution.record_cancelled()
        raise
    except WebSearchConfigurationError:
        raise
    except Exception as exc:  # noqa: BLE001 - provider SDK errors vary by version
        gateway_execution.record_error(exc)
        raise WebSearchGenerationError(str(exc)) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await _maybe_await(close())

    yield WebSearchAnswerComplete(
        response=_response_from_message(
            question=question,
            message=final_message,
            conversation_id=prepared_execution.conversation_id or conversation_id,
        )
    )


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


def _usage_dict(usage: Any) -> dict[str, int] | None:
    parsed = _parse_usage(usage)
    if parsed is None:
        return None
    result = {
        "input_tokens": parsed.input_tokens,
        "output_tokens": parsed.output_tokens,
        "web_search_requests": parsed.web_search_requests,
    }
    return {key: value for key, value in result.items() if isinstance(value, int)} or None


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


def _anthropic_client_for_route(
    route: ResolvedLlmWorkloadRoute,
    *,
    settings: Settings,
) -> Any:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise WebSearchConfigurationError("anthropic package is required for web search.") from exc
    api_key = route.api_key.get_secret_value() if route.api_key is not None else ""
    if not api_key:
        raise WebSearchConfigurationError("Anthropic API key is not configured.")
    return AsyncAnthropic(
        api_key=api_key,
        base_url=route.endpoint_url.rstrip("/"),
        timeout=settings.llm_external_long_generation_timeout_seconds,
    )


def _anthropic_web_search_request(
    *,
    question: str,
    max_uses: int,
    profile_id: str,
    model: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "system": _system_prompt_for_profile(profile_id),
        "messages": [{"role": "user", "content": question}],
        "tools": [
            {
                "type": WEB_SEARCH_TOOL_TYPE,
                "name": "web_search",
                "max_uses": max_uses,
            }
        ],
    }


def _system_prompt_for_profile(profile_id: str) -> str:
    return SYSTEM_PROMPTS_BY_PROFILE.get(profile_id, SYSTEM_PROMPT)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _response_from_message(
    *,
    question: str,
    message: Any,
    conversation_id: str | None = None,
) -> WebSearchAnswerResponse:
    answer_parts: list[str] = []
    citations: list[WebSearchCitation] = []
    citation_index: dict[tuple[str, str, str | None], int] = {}

    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if not isinstance(text, str) or not text:
            continue
        block_citation_numbers: list[int] = []
        for citation in getattr(block, "citations", None) or []:
            parsed = _parse_citation(citation)
            if parsed is None:
                continue
            key = (parsed.url, parsed.title, parsed.cited_text)
            number = citation_index.get(key)
            if number is None:
                citations.append(parsed)
                number = len(citations)
                citation_index[key] = number
            if number not in block_citation_numbers:
                block_citation_numbers.append(number)
        if block_citation_numbers:
            markers = "".join(f"[{number}]" for number in block_citation_numbers)
            answer_parts.append(f"{text}{markers}")
        else:
            answer_parts.append(text)

    answer = "".join(answer_parts).strip()
    return WebSearchAnswerResponse(
        query=question,
        answer=answer,
        citations=citations,
        model=str(getattr(message, "model", "") or ""),
        usage=_parse_usage(getattr(message, "usage", None)),
        conversation_id=conversation_id,
    )


def _parse_citation(citation: Any) -> WebSearchCitation | None:
    url = getattr(citation, "url", None)
    title = getattr(citation, "title", None)
    if not isinstance(url, str) or not url:
        return None
    if not isinstance(title, str) or not title:
        title = url
    cited_text = getattr(citation, "cited_text", None)
    return WebSearchCitation(
        url=url,
        title=title,
        cited_text=cited_text if isinstance(cited_text, str) and cited_text else None,
    )


def _parse_usage(usage: Any) -> WebSearchUsage | None:
    if usage is None:
        return None
    server_tool_use = getattr(usage, "server_tool_use", None)
    web_search_requests = getattr(server_tool_use, "web_search_requests", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if not any(
        isinstance(value, int) for value in (input_tokens, output_tokens, web_search_requests)
    ):
        return None
    return WebSearchUsage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        web_search_requests=web_search_requests if isinstance(web_search_requests, int) else None,
    )
