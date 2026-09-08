"""PMS domain package."""

from __future__ import annotations


def register_ai_capabilities(*args, **kwargs):
    from .tools import register_ai_capabilities as _register_ai_capabilities

    return _register_ai_capabilities(*args, **kwargs)


__all__ = ["register_ai_capabilities"]
