"""RAG domain package."""

from __future__ import annotations

from aidoo_api.core.settings import get_settings


def register_ai_capabilities(registry) -> None:
    if not get_settings().rag_enabled:
        return
    from aidoo_api.domains.rag.tools import register_ai_capabilities as _register_ai_capabilities

    _register_ai_capabilities(registry)


__all__ = ["register_ai_capabilities"]
