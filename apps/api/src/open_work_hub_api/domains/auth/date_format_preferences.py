from __future__ import annotations

from pydantic_core import PydanticCustomError

from open_work_hub_api.domains.auth.access import normalize_date_format


def invalid_date_format_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.invalid_date_format",
        "Invalid date format.",
        {},
    )


def normalize_date_format_payload(data: object) -> object:
    if not isinstance(data, dict) or data.get("date_format") is None:
        return data
    value = data.get("date_format")
    if not isinstance(value, str):
        raise invalid_date_format_error()
    try:
        normalized = normalize_date_format(value)
    except ValueError as exc:
        raise invalid_date_format_error() from exc
    return {**data, "date_format": normalized}


def validate_date_format_value(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_date_format(value)
    except ValueError as exc:
        raise invalid_date_format_error() from exc


def default_date_format_value() -> str:
    return normalize_date_format(None)
