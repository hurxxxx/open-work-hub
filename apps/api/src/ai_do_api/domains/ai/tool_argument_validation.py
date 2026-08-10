from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


_LOCALIZED_TOOL_VALIDATION_ERROR_TYPES = frozenset(
    {
        "planner.update_mutable_field_required",
        "planner.update_start_at_end_at_required",
        "pms.update_mutable_field_required",
    }
)


@dataclass(frozen=True)
class ToolArgumentValidationResult:
    validated_arguments: dict[str, Any]
    parsed_args: BaseModel | Mapping[str, Any]


class ToolArgumentValidationFailure(Exception):
    def __init__(
        self,
        *,
        message: str,
        validation_error: ValidationError,
        localized_error: tuple[str, dict[str, Any]] | None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.validation_error = validation_error
        self.localized_error = localized_error

    @property
    def generic_reason(self) -> str:
        return self.message.removeprefix("Invalid tool arguments: ")


def validate_tool_arguments(
    *,
    args_model: type[BaseModel] | None,
    arguments: Mapping[str, Any],
) -> ToolArgumentValidationResult:
    if args_model is None:
        validated_arguments = dict(arguments)
        return ToolArgumentValidationResult(
            validated_arguments=validated_arguments,
            parsed_args=validated_arguments,
        )

    try:
        parsed_args = args_model.model_validate(dict(arguments))
    except ValidationError as error:
        raise ToolArgumentValidationFailure(
            message=validation_error_message(error),
            validation_error=error,
            localized_error=localized_tool_validation_error(error),
        ) from error

    return ToolArgumentValidationResult(
        validated_arguments=parsed_args.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        ),
        parsed_args=parsed_args,
    )


def validation_error_message(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", []))
        message = item.get("msg", "Invalid value.")
        if location:
            parts.append(f"{location}: {message}")
        else:
            parts.append(str(message))
    if not parts:
        return "Invalid tool arguments."
    return "Invalid tool arguments: " + "; ".join(parts)


def localized_tool_validation_error(
    error: ValidationError,
) -> tuple[str, dict[str, Any]] | None:
    errors = error.errors()
    if len(errors) != 1:
        return None
    item = errors[0]
    error_type = item.get("type")
    if (
        not isinstance(error_type, str)
        or error_type not in _LOCALIZED_TOOL_VALIDATION_ERROR_TYPES
    ):
        return None
    params = item.get("ctx") if isinstance(item.get("ctx"), dict) else {}
    return error_type, dict(params)
