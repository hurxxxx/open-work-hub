from __future__ import annotations

import re
from collections import Counter
from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel, Field


HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})
METHOD_ORDER = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
PATH_DERIVED_MARKERS = ("_api_v1_", "__workspace_slug__", "__")


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]] = Field(..., description="Error detail.")
    code: str | None = Field(default=None, description="Stable application error code.")
    params: dict[str, Any] | None = Field(default=None, description="Error interpolation parameters.")


PROTECTED_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required."},
    403: {"model": ErrorResponse, "description": "Access denied."},
}


def _snake_case(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()
    return re.sub(r"_+", "_", normalized)


def _route_method(route: APIRoute) -> str:
    methods = {method.lower() for method in route.methods if method.lower() in HTTP_METHODS}
    methods.discard("head")
    methods.discard("options")
    for method in METHOD_ORDER:
        if method in methods:
            return method
    return sorted(methods)[0] if methods else "route"


def stable_operation_id(route: APIRoute) -> str:
    first_tag = _snake_case(str(route.tags[0])) if route.tags else "default"
    route_name = _snake_case(route.name)
    method = _route_method(route)
    return f"{first_tag}_{route_name}_{method}"


def validate_openapi_contract(schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    operation_ids: list[str] = []

    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                errors.append(f"{method.upper()} {path} is missing operationId.")
                continue
            operation_ids.append(operation_id)
            if not re.fullmatch(r"[a-z][a-z0-9_]*", operation_id):
                errors.append(f"{method.upper()} {path} has non-snake operationId {operation_id!r}.")
            for marker in PATH_DERIVED_MARKERS:
                if marker in operation_id:
                    errors.append(
                        f"{method.upper()} {path} has path-derived operationId {operation_id!r}."
                    )
                    break

    for operation_id, count in Counter(operation_ids).items():
        if count > 1:
            errors.append(f"operationId {operation_id!r} is duplicated {count} times.")

    schema_names = schema.get("components", {}).get("schemas", {})
    if isinstance(schema_names, dict):
        for schema_name in schema_names:
            if not isinstance(schema_name, str):
                continue
            for marker in PATH_DERIVED_MARKERS:
                if marker in schema_name:
                    errors.append(f"component schema {schema_name!r} includes path-derived text.")
                    break

    return errors


def assert_openapi_contract(schema: dict[str, Any]) -> None:
    errors = validate_openapi_contract(schema)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise AssertionError(f"OpenAPI contract quality check failed:\n{details}")
