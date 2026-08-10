"""Thin unified retrieval entrypoint.

This package intentionally keeps the abstraction shallow: callers enter through
``application.py`` while RAG and keyword search services keep owning their
backend-specific behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: "AiCapabilityRegistry") -> None:
    from open_work_hub_api.domains.retrieval.tools import (
        register_ai_capabilities as _register_ai_capabilities,
    )

    _register_ai_capabilities(registry)


__all__ = ["register_ai_capabilities"]
