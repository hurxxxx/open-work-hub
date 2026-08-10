from __future__ import annotations

import re
from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from open_work_hub_api.openapi_contract_rules import HTTP_METHODS, validate_openapi_contract_rules

METHOD_ORDER = ("get", "post", "put", "patch", "delete", "options", "head", "trace")


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
    return [finding.message for finding in validate_openapi_contract_rules(schema)]


def assert_openapi_contract(schema: dict[str, Any]) -> None:
    errors = validate_openapi_contract(schema)
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise AssertionError(f"OpenAPI contract quality check failed:\n{details}")
