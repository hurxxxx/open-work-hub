from typing import Any

from ai_do_api.core.i18n import LocalizedApiMessage, translate_message


LOCALIZED_VALIDATION_ERROR_TYPES = frozenset(
    {
        "admin.invalid_workspace_role",
        "ai.unknown_workspace_app",
        "auth.invalid_locale",
        "auth.invalid_time_zone",
        "auth.invalid_date_format",
        "auth.invalid_app_bar_layout",
        "auth.password_confirmation_mismatch",
        "auth.valid_email_required",
        "auth.valid_login_id_required",
        "conversations.scope_pair_required",
        "conversations.unsupported_scope",
        "rag.metadata_filter_key_invalid",
        "rag.metadata_filter_key_length",
        "rag.metadata_filter_key_reserved",
        "rag.metadata_filter_list_empty",
        "rag.metadata_filter_list_scalar_required",
        "rag.metadata_filter_value_invalid",
    }
)
GENERIC_VALIDATION_ERROR_TYPES: dict[str, str] = {
    "bool_parsing": "validation.bool_type",
    "bool_type": "validation.bool_type",
    "date_from_datetime_inexact": "validation.date_type",
    "date_from_datetime_parsing": "validation.date_type",
    "date_parsing": "validation.date_type",
    "date_type": "validation.date_type",
    "datetime_from_date_parsing": "validation.datetime_type",
    "datetime_parsing": "validation.datetime_type",
    "datetime_type": "validation.datetime_type",
    "dict_type": "validation.object_type",
    "extra_forbidden": "validation.extra_forbidden",
    "float_parsing": "validation.float_type",
    "float_type": "validation.float_type",
    "greater_than": "validation.greater_than",
    "greater_than_equal": "validation.greater_than_equal",
    "int_parsing": "validation.integer_type",
    "int_type": "validation.integer_type",
    "less_than": "validation.less_than",
    "less_than_equal": "validation.less_than_equal",
    "list_type": "validation.array_type",
    "literal_error": "validation.literal_error",
    "missing": "validation.field_required",
    "model_attributes_type": "validation.object_type",
    "string_too_long": "validation.string_too_long",
    "string_too_short": "validation.string_too_short",
    "string_type": "validation.string_type",
    "too_long": "validation.too_long",
    "too_short": "validation.too_short",
}


GENERIC_VALIDATION_PARAM_KEYS = frozenset(
    {
        "actual_length",
        "expected",
        "ge",
        "gt",
        "le",
        "lt",
        "max_length",
        "min_length",
    }
)


def build_request_validation_error_body(
    errors: list[dict[str, Any]],
    locale: str,
) -> tuple[dict[str, object], str]:
    first_message = _first_domain_validation_message(errors)
    if first_message is None:
        first_message = LocalizedApiMessage(code="validation.request_invalid")

    body: dict[str, object] = {
        "detail": translate_message(first_message, locale),
        "code": first_message.code,
        "validation": [_localized_validation_item(error, locale) for error in errors],
    }
    if first_message.params:
        body["params"] = first_message.params
    return body, first_message.code


def _first_domain_validation_message(
    errors: list[dict[str, Any]],
) -> LocalizedApiMessage | None:
    for error in errors:
        error_type = error.get("type")
        if not isinstance(error_type, str) or error_type not in LOCALIZED_VALIDATION_ERROR_TYPES:
            continue
        params = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
        return LocalizedApiMessage(code=error_type, params=dict(params))
    return None


def _localized_validation_item(error: dict[str, Any], locale: str) -> dict[str, object]:
    error_type = error.get("type")
    message = _validation_message_for_error(error)
    return {
        "loc": list(error.get("loc", ())),
        "type": error_type if isinstance(error_type, str) else "unknown",
        "message": translate_message(message, locale),
    }


def _validation_message_for_error(error: dict[str, Any]) -> LocalizedApiMessage:
    error_type = error.get("type")
    if isinstance(error_type, str) and error_type in LOCALIZED_VALIDATION_ERROR_TYPES:
        params = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
        return LocalizedApiMessage(code=error_type, params=dict(params))
    code = (
        GENERIC_VALIDATION_ERROR_TYPES.get(error_type)
        if isinstance(error_type, str)
        else None
    ) or "validation.value_invalid"
    return LocalizedApiMessage(code=code, params=_generic_validation_params(error))


def _generic_validation_params(error: dict[str, Any]) -> dict[str, object]:
    ctx = error.get("ctx")
    if not isinstance(ctx, dict):
        return {}
    return {
        key: value
        for key, value in ctx.items()
        if key in GENERIC_VALIDATION_PARAM_KEYS and isinstance(value, str | int | float | bool)
    }
