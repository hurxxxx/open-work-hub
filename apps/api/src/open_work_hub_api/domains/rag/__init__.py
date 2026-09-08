"""RAG domain package."""

from __future__ import annotations


def register_ai_capabilities(registry) -> None:
    from open_work_hub_api.domains.rag.tools import (
        register_ai_capabilities as _register_ai_capabilities,
    )

    _register_ai_capabilities(registry)


__all__ = ["register_ai_capabilities"]
