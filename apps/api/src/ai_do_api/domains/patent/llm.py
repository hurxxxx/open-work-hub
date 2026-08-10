"""LLM helpers for the patent domain.

Thin wrappers over the AI Gateway text completion path. ``generate_json`` ports
the markdown-fence stripping and unbalanced-bracket repair from the legacy
``_call_gemini_json`` helper.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.core.llm import LlmTaskContext
from ai_do_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)

# Patent generations (search-formula, reports, claim analysis) map to the
# dedicated ``patent_analysis`` workload. The registry default is local and a
# platform administrator may select an approved external provider/model.
_TASK_KIND = "patent_analysis"
_DEFAULT_TIMEOUT_SECONDS = 180.0


def generate_text(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    conversation_id: str | None = None,
) -> str:
    """Run a single-turn completion and return the assistant text."""
    context = LlmTaskContext(
        source="patent",
        workspace_id=workspace_id,
        task_kind=_TASK_KIND,
        app_id="patent-analysis",
        actor_user_id=actor_user_id,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    completion = execute_llm(
        _TASK_KIND,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort="none",
        timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        conversation_id=conversation_id,
    ).completion
    return completion.text.strip()


def generate_json(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str,
    prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Run a completion expecting JSON and parse it, repairing if needed."""
    raw = generate_text(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        prompt=prompt
        + "\n\n응답은 반드시 유효한 JSON 형식으로만 작성하세요. 설명 없이 JSON만 출력하세요.",
        max_tokens=max_tokens,
        temperature=temperature,
        conversation_id=conversation_id,
    )
    parsed = parse_json_lenient(raw)
    return parsed if isinstance(parsed, dict) else {}


def parse_json_lenient(raw: str) -> Any:
    """Parse model JSON, stripping ``` fences and repairing truncated output.

    Ported from the legacy ``_call_gemini_json``: closes an unbalanced quote
    and any unclosed arrays/objects, then falls back to ``{}`` on failure.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        fixed = cleaned
        if fixed.count('"') % 2 == 1:
            fixed += '"'
        open_brackets = fixed.count("[") - fixed.count("]")
        open_braces = fixed.count("{") - fixed.count("}")
        fixed += "]" * max(open_brackets, 0)
        fixed += "}" * max(open_braces, 0)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return {}
