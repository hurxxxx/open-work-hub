from __future__ import annotations

from dataclasses import dataclass

from open_work_hub_api.domains.ai.runtime.contracts import RuntimeProfile


LONG_DOC_CHAR_THRESHOLD = 12_000
LONG_DOC_MAX_TOKENS_THRESHOLD = 32_768


@dataclass(frozen=True)
class RuntimeProfileSignal:
    runtime_profile: RuntimeProfile
    reason_codes: tuple[str, ...]


def select_runtime_profile_signal(
    *,
    messages: list[dict[str, str]],
    allowed_app_ids: list[str] | None,
    max_tokens: int | None,
) -> RuntimeProfileSignal:
    text = message_text(messages)
    reason_codes: list[str] = []

    if allowed_app_ids == []:
        reason_codes.append("text_only_scope")

    if max_tokens is not None and max_tokens >= LONG_DOC_MAX_TOKENS_THRESHOLD:
        reason_codes.append("large_output_budget")
        return RuntimeProfileSignal("long_doc", tuple(reason_codes))

    if len(text) >= LONG_DOC_CHAR_THRESHOLD:
        reason_codes.append("large_input")
        return RuntimeProfileSignal("long_doc", tuple(reason_codes))

    if has_multiple_app_scope(allowed_app_ids):
        reason_codes.append("multi_app_scope")
        return RuntimeProfileSignal("grounded_report", tuple(reason_codes))

    reason_codes.append("default_interactive_read")
    return RuntimeProfileSignal("interactive_read", tuple(reason_codes))


def message_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(str(message.get("content") or "") for message in messages)


def has_multiple_app_scope(allowed_app_ids: list[str] | None) -> bool:
    return allowed_app_ids is not None and len(set(allowed_app_ids)) > 1
