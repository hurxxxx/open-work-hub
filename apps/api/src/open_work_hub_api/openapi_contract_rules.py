from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})
PATH_DERIVED_MARKERS = ("_api_v1_", "__")


@dataclass(frozen=True)
class OpenApiContractFinding:
    message: str


def validate_openapi_contract_rules(schema: dict[str, Any]) -> list[OpenApiContractFinding]:
    findings: list[OpenApiContractFinding] = []
    operation_ids: list[str] = []

    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                findings.append(
                    OpenApiContractFinding(f"{method.upper()} {path} is missing operationId.")
                )
                continue
            operation_ids.append(operation_id)
            if not re.fullmatch(r"[a-z][a-z0-9_]*", operation_id):
                findings.append(
                    OpenApiContractFinding(
                        f"{method.upper()} {path} has non-snake operationId {operation_id!r}."
                    )
                )
            if _contains_path_derived_marker(operation_id):
                findings.append(
                    OpenApiContractFinding(
                        f"{method.upper()} {path} has path-derived operationId {operation_id!r}."
                    )
                )

    for operation_id, count in Counter(operation_ids).items():
        if count > 1:
            findings.append(
                OpenApiContractFinding(f"operationId {operation_id!r} is duplicated {count} times.")
            )

    schema_names = schema.get("components", {}).get("schemas", {})
    if isinstance(schema_names, dict):
        for schema_name in schema_names:
            if not isinstance(schema_name, str):
                continue
            if _contains_path_derived_marker(schema_name):
                findings.append(
                    OpenApiContractFinding(
                        f"component schema {schema_name!r} includes path-derived text."
                    )
                )

    return findings


def _contains_path_derived_marker(value: str) -> bool:
    return any(marker in value for marker in PATH_DERIVED_MARKERS)
