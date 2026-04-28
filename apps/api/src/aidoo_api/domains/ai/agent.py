from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from aidoo_api.core.llm import (
    LlmTaskContext,
    PolicyDecision,
    ResolvedLlmExecution,
    complete_chat_stream,
    get_pool_config,
)
from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.ai.events import EnvelopeEncoder, make_envelope
from aidoo_api.domains.ai.runtime.contracts import RuntimeProfile
from aidoo_api.domains.ai.tool_runtime import execute_tool_call, iter_tool_call_events
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.conversations.models import Conversation


AGENT_SYSTEM_PROMPT = (
    "너는 두원공조 사내 업무를 돕는 한국어 AI 비서다. "
    "워크스페이스 사실은 추정하지 말고 가능하면 도구를 우선 사용한다. "
    "도구 결과가 있으면 그 범위 안에서만 답하고, 부족하면 부족하다고 말한다. "
    "도구 오류가 나면 조용히 무시하지 말고 필요한 경우 다시 시도하거나 한계를 설명한다.\n\n"
    "긴 산출물은 chat 말풍선에 쏟지 말고 오른쪽 사이드 패널(artifact) 에 렌더한다. "
    "chat 에는 한두 문장 요약만 남기고 실제 내용은 artifact 안에 넣는다. "
    "산출물 성격에 따라 artifact type 을 골라 감싼다:\n\n"
    '(1) 문서형 산출물 (기안서 / 이메일 / 보고서 / 번역 / 회의록 / 표 양식 등) — type="document"\n'
    "    본문은 순수 markdown 으로 쓴다. 바깥에 ``` 를 추가하지 말 것.\n"
    '    <artifact type="document" title="주간 보고서">\n'
    "    # 주간 보고서\n"
    "    | 항목 | 내용 |\n"
    "    | --- | --- |\n"
    "    ...\n"
    "    </artifact>\n\n"
    '(2) 브라우저에서 실행되는 완전한 HTML 페이지 (랜딩 / 슈팅 게임 / 대시보드 시연 등) — type="html"\n'
    "    본문은 <!doctype html> 로 시작하는 완성된 HTML 문서 한 개. 사용자는 Preview 탭에서 실제 동작을 본다.\n"
    '    <artifact type="html" title="간단한 슈팅 게임">\n'
    "    <!doctype html>\n"
    '    <html lang="ko"><head>...</head><body>...</body></html>\n'
    "    </artifact>\n\n"
    '(3) 참고용 프로그램 코드 (전체 스크립트 / 30줄 이상의 JS·Python·SQL·Bash, 또는 HTML 템플릿 스니펫) — type="code"\n'
    "    language 속성에 언어를 쓰고, 본문은 코드 자체만 넣는다. 바깥에 ``` 를 쓰지 말 것.\n"
    '    <artifact type="code" language="python" title="FastAPI 라우트 예제">\n'
    "    from fastapi import APIRouter\n"
    "    ...\n"
    "    </artifact>\n\n"
    '(4) SVG 그래픽 (로고 / 아이콘 / 다이어그램) — type="svg"\n'
    "    본문은 <svg> 요소 자체. 외부 리소스(이미지 URL, script) 는 넣지 않는다.\n"
    '    <artifact type="svg" title="회사 로고">\n'
    '    <svg viewBox="0 0 100 100">...</svg>\n'
    "    </artifact>\n\n"
    'HTML 을 \'돌려서 보여주는\' 목적이면 type="html", 소스만 설명/공유하려면 type="code" language="html" 을 쓴다.\n'
    "짧은 한두 문단 답변이나 10줄 미만 스니펫은 artifact 없이 chat 에 쓴다. "
    "문서 본문 안에 짧은 코드 예시가 필요하면 document artifact 안에서 markdown fenced code block 으로 인라인 배치한다."
)


@dataclass
class _PendingToolCall:
    call_id: str
    name: str
    arguments_buffer: str = ""


