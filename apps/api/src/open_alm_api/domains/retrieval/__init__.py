"""Thin unified retrieval entrypoint.

This package intentionally keeps the abstraction shallow: callers enter through
``application.py`` and the existing RAG, keyword search, QNA, and legacy issue
services keep owning their backend-specific behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_alm_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: "AiCapabilityRegistry") -> None:
    from open_alm_api.domains.retrieval.tools import (
        register_ai_capabilities as _register_ai_capabilities,
    )

    _register_ai_capabilities(registry)


__all__ = ["register_ai_capabilities"]
