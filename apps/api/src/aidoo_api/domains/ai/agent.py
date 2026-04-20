from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from aidoo_api.core.llm import LlmTaskContext, ResolvedLlmExecution, complete_chat_stream
from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.events import EnvelopeEncoder, make_envelope
from aidoo_api.domains.ai.tool_runtime import execute_tool_call, iter_tool_call_events
from aidoo_api.domains.auth.models import User, Workspace


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
) -> AsyncIterator[Any]:
    conversation = _prepend_agent_system_message(messages)
    total_tool_calls = 0
    consecutive_tool_errors = 0
    last_tool_signature: str | None = None
    aggregated_usage: dict[str, int] | None = None

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
            tool_choice="auto",
            resolved_execution=execution,
            agent_run_id=agent_run_id,
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
                aggregated_usage = _merge_usage(aggregated_usage, chunk.usage)
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
            if aggregated_usage:
                yield make_envelope(
                    "usage",
                    encoder.next_seq(),
                    aggregated_usage,
                )
            yield make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": turn_finish_reason,
                    "audit_id": None,
                    "meta": _build_done_meta(execution),
                },
            )
            return

        if not pending_order:
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
                    "meta": _build_done_meta(execution),
                },
            )
            return

        assistant_tool_calls: list[dict[str, Any]] = []
        tool_messages: list[dict[str, Any]] = []

        for call_id in pending_order:
            pending = pending_calls[call_id]
            total_tool_calls += 1
            if total_tool_calls > max_tool_calls:
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
                        "meta": _build_done_meta(execution),
                    },
                )
                return

            parsed_arguments = _parse_tool_arguments(pending)
            signature = _tool_signature(pending.name, parsed_arguments)
            if last_tool_signature == signature:
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
                        "meta": _build_done_meta(execution),
                    },
                )
                return
            last_tool_signature = signature

            tool_execution = execute_tool_call(
                db,
                workspace=workspace,
                principal=principal,
                user=user,
                tool_name=pending.name,
                arguments=parsed_arguments,
                source="api.stream",
                call_id=pending.call_id,
                agent_run_id=agent_run_id,
            )
            for event in iter_tool_call_events(
                encoder=encoder,
                execution=tool_execution,
                include_call_frames=False,
            ):
                yield event

            assistant_tool_calls.append(
                {
                    "id": pending.call_id,
                    "type": "function",
                    "function": {
                        "name": pending.name,
                        "arguments": pending.arguments_buffer,
                    },
                }
            )
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": pending.call_id,
                    "content": tool_execution.llm_result_content,
                }
            )

            if tool_execution.status == "blocked":
                yield make_envelope(
                    "error",
                    encoder.next_seq(),
                    {
                        "code": "agent_loop_blocked_tool_call",
                        "message": tool_execution.error_message
                        or "승인이 필요한 도구는 자동 실행할 수 없습니다.",
                        "retryable": False,
                    },
                )
                yield make_envelope(
                    "done",
                    encoder.next_seq(),
                    {
                        "finish_reason": "error",
                        "audit_id": None,
                        "meta": _build_done_meta(execution),
                    },
                )
                return

            if tool_execution.status == "error":
                consecutive_tool_errors += 1
                if consecutive_tool_errors >= max_consecutive_tool_errors:
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
                            "meta": _build_done_meta(execution),
                        },
                    )
                    return
            else:
                consecutive_tool_errors = 0

        conversation.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": assistant_tool_calls,
            }
        )
        conversation.extend(tool_messages)

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
            "meta": _build_done_meta(execution),
        },
    )
    return


def _prepend_agent_system_message(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        *[dict(message) for message in messages],
    ]


def _parse_tool_arguments(pending: _PendingToolCall) -> dict[str, Any]:
    if not pending.arguments_buffer.strip():
        return {}
    try:
        parsed = json.loads(pending.arguments_buffer)
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


def _build_done_meta(execution: ResolvedLlmExecution) -> dict[str, Any]:
    return {
        "policy": execution.decision.policy,
        "chosen_pool": execution.decision.chosen_pool,
        "decision_reason": execution.decision.reason,
        "forced_local": execution.decision.forced_local,
        "pii_hits": list(execution.decision.pii_hits),
        "model": execution.chosen_model,
        "chosen_model": execution.chosen_model,
        "canonical_model": execution.config.canonical_model,
        "provider": execution.config.provider,
    }