@dataclass
class _LoopState:
    total_tool_calls: int = 0
    consecutive_tool_errors: int = 0
    last_tool_signature: str | None = None
    aggregated_usage: dict[str, int] | None = None


async def run_agent_turn_stream(
    *,
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    messages: list[dict[str, Any]],
    temperature: float | None,
    stream_reasoning: bool,
    encoder: EnvelopeEncoder,
    max_turns: int,
    max_tool_calls: int,
    max_consecutive_tool_errors: int,
    agent_run_id: str,
    tool_specs: list[dict[str, Any]],
    bound_conversation: Conversation | None,
    scope_system_prompt: str | None = None,
    allowed_app_ids: list[str] | None = None,
    runtime_profile: RuntimeProfile = "interactive_read",
    runtime_routing_reason_codes: tuple[str, ...] = (),
    runtime_graph_gate: str = "disabled",
    runtime_graph_fallback_reason: str | None = None,
    runtime_graph_used: bool = False,
    parallel_tool_calls: bool | None = None,
) -> AsyncIterator[Any]:
    conversation = _prepend_agent_system_message(
        messages,
        scope_system_prompt=scope_system_prompt,
    )
    model_meta = _build_snapshot_model_meta(
        execution,
        temperature=temperature,
        stream_reasoning=stream_reasoning,
        parallel_tool_calls=parallel_tool_calls,
        tool_choice_state="auto",
        allowed_app_ids=allowed_app_ids,
        tool_specs=tool_specs,
        runtime_profile=runtime_profile,
        runtime_routing_reason_codes=runtime_routing_reason_codes,
        runtime_graph_gate=runtime_graph_gate,
        runtime_graph_fallback_reason=runtime_graph_fallback_reason,
        runtime_graph_used=runtime_graph_used,
    )
    async for event in _run_agent_loop_stream(
        context=context,
        execution=execution,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        conversation=conversation,
        temperature=temperature,
        stream_reasoning=stream_reasoning,
        encoder=encoder,
        max_turns=max_turns,
        max_tool_calls=max_tool_calls,
        max_consecutive_tool_errors=max_consecutive_tool_errors,
        agent_run_id=agent_run_id,
        tool_specs=tool_specs,
        bound_conversation=bound_conversation,
        parallel_tool_calls=parallel_tool_calls,
        tool_choice_state="auto",
        current_snapshot=None,
        replay_approval=None,
        model_meta=model_meta,
    ):
        yield event


async def resume_agent_run(
    *,
    context: LlmTaskContext,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: Conversation,
    approval_id: str,
    encoder: EnvelopeEncoder,
    max_turns: int,
    max_tool_calls: int,
    max_consecutive_tool_errors: int,
    tool_specs: list[dict[str, Any]],
) -> AsyncIterator[Any]:
    approval, snapshot = ai_approvals.get_resume_context(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation.id,
        approval_id=approval_id,
        for_update=True,
    )
    replay_config = ai_approvals.rehydrate_model_meta(snapshot)
    execution = _execution_from_snapshot(snapshot)
    # Resume replays the frozen snapshot verbatim. We intentionally do not
    # rebuild any scope-bound prompt here because canonical replay must match
    # the exact context the halted run saw when it requested approval.
    conversation_messages = _copy_messages(snapshot.messages_json or [])
    async for event in _run_agent_loop_stream(
        context=context,
        execution=execution,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        conversation=conversation_messages,
        temperature=replay_config.temperature,
        stream_reasoning=(
            replay_config.stream_reasoning
            if replay_config.stream_reasoning is not None
            else execution.resolved_reasoning_effort != "none"
        ),
        encoder=encoder,
        max_turns=max_turns,
        max_tool_calls=max_tool_calls,
        max_consecutive_tool_errors=max_consecutive_tool_errors,
        agent_run_id=snapshot.id,
        tool_specs=tool_specs,
        bound_conversation=conversation,
        parallel_tool_calls=replay_config.parallel_tool_calls,
        tool_choice_state=replay_config.tool_choice_state or "auto",
        current_snapshot=snapshot,
        replay_approval=approval,
        model_meta=replay_config.raw,
    ):
        yield event


