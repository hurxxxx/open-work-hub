"""LLM pool routing + policy + health.

Public surface:

- ``LlmTaskContext`` — identity of an LLM request (source / actor_user_id /
  workspace_id / task_kind). Mandatory input to ``choose_pool`` and
  ``complete_chat``.
- ``PolicyDecision`` — output of ``choose_pool``; records the policy mode, the
  chosen pool, any PII hits, whether local was forced, and a short reason.
- ``get_pool_client(pool)`` / ``get_async_pool_client(pool)`` /
  ``get_pool_config(pool)`` — pool-scoped OpenAI clients + config.
- ``check_pool_health(pool)`` / ``check_all_pools_health()`` — pool-independent
  health. **No cross-pool fallback** in any public function.
- ``complete_chat(context, db, ...)`` / ``complete_chat_stream(...)`` — the two
  call paths for chat completions (sync + SSE streaming). Handle policy, PII,
  pool selection, timeout, and forward to the OpenAI-compatible client.
  Callers MUST supply a ``LlmTaskContext``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Literal, Mapping

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
    OpenAIError,
)
from sqlalchemy.orm import Session

from aidoo_api.core.pii import scan_pii
from aidoo_api.core.settings import Settings, get_settings
from aidoo_api.domains.ai.registry import RegisteredLlmTask, get_ai_capability_registry
from aidoo_api.domains.ai.policy_service import LlmPolicyMode, resolve_policy


logger = logging.getLogger(__name__)


LlmPoolName = Literal["local", "external"]
LlmPoolHint = Literal["local"]
LlmHealthStatus = Literal[
    "ready", "unavailable", "model_missing", "not_configured", "disabled"
]

LOCAL_DEFAULT_MAX_TOKENS = 30_000
EXTERNAL_DEFAULT_MAX_TOKENS = 262_144
LOCAL_TASK_MAX_TOKENS: Mapping[str, int] = {
    # Interactive turns should fail fast when the model loops instead of
    # consuming a long-form generation budget.
    "chatbot": 4_096,
    "rag_grounded_answer": 6_144,
    "meeting_insight_actions": 4_096,
    "meeting_insight_decisions": 4_096,
    "meeting_insight_followup": 4_096,
    # Summaries and batch outputs are expected to be longer.
    "meeting_summary": 12_000,
    "batch_generation": LOCAL_DEFAULT_MAX_TOKENS,
}
EXTERNAL_TASK_MAX_TOKENS: Mapping[str, int] = {
    "chatbot": 8_192,
    "rag_grounded_answer": 12_288,
    "meeting_insight_actions": 6_144,
    "meeting_insight_decisions": 6_144,
    "meeting_insight_followup": 6_144,
    "meeting_summary": 24_000,
    "batch_generation": EXTERNAL_DEFAULT_MAX_TOKENS,
}
LOCAL_DEFAULT_REASONING_EFFORT = "none"
EXTERNAL_DEFAULT_REASONING_EFFORT = "medium"


SupportedLlmTask = RegisteredLlmTask


def get_supported_llm_tasks() -> tuple[SupportedLlmTask, ...]:
    registry = get_ai_capability_registry()
    return tuple(
        sorted(
            registry.llm_tasks.values(),
            key=lambda item: item.task_kind,
        )
    )


def get_llm_policy_seed_data() -> tuple[tuple[str, LlmPolicyMode, str], ...]:
    return tuple(
        (task.task_kind, task.default_policy, task.description)
        for task in get_supported_llm_tasks()
    )


# ---------------------------------------------------------------------------
# Config + identity types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmPoolConfig:
    pool: LlmPoolName
    provider: str
    base_url: str
    api_key: str
    default_model: str
    canonical_model: str
    long_generation_timeout_seconds: float
    enabled: bool = True
    default_headers: Mapping[str, str] | None = None

    @property
    def configured(self) -> bool:
        return (
            self.enabled
            and bool(self.base_url.strip())
            and bool(self.api_key.strip())
            and bool(self.default_model.strip())
        )


@dataclass(frozen=True)
class LlmTaskContext:
    source: str
    workspace_id: str
    task_kind: str
    actor_user_id: str | None = None
    principal_kind: Literal["user", "service_account", "system"] = "user"
    principal_id: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    policy: LlmPolicyMode
    chosen_pool: LlmPoolName
    pii_hits: list[str] = field(default_factory=list)
    forced_local: bool = False
    reason: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "chosen_pool": self.chosen_pool,
            "pii_hits": list(self.pii_hits),
            "forced_local": self.forced_local,
            "decision_reason": self.reason,
        }


@dataclass(frozen=True)
class ResolvedLlmExecution:
    pool: LlmPoolName
    decision: PolicyDecision
    config: LlmPoolConfig
    chosen_model: str
    resolved_max_tokens: int
    resolved_reasoning_effort: str


@dataclass(frozen=True)
class LlmPoolHealth:
    pool: LlmPoolName
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: LlmHealthStatus
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ready": self.ready}


@dataclass(frozen=True)
class LlmDualHealth:
    local: LlmPoolHealth
    external: LlmPoolHealth | None

    @property
    def ready(self) -> bool:
        """Overall readiness = local is ready OR external is ready.

        This is a signal for operations dashboards only. It is NOT used to
        decide a route at request time — see ``choose_pool``.
        """
        return self.local.ready or bool(self.external and self.external.ready)

    def public_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "local": self.local.public_dict(),
            "external": self.external.public_dict() if self.external else None,
        }


@dataclass(frozen=True)
class LlmTaskReadiness:
    task_kind: str
    description: str
    policy: LlmPolicyMode
    chosen_pool: LlmPoolName | None
    ready: bool
    detail: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LlmEffectiveReadiness:
    tasks: tuple[LlmTaskReadiness, ...]

    @property
    def ready(self) -> bool:
        return all(task.ready for task in self.tasks)

    def public_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "tasks": [task.public_dict() for task in self.tasks],
        }


# ---------------------------------------------------------------------------
# Pool config + client
# ---------------------------------------------------------------------------


def get_pool_config(
    pool: LlmPoolName, settings: Settings | None = None
) -> LlmPoolConfig:
    settings = settings or get_settings()
    if pool == "local":
        return LlmPoolConfig(
            pool="local",
            provider=settings.llm_local_provider,
            base_url=settings.llm_local_base_url,
            api_key=settings.llm_local_api_key,
            default_model=settings.llm_local_default_model,
            canonical_model=settings.llm_local_canonical_model,
            long_generation_timeout_seconds=(
                settings.llm_local_long_generation_timeout_seconds
            ),
            enabled=True,  # the local pool is always a possibility
        )

    headers: dict[str, str] = {}
    if settings.llm_external_http_referer.strip():
        headers["HTTP-Referer"] = settings.llm_external_http_referer.strip()
    if settings.llm_external_title.strip():
        headers["X-OpenRouter-Title"] = settings.llm_external_title.strip()

    return LlmPoolConfig(
        pool="external",
        provider=settings.llm_external_provider,
        base_url=settings.llm_external_base_url,
        api_key=settings.llm_external_api_key,
        default_model=settings.llm_external_default_model,
        canonical_model=settings.llm_external_canonical_model,
        long_generation_timeout_seconds=(
            settings.llm_external_long_generation_timeout_seconds
        ),
        enabled=settings.llm_external_enabled,
        default_headers=headers or None,
    )


@lru_cache(maxsize=2)
def get_pool_client(pool: LlmPoolName) -> OpenAI:
    config = get_pool_config(pool)
    settings = get_settings()
    return OpenAI(
        api_key=config.api_key or "placeholder",
        base_url=config.base_url,
        default_headers=dict(config.default_headers) if config.default_headers else None,
        max_retries=0,
        timeout=settings.llm_request_timeout_seconds,
    )


@lru_cache(maxsize=2)
def get_async_pool_client(pool: LlmPoolName) -> AsyncOpenAI:
    config = get_pool_config(pool)
    settings = get_settings()
    return AsyncOpenAI(
        api_key=config.api_key or "placeholder",
        base_url=config.base_url,
        default_headers=dict(config.default_headers) if config.default_headers else None,
        max_retries=0,
        timeout=settings.llm_request_timeout_seconds,
    )


def _clear_pool_client_cache() -> None:
    cache_clear = getattr(get_pool_client, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    async_cache_clear = getattr(get_async_pool_client, "cache_clear", None)
    if async_cache_clear is not None:
        async_cache_clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def check_pool_health(
    pool: LlmPoolName, settings: Settings | None = None
) -> LlmPoolHealth:
    settings = settings or get_settings()
    config = get_pool_config(pool, settings)

    if not config.enabled:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="disabled",
            detail=f"{config.pool} pool is disabled.",
        )

    if not config.configured:
        missing = [
            name
            for name, value in {
                "base_url": config.base_url,
                "api_key": config.api_key,
                "default_model": config.default_model,
            }.items()
            if not str(value).strip()
        ]
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="not_configured",
            detail=f"Missing LLM {config.pool} setting(s): {', '.join(missing)}",
        )

    try:
        models = get_pool_client(config.pool).models.list()
    except (APIConnectionError, APITimeoutError) as error:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=str(error),
        )
    except APIStatusError as error:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=f"{error.status_code}: {error.message}",
        )
    except OpenAIError as error:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="unavailable",
            detail=str(error),
        )

    model_ids = {model.id for model in models.data}
    if config.default_model not in model_ids:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="model_missing",
            detail=(
                f"Configured model was not found. Available models: "
                f"{', '.join(sorted(model_ids))}"
            ),
        )

    return LlmPoolHealth(
        pool=config.pool,
        provider=config.provider,
        base_url=config.base_url,
        model=config.default_model,
        canonical_model=config.canonical_model,
        status="ready",
    )


def check_all_pools_health(settings: Settings | None = None) -> LlmDualHealth:
    settings = settings or get_settings()
    local = check_pool_health("local", settings)
    external: LlmPoolHealth | None = (
        check_pool_health("external", settings)
        if settings.llm_external_enabled
        else None
    )
    return LlmDualHealth(local=local, external=external)


def check_effective_llm_readiness(
    db: Session, settings: Settings | None = None
) -> LlmEffectiveReadiness:
    settings = settings or get_settings()
    dual = check_all_pools_health(settings)
    tasks: list[LlmTaskReadiness] = []

    for task in get_supported_llm_tasks():
        try:
            policy = resolve_policy(task.task_kind, db)
        except Exception as error:
            tasks.append(
                LlmTaskReadiness(
                    task_kind=task.task_kind,
                    description=task.description,
                    policy=task.default_policy,
                    chosen_pool=None,
                    ready=False,
                    detail=f"policy_lookup_failed: {error}",
                )
            )
            continue

        chosen_pool: LlmPoolName = "external" if policy == "external" else "local"
        pool_health = dual.external if chosen_pool == "external" else dual.local
        if pool_health is None:
            tasks.append(
                LlmTaskReadiness(
                    task_kind=task.task_kind,
                    description=task.description,
                    policy=policy,
                    chosen_pool=chosen_pool,
                    ready=False,
                    detail="external pool is disabled",
                )
            )
            continue

        tasks.append(
            LlmTaskReadiness(
                task_kind=task.task_kind,
                description=task.description,
                policy=policy,
                chosen_pool=chosen_pool,
                ready=pool_health.ready,
                detail=None if pool_health.ready else pool_health.detail or pool_health.status,
            )
        )

    return LlmEffectiveReadiness(tasks=tuple(tasks))


# ---------------------------------------------------------------------------
# Pool selection + chat completion
# ---------------------------------------------------------------------------


def choose_pool(
    context: LlmTaskContext,
    text_inputs: Iterable[str],
    db: Session,
    *,
    pool_hint: LlmPoolHint | None = None,
) -> tuple[LlmPoolName, PolicyDecision]:
    """Determine which pool to use for ``context``.

    Rules:
      1. Lookup ``policy_mode`` for ``context.task_kind``. Missing row ⇒ `local_only`.
      2. If policy is ``external``, scan ``text_inputs`` for PII. A hit ⇒
         force ``local`` (``forced_local=True``) and record the hit labels.
      3. No cross-pool fallback is ever performed here.
    """
    policy = resolve_policy(context.task_kind, db)
    if pool_hint == "local":
        return "local", PolicyDecision(
            policy=policy,
            chosen_pool="local",
            forced_local=True,
            reason="local_hint",
        )

    if policy == "external":
        hits = scan_pii(text_inputs)
        if hits:
            decision = PolicyDecision(
                policy="external",
                chosen_pool="local",
                pii_hits=[hit.pattern for hit in hits],
                forced_local=True,
                reason="pii_detected",
            )
            return "local", decision
        return "external", PolicyDecision(
            policy="external",
            chosen_pool="external",
            reason="policy_external",
        )

    return "local", PolicyDecision(
        policy="local_only",
        chosen_pool="local",
        reason="policy_local_only",
    )


def resolve_chat_execution(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
    pool_hint: LlmPoolHint | None = None,
) -> ResolvedLlmExecution:
    text_inputs = _collect_text_inputs(messages)
    pool, decision = choose_pool(context, text_inputs, db, pool_hint=pool_hint)
    config = get_pool_config(pool)
    chosen_model = model or config.default_model
    resolved_max_tokens, resolved_reasoning_effort = _resolve_generation_defaults(
        pool,
        task_kind=context.task_kind,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    return ResolvedLlmExecution(
        pool=pool,
        decision=decision,
        config=config,
        chosen_model=chosen_model,
        resolved_max_tokens=resolved_max_tokens,
        resolved_reasoning_effort=resolved_reasoning_effort,
    )


def complete_chat(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    extra_body: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    model: str | None = None,
    audit_entity_id: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    resolved_execution: ResolvedLlmExecution | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> tuple[Any, PolicyDecision, LlmPoolConfig]:
    """Run a chat completion against the pool selected by policy + PII.

    The caller MUST supply an ``LlmTaskContext``. Every invocation — success,
    provider error, or configuration error — produces one ``llm_call`` audit
    log row. Raw prompt/content is never persisted; only identity + decision
    + token counters + error summary are recorded.

    Returns a 3-tuple of the raw completion response, the ``PolicyDecision``
    that was applied, and the ``LlmPoolConfig`` actually used. Pool failure
    surfaces as ``OpenAIError``; local pool failure does **not** transparently
    re-try on external.
    """
    # Local import keeps core/llm.py free of domain-layer dependencies in the
    # import graph (domains → core, not core → domains).
    from aidoo_api.domains.ai.audit import log_llm_call

    execution = resolved_execution or resolve_chat_execution(
        context,
        db,
        messages=messages,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        model=model,
        pool_hint=pool_hint,
    )
    config = execution.config
    decision = execution.decision

    if not config.configured:
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            workspace_id=context.workspace_id,
            task_kind=context.task_kind,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=0,
            max_tokens=execution.resolved_max_tokens,
            error=f"{execution.pool} pool is not configured",
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        raise OpenAIError(f"{execution.pool} pool is not configured")

    client = get_pool_client(execution.pool).with_options(
        timeout=timeout_seconds or config.long_generation_timeout_seconds
    )
    payload = _build_chat_payload(
        execution,
        messages=messages,
        temperature=temperature,
        extra_body=extra_body,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
    )

    started = time.monotonic()
    try:
        response = client.chat.completions.create(**payload)
    except Exception as error:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            workspace_id=context.workspace_id,
            task_kind=context.task_kind,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=elapsed_ms,
            max_tokens=execution.resolved_max_tokens,
            error=str(error),
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        raise
    elapsed_ms = int((time.monotonic() - started) * 1000)

    usage = _extract_usage(response)
    finish_reason = _first_choice_finish_reason(response)
    log_llm_call(
        source=context.source,
        actor_user_id=context.actor_user_id,
        principal_kind=context.principal_kind,
        principal_id=context.principal_id,
        workspace_id=context.workspace_id,
        task_kind=context.task_kind,
        policy=decision.policy,
        chosen_pool=decision.chosen_pool,
        decision_reason=decision.reason,
        forced_local=decision.forced_local,
        pii_hits=decision.pii_hits,
        model=getattr(response, "model", execution.chosen_model),
        status="ok",
        latency_ms=elapsed_ms,
        usage=usage,
        max_tokens=execution.resolved_max_tokens,
        finish_reason=finish_reason,
        entity_id=audit_entity_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    return response, decision, config


def _extract_usage(response: Any) -> dict[str, int] | None:
    """Normalise OpenAI-compatible usage payloads to the fixed audit shape.

    Missing fields are dropped rather than zero-filled so that the audit log
    does not confuse "unreported" with "zero".
    """
    usage_obj = getattr(response, "usage", None)
    if usage_obj is None:
        return None
    out: dict[str, int] = {}
    for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage_obj, field_name, None)
        if isinstance(value, int):
            out[field_name] = value
    return out or None


def _first_choice_finish_reason(response: Any) -> str | None:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    value = getattr(choices[0], "finish_reason", None)
    return value if isinstance(value, str) and value else None


def _collect_text_inputs(messages: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        out.append(text)
    return out


def _build_extra_body_for_pool(
    pool: LlmPoolName, reasoning_effort: str | None
) -> dict[str, Any]:
    if reasoning_effort is None:
        return {}
    if reasoning_effort == "none":
        return {"think": False} if pool == "local" else {}
    if pool == "external":
        return {"reasoning": {"effort": reasoning_effort}}
    return {"reasoning_effort": reasoning_effort}


def _resolve_generation_defaults(
    pool: LlmPoolName,
    *,
    task_kind: str,
    max_tokens: int | None,
    reasoning_effort: str | None,
) -> tuple[int, str]:
    if pool == "external":
        return (
            max_tokens or _default_max_tokens_for_task(pool, task_kind),
            reasoning_effort or EXTERNAL_DEFAULT_REASONING_EFFORT,
        )
    return (
        max_tokens or _default_max_tokens_for_task(pool, task_kind),
        reasoning_effort or LOCAL_DEFAULT_REASONING_EFFORT,
    )


def _default_max_tokens_for_task(pool: LlmPoolName, task_kind: str) -> int:
    if pool == "external":
        return EXTERNAL_TASK_MAX_TOKENS.get(task_kind, EXTERNAL_DEFAULT_MAX_TOKENS)
    return LOCAL_TASK_MAX_TOKENS.get(task_kind, LOCAL_DEFAULT_MAX_TOKENS)


def _merge_extra_body(
    base: Mapping[str, Any], extra: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if not base and not extra:
        return None
    merged = dict(base)
    if extra:
        merged.update(dict(extra))
    return merged


def _build_chat_payload(
    execution: ResolvedLlmExecution,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None,
    extra_body: Mapping[str, Any] | None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    stream_reasoning: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": execution.chosen_model,
        "messages": messages,
        "max_tokens": execution.resolved_max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    effective_reasoning_effort = (
        execution.resolved_reasoning_effort if stream_reasoning else "none"
    )
    merged_extra_body = _merge_extra_body(
        _build_extra_body_for_pool(
            execution.pool,
            effective_reasoning_effort,
        ),
        extra_body,
    )
    if merged_extra_body:
        payload["extra_body"] = merged_extra_body
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if parallel_tool_calls is not None:
        payload["parallel_tool_calls"] = parallel_tool_calls
    return payload


async def complete_chat_stream(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    extra_body: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    model: str | None = None,
    audit_entity_id: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    stream_reasoning: bool = True,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    resolved_execution: ResolvedLlmExecution | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
):
    """Streaming twin of :func:`complete_chat`.

    Yields ``(StreamChunk, PolicyDecision, LlmPoolConfig)`` tuples. The
    caller (route layer) converts each chunk into an agent-event envelope
    and uses ``decision``/``config`` to build the terminal ``done`` meta.

    Exactly one ``llm_call`` audit row is committed per stream:
      - ``status="ok"``        — finish_reason ∈ {stop, length}
      - ``status="error"``     — provider/adapter exception or bad finish
      - ``status="cancelled"`` — consumer closed the stream
        (``asyncio.CancelledError``)

    Raw prompt/content is never persisted — only usage/latency/status, mirror
    of :func:`complete_chat`.
    """
    import asyncio

    from aidoo_api.core.llm_adapters import get_stream_adapter
    from aidoo_api.domains.ai.audit import log_llm_call

    execution = resolved_execution or resolve_chat_execution(
        context,
        db,
        messages=messages,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        model=model,
        pool_hint=pool_hint,
    )
    config = execution.config
    decision = execution.decision

    if not config.configured:
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            workspace_id=context.workspace_id,
            task_kind=context.task_kind,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=0,
            max_tokens=execution.resolved_max_tokens,
            error=f"{execution.pool} pool is not configured",
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        raise OpenAIError(f"{execution.pool} pool is not configured")

    client = get_async_pool_client(execution.pool).with_options(
        timeout=timeout_seconds or config.long_generation_timeout_seconds
    )
    payload = _build_chat_payload(
        execution,
        messages=messages,
        temperature=temperature,
        extra_body=extra_body,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
        stream_reasoning=stream_reasoning,
    )

    adapter = get_stream_adapter(execution.pool)
    started = time.monotonic()
    status_final: str = "error"
    finish_reason_final: str | None = None
    error_message: str | None = None
    accumulated_usage: dict[str, int] | None = None
    try:
        async for chunk in adapter.open_stream(client, payload):
            if chunk.kind == "usage" and chunk.usage:
                accumulated_usage = chunk.usage
            if chunk.kind == "done":
                status_final = (
                    "ok"
                    if chunk.finish_reason in ("stop", "length", "tool_calls")
                    else "error"
                )
                finish_reason_final = chunk.finish_reason
            yield chunk, decision, config
    except (asyncio.CancelledError, GeneratorExit):
        status_final = "cancelled"
        raise
    except BaseException as error:  # noqa: BLE001 — we re-raise
        status_final = "error"
        error_message = str(error)
        raise
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            workspace_id=context.workspace_id,
            task_kind=context.task_kind,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status=status_final,
            latency_ms=elapsed_ms,
            usage=accumulated_usage,
            max_tokens=execution.resolved_max_tokens,
            finish_reason=finish_reason_final,
            error=error_message,
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
