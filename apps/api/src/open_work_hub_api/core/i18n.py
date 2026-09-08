from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from open_work_hub_api.core.i18n_catalog import (
    DEFAULT_LOCALE,
    ERROR_CODE_HEADER,
    MESSAGE_PARAM_VALUE_TRANSLATIONS,
    MESSAGES,
    PARAM_VALUE_TRANSLATIONS,
    SUPPORTED_LOCALES,
    LocalizedApiMessage,
    normalize_locale,
    select_locale,
    translate_message,
    translate_param_value,
)

__all__ = [
    "DEFAULT_LOCALE",
    "ERROR_CODE_HEADER",
    "MESSAGES",
    "MESSAGE_PARAM_VALUE_TRANSLATIONS",
    "PARAM_VALUE_TRANSLATIONS",
    "SUPPORTED_LOCALES",
    "LocalizedApiMessage",
    "localized_http_exception",
    "normalize_locale",
    "select_locale",
    "translate_message",
    "translate_param_value",
]


def localized_http_exception(
    *,
    status_code: int,
    code: str,
    headers: dict[str, str] | None = None,
    **params: Any,
) -> HTTPException:
    merged_headers = {ERROR_CODE_HEADER: code}
    if headers:
        merged_headers.update(headers)
    return HTTPException(
        status_code=status_code,
        detail=LocalizedApiMessage(code=code, params=params),
        headers=merged_headers,
    )