async def _run_agent_loop_stream(
    *,
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: list[dict[str, Any]],
    temperature: float | None,
    stream_reasoning: bool,
    encoder: EnvelopeEncoder,
    max_turns: int,
    max_tool_calls: int,
    max_consecutive_tool_errors: int,
    agent_run_id: str,
    tool_specs: list[dict[str, Any]],
    bound_conversation: Conversation | None,
    parallel_tool_calls: bool | None,
    tool_choice_state: str | dict[str, Any] | None,
    current_snapshot: ai_approvals.AgentRunSnapshot | None,
    replay_approval: ai_approvals.AiToolApproval | None,
    model_meta: dict[str, Any],
) -> AsyncIterator[Any]:
    state = _LoopState()
    replay_tool_executed = False
    try:
        if replay_approval is not None:
            ai_approvals.mark_snapshot_resumed(db, current_snapshot)
            db.commit()
            yield make_envelope(
                "approval_resolved",
                encoder.next_seq(),
                {
                    "approval_id": replay_approval.id,
                    "call_id": replay_approval.tool_call_id,
                    "decision": replay_approval.status,
                    "reason": replay_approval.reject_reason,
                },
            )
            replay_execution = execute_tool_call(
                db,
                workspace=workspace,
                principal=principal,
                user=user,
                tool_name=replay_approval.tool_name,
                arguments=_parse_json_arguments(replay_approval.arguments_json),
                source="api.resume",
                call_id=replay_approval.tool_call_id,
                agent_run_id=agent_run_id,
                conversation_id=bound_conversation.id if bound_conversation is not None else None,
                approved_call_id=replay_approval.id,
            )
            replay_tool_executed = True
            for event in iter_tool_call_events(
                encoder=encoder,
                execution=replay_execution,
                include_call_frames=False,
            ):
                yield event
            _append_tool_exchange(
                conversation,
                call_id=replay_approval.tool_call_id,
                tool_name=replay_approval.tool_name,
                arguments_json=replay_approval.arguments_json,
                tool_content=replay_execution.llm_result_content,
            )
            if replay_execution.status == "error":
                state.consecutive_tool_errors = 1
                if state.consecutive_tool_errors >= max_consecutive_tool_errors:
                    _complete_snapshot_if_needed(db, current_snapshot)
                    yield make_envelope(
                        "error",
                        encoder.next_seq(),
                        {
                            "code": "agent_loop_tool_error_budget",
                            "message": "도구 호출 오류가 연속으로 발생해 처리를 중단했습니다.",
                            "retryable": False,
                        },
                    )
                    yield make_envelope(
                        "done",
                        encoder.next_seq(),
                        {
                            "finish_reason": "error",
                            "audit_id": None,
                            "meta": _build_done_meta(execution, model_meta=model_meta),
                        },
                    )
                    return

        for _turn_index in range(max_turns):
            pending_calls: dict[str, _PendingToolCall] = {}
            pending_order: list[str] = []
            turn_finish_reason = "stop"

            async for chunk, _decision, _config in complete_chat_stream(
                context,
                db,
                messages=conversation,
                temperature=temperature,
                stream_reasoning=stream_reasoning,
                tools=tool_specs,
                tool_choice=tool_choice_state,
                parallel_tool_calls=parallel_tool_calls,
                resolved_execution=execution,
                agent_run_id=agent_run_id,
                conversation_id=bound_conversation.id if bound_conversation is not None else None,
            ):
                if chunk.kind == "content" and chunk.text:
                    yield make_envelope(
                        "content_delta",
                        encoder.next_seq(),
                        {"text": chunk.text},
                    )
                    continue
                if chunk.kind == "reasoning" and chunk.text and stream_reasoning:
                    yield make_envelope(
                        "reasoning_delta",
                        encoder.next_seq(),
                        {"text": chunk.text},
                    )
                    continue
                if chunk.kind == "usage" and chunk.usage:
                    state.aggregated_usage = _merge_usage(state.aggregated_usage, chunk.usage)
                    continue
                if chunk.kind == "tool_call_start":
                    call_id = chunk.tool_call_id or f"tool_call_{len(pending_order)}"
                    name = chunk.tool_name or "unknown.tool"
                    pending_calls[call_id] = _PendingToolCall(call_id=call_id, name=name)
                    pending_order.append(call_id)
                    yield make_envelope(
                        "tool_call_started",
                        encoder.next_seq(),
                        {
                            "call_id": call_id,
                            "name": name,
                        },
                    )
                    continue
                if chunk.kind == "tool_call_args" and chunk.tool_call_id and chunk.args_delta:
                    pending = pending_calls.get(chunk.tool_call_id)
                    if pending is None:
                        pending = _PendingToolCall(
                            call_id=chunk.tool_call_id,
                            name=chunk.tool_name or "unknown.tool",
                        )
                        pending_calls[pending.call_id] = pending
                        pending_order.append(pending.call_id)
                        yield make_envelope(
                            "tool_call_started",
                            encoder.next_seq(),
                            {
                                "call_id": pending.call_id,
                                "name": pending.name,
                            },
                        )
                    pending.arguments_buffer += chunk.args_delta
                    yield make_envelope(
                        "tool_call_args_delta",
                        encoder.next_seq(),
                        {
                            "call_id": pending.call_id,
                            "delta": chunk.args_delta,
                        },
                    )
                    continue
                if chunk.kind == "done":
                    turn_finish_reason = chunk.finish_reason or "stop"
                    continue

            if turn_finish_reason != "tool_calls":
                _complete_snapshot_if_needed(db, current_snapshot)
                if state.aggregated_usage:
                    yield make_envelope(
                        "usage",
                        encoder.next_seq(),
                        state.aggregated_usage,
                    )
                yield make_envelope(
                    "done",
                    encoder.next_seq(),
                    {
                        "finish_reason": turn_finish_reason,
                        "audit_id": None,
                        "meta": _build_done_meta(execution, model_meta=model_meta),
                    },
                )
                return

            if not pending_order:
                _complete_snapshot_if_needed(db, current_snapshot)
                yield make_envelope(
                    "error",
                    encoder.next_seq(),
                    {
                        "code": "agent_loop_missing_tool_calls",
                        "message": "모델이 tool_calls 종료를 보냈지만 호출 정보가 비어 있습니다.",
                        "retryable": False,
                    },
                )
                yield make_envelope(
                    "done",
                    encoder.next_seq(),
                    {
                        "finish_reason": "error",
                        "audit_id": None,
                        "meta": _build_done_meta(execution, model_meta=model_meta),
                    },
                )
                return

            for call_id in pending_order:
                pending = pending_calls[call_id]
                state.total_tool_calls += 1
                if state.total_tool_calls > max_tool_calls:
                    _complete_snapshot_if_needed(db, current_snapshot)
                    yield make_envelope(
                        "error",
                        encoder.next_seq(),
                        {
                            "code": "agent_loop_tool_budget",
                            "message": "허용된 도구 호출 횟수를 초과했습니다.",
                            "retryable": False,
                        },
                    )
                    yield make_envelope(
                        "done",
                        encoder.next_seq(),
                        {
                            "finish_reason": "error",
                            "audit_id": None,
                            "meta": _build_done_meta(execution, model_meta=model_meta),
                        },
                    )
                    return

                parsed_arguments = _parse_tool_arguments(pending)
                signature = _tool_signature(pending.name, parsed_arguments)
                if state.last_tool_signature == signature:
                    _complete_snapshot_if_needed(db, current_snapshot)
                    yield make_envelope(
                        "error",
                        encoder.next_seq(),
                        {
                            "code": "agent_loop_duplicate_tool_call",
                            "message": f"중복 도구 호출이 감지되었습니다: {pending.name}",
                            "retryable": False,
                        },
                    )
                    yield make_envelope(
                        "done",
                        encoder.next_seq(),
                        {
                            "finish_reason": "error",
                            "audit_id": None,
                            "meta": _build_done_meta(execution, model_meta=model_meta),
                        },
                    )
                    return
                state.last_tool_signature = signature

                tool_execution = execute_tool_call(
                    db,
                    workspace=workspace,
                    principal=principal,
                    user=user,
                    tool_name=pending.name,
                    arguments=parsed_arguments,
                    source="api.resume" if current_snapshot is not None else "api.stream",
                    call_id=pending.call_id,
                    agent_run_id=agent_run_id,
                    conversation_id=bound_conversation.id
                    if bound_conversation is not None
                    else None,
                )

                if tool_execution.status == "blocked":
                    if bound_conversation is None:
                        raise RuntimeError(
                            "Approval-gated agent runs require a persisted conversation."
                        )
                    next_agent_run_id = agent_run_id if current_snapshot is None else new_id()
                    if current_snapshot is not None:
                        ai_approvals.mark_snapshot_completed(db, current_snapshot)
                    snapshot = ai_approvals.persist_snapshot_on_halt(
                        db,
                        workspace=workspace,
                        conversation=bound_conversation,
                        requested_by_user=user,
                        messages_json=_copy_messages(conversation),
                        blocked_call_id=pending.call_id,
                        model_meta=dict(model_meta),
                        snapshot_id=next_agent_run_id,
                    )
                    approval = ai_approvals.create_pending_approval(
                        db,
                        workspace=workspace,
                        conversation=bound_conversation,
                        requested_by_user=user,
                        agent_run_id=snapshot.id,
                        tool_call_id=pending.call_id,
                        tool_name=pending.name,
                        arguments_json=tool_execution.arguments_json,
                        resource_preview=tool_execution.resource_preview,
                    )
                    db.commit()
                    if state.aggregated_usage:
                        yield make_envelope(
                            "usage",
                            encoder.next_seq(),
                            state.aggregated_usage,
                        )
                    yield make_envelope(
                        "approval_required",
                        encoder.next_seq(),
                        {
                            "approval_id": approval.id,
                            "call_id": pending.call_id,
                            "tool": pending.name,
                            "resource_preview": approval.resource_preview,
                            "expires_at_ms": int(approval.expires_at.timestamp() * 1000),
                        },
                    )
                    yield make_envelope(
                        "done",
                        encoder.next_seq(),
                        {
                            "finish_reason": "awaiting_approval",
                            "audit_id": None,
                            "meta": _build_done_meta(
                                execution,
                                model_meta=model_meta,
                                pending_approval_id=approval.id,
                                pending_call_id=pending.call_id,
                                agent_run_id=snapshot.id,
                            ),
                        },
                    )
                    return

                for event in iter_tool_call_events(
                    encoder=encoder,
                    execution=tool_execution,
                    include_call_frames=False,
                ):
                    yield event
                _append_tool_exchange(
                    conversation,
                    call_id=pending.call_id,
                    tool_name=pending.name,
                    arguments_json=pending.arguments_buffer,
                    tool_content=tool_execution.llm_result_content,
                )

                if tool_execution.status == "error":
                    state.consecutive_tool_errors += 1
                    if state.consecutive_tool_errors >= max_consecutive_tool_errors:
                        _complete_snapshot_if_needed(db, current_snapshot)
                        yield make_envelope(
                            "error",
                            encoder.next_seq(),
                            {
                                "code": "agent_loop_tool_error_budget",
                                "message": "도구 호출 오류가 연속으로 발생해 처리를 중단했습니다.",
                                "retryable": False,
                            },
                        )
                        yield make_envelope(
                            "done",
                            encoder.next_seq(),
                            {
                                "finish_reason": "error",
                                "audit_id": None,
                                "meta": _build_done_meta(execution, model_meta=model_meta),
                            },
                        )
                        return
                else:
                    state.consecutive_tool_errors = 0

        _complete_snapshot_if_needed(db, current_snapshot)
        yield make_envelope(
            "error",
            encoder.next_seq(),
            {
                "code": "agent_loop_turn_cap",
                "message": "허용된 agent loop 턴 수를 초과했습니다.",
                "retryable": False,
            },
        )
        yield make_envelope(
            "done",
            encoder.next_seq(),
            {
                "finish_reason": "error",
                "audit_id": None,
                "meta": _build_done_meta(execution, model_meta=model_meta),
            },
        )
    except (asyncio.CancelledError, GeneratorExit):
        if (
            replay_approval is not None
            and current_snapshot is not None
            and current_snapshot.status == "resumed"
        ):
            # Only rewind to awaiting_approval when the cancel hit BEFORE the
            # approved tool actually ran. If the tool already executed, any
            # DB side effects are committed on the outer router boundary, so
            # a rewind would let a second resume re-execute the same write.
            if not replay_tool_executed and replay_approval.status in {"approved", "rejected"}:
                ai_approvals.rewind_snapshot_to_awaiting_approval(db, current_snapshot)
            else:
                ai_approvals.mark_snapshot_completed(db, current_snapshot)
            db.commit()
        raise
    except Exception:
        _complete_snapshot_if_needed(db, current_snapshot)
        raise


