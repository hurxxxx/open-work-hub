from __future__ import annotations

from typing import Any

from open_alm_api.core.llm_execution_adapters import supports_tool_calling


def stream_tool_calling_enabled(
    settings: Any,
    pool: str,
    provider: str | None = None,
) -> bool:
    if not bool(getattr(settings, "ai_tool_calling_enabled", False)):
        return False
    if pool == "local" and not bool(getattr(settings, "ai_local_tool_calling_enabled", False)):
        return False
    return supports_tool_calling(pool, provider)
