from __future__ import annotations

import logging


_SENSITIVE_HTTP_LOGGER_NAMES = ("httpx", "httpx2", "httpcore")
_DISABLED_LEVEL = logging.CRITICAL + 1


def install_sensitive_http_logging_guard() -> None:
    """Prevent HTTP client internals from logging request URLs and query strings."""

    for logger_name in _SENSITIVE_HTTP_LOGGER_NAMES:
        client_logger = logging.getLogger(logger_name)
        client_logger.setLevel(_DISABLED_LEVEL)
        client_logger.propagate = False


__all__ = ["install_sensitive_http_logging_guard"]