def _prepend_agent_system_message(
    messages: list[dict[str, Any]],
    *,
    scope_system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    system_prompt = AGENT_SYSTEM_PROMPT
    if scope_system_prompt:
        system_prompt = f"{system_prompt}\n\n{scope_system_prompt}"
    return [
        {"role": "system", "content": system_prompt},
        *[dict(message) for message in messages],
    ]


def _assistant_tool_call_message(
    *,
    call_id: str,
    tool_name: str,
    arguments_json: str,
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arguments_json,
                },
            }
        ],
    }


def _tool_result_message(*, call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": content,
    }


def _append_tool_exchange(
    conversation: list[dict[str, Any]],
    *,
    call_id: str,
    tool_name: str,
    arguments_json: str,
    tool_content: str,
) -> None:
    conversation.append(
        _assistant_tool_call_message(
            call_id=call_id,
            tool_name=tool_name,
            arguments_json=arguments_json,
        )
    )
    conversation.append(
        _tool_result_message(
            call_id=call_id,
            content=tool_content,
        )
    )


def _parse_tool_arguments(pending: _PendingToolCall) -> dict[str, Any]:
    if not pending.arguments_buffer.strip():
        return {}
    try:
        parsed = json.loads(pending.arguments_buffer)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    digest = hashlib.sha1(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"{tool_name}:{digest}"


def _merge_usage(
    aggregated: dict[str, int] | None,
    incoming: dict[str, int],
) -> dict[str, int]:
    if aggregated is None:
        return dict(incoming)
    merged = dict(aggregated)
    for field_name, value in incoming.items():
        if isinstance(value, int):
            merged[field_name] = merged.get(field_name, 0) + value
    return merged


def _build_done_meta(
    execution: ResolvedLlmExecution,
    *,
    model_meta: dict[str, Any] | None = None,
    pending_approval_id: str | None = None,
    pending_call_id: str | None = None,
    agent_run_id: str | None = None,
) -> dict[str, Any]:
    meta = {
        "policy": execution.decision.policy,
        "chosen_pool": execution.decision.chosen_pool,
        "decision_reason": execution.decision.reason,
        "forced_local": execution.decision.forced_local,
        "pii_hits": list(execution.decision.pii_hits),
        "model": execution.chosen_model,
        "chosen_model": execution.chosen_model,
        "canonical_model": execution.config.canonical_model,
        "provider": execution.config.provider,
        "pending_approval_id": pending_approval_id,
        "pending_call_id": pending_call_id,
        "agent_run_id": agent_run_id,
    }
    if model_meta is not None:
        meta.update(_runtime_done_meta(model_meta))
    return meta


def _runtime_done_meta(model_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_profile": model_meta.get("runtime_profile"),
        "runtime_routing_reason_codes": list(model_meta.get("runtime_routing_reason_codes") or []),
        "graph_gate": model_meta.get("graph_gate"),
        "graph_fallback_reason": model_meta.get("graph_fallback_reason"),
        "graph_used": bool(model_meta.get("graph_used")),
    }


def _build_snapshot_model_meta(
    execution: ResolvedLlmExecution,
    *,
    temperature: float | None,
    stream_reasoning: bool,
    parallel_tool_calls: bool | None,
    tool_choice_state: str | dict[str, Any] | None,
    allowed_app_ids: list[str] | None,
    tool_specs: list[dict[str, Any]],
    runtime_profile: RuntimeProfile,
    runtime_routing_reason_codes: tuple[str, ...],
    runtime_graph_gate: str,
    runtime_graph_fallback_reason: str | None,
    runtime_graph_used: bool,
) -> dict[str, Any]:
    return {
        "model": execution.chosen_model,
        "chosen_model": execution.chosen_model,
        "canonical_model": execution.config.canonical_model,
        "provider": execution.config.provider,
        "policy": execution.decision.policy,
        "chosen_pool": execution.decision.chosen_pool,
        "decision_reason": execution.decision.reason,
        "forced_local": execution.decision.forced_local,
        "pii_hits": list(execution.decision.pii_hits),
        "stream_reasoning": stream_reasoning,
        "parallel_tool_calls": parallel_tool_calls,
        "tool_choice_state": tool_choice_state,
        "temperature": temperature,
        "max_output_tokens": execution.resolved_max_tokens,
        "reasoning_effort": execution.resolved_reasoning_effort,
        "runtime_profile": runtime_profile,
        "runtime_routing_reason_codes": list(runtime_routing_reason_codes),
        "graph_gate": runtime_graph_gate,
        "graph_fallback_reason": runtime_graph_fallback_reason,
        "graph_used": runtime_graph_used,
        "scope": _build_snapshot_scope_meta(
            allowed_app_ids=allowed_app_ids,
            tool_specs=tool_specs,
        ),
    }


def _build_snapshot_scope_meta(
    *,
    allowed_app_ids: list[str] | None,
    tool_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "allowed_app_ids": list(allowed_app_ids) if allowed_app_ids is not None else None,
        "resolved_agent_ids": ["single_loop"],
        "resolved_tool_names": _tool_names_from_specs(tool_specs),
    }


def _tool_names_from_specs(tool_specs: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for spec in tool_specs:
        function_spec = spec.get("function")
        if not isinstance(function_spec, dict):
            continue
        name = function_spec.get("name")
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names


def _execution_from_snapshot(
    snapshot: ai_approvals.AgentRunSnapshot,
) -> ResolvedLlmExecution:
    replay = ai_approvals.rehydrate_model_meta(snapshot)
    chosen_pool = replay.chosen_pool if replay.chosen_pool in {"local", "external"} else "local"
    config = get_pool_config(chosen_pool)
    policy = (
        replay.policy
        if replay.policy in {"local_only", "external"}
        else ("external" if chosen_pool == "external" else "local_only")
    )
    decision = PolicyDecision(
        policy=policy,
        chosen_pool=chosen_pool,
        pii_hits=list(replay.raw.get("pii_hits") or []),
        forced_local=bool(replay.raw.get("forced_local")),
        reason=str(replay.raw.get("decision_reason") or "resume_snapshot"),
    )
    return ResolvedLlmExecution(
        pool=chosen_pool,
        decision=decision,
        config=config,
        chosen_model=replay.model or config.default_model,
        resolved_max_tokens=replay.max_output_tokens or 4096,
        resolved_reasoning_effort=str(replay.raw.get("reasoning_effort") or "none"),
    )


def _complete_snapshot_if_needed(
    db: Session,
    snapshot: ai_approvals.AgentRunSnapshot | None,
) -> None:
    if snapshot is None:
        return
    if snapshot.status != "resumed":
        return
    ai_approvals.mark_snapshot_completed(db, snapshot)
    db.commit()


def _copy_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [deepcopy(message) for message in messages]
