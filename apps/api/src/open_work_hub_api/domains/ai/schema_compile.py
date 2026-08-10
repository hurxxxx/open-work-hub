from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

ToolArgsModel = type[BaseModel]

ARRAY_VALIDATION_KEYWORDS = ("minItems", "maxItems", "uniqueItems")
SCALAR_VALIDATION_KEYWORDS = (
    "default",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    *ARRAY_VALIDATION_KEYWORDS,
)


def compile_input_schemas(model: ToolArgsModel | None) -> tuple[dict[str, Any], dict[str, Any]]:
    mcp_schema = _build_mcp_input_schema(model)
    return mcp_schema, _build_strict_tool_input_schema(mcp_schema)


def _build_mcp_input_schema(model: ToolArgsModel | None) -> dict[str, Any]:
    if model is None:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    raw_schema = model.model_json_schema(by_alias=True, mode="validation")
    definitions = raw_schema.get("$defs", {})
    normalized = _normalize_schema(raw_schema, definitions=definitions)
    normalized["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return normalized


def _normalize_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    if "$ref" in schema:
        return _normalize_ref(schema["$ref"], definitions=definitions)

    if "allOf" in schema or "not" in schema or "patternProperties" in schema:
        raise ValueError(f"Unsupported JSON schema construct: {sorted(schema.keys())}")
    if "if" in schema or "then" in schema or "else" in schema:
        raise ValueError("Conditional JSON schema constructs are not supported.")

    if "anyOf" in schema or "oneOf" in schema:
        branches = schema.get("anyOf") or schema.get("oneOf")
        if not isinstance(branches, list):
            raise ValueError("Union schema must be a list.")
        normalized = _normalize_nullable_union(branches, definitions=definitions)
        normalized.update(_copy_scalar_metadata(schema))
        return normalized

    schema_type = schema.get("type")
    if schema_type == "object":
        return _normalize_object_schema(schema, definitions=definitions)
    if schema_type == "array":
        return _normalize_array_schema(schema, definitions=definitions)
    if isinstance(schema_type, list):
        return _normalize_type_list_schema(schema)
    if schema_type in {"string", "number", "integer", "boolean", "null"}:
        return _normalize_scalar_schema(schema)
    if "enum" in schema:
        return _normalize_scalar_schema(schema)

    raise ValueError(f"Unsupported JSON schema node: {schema}")


def _normalize_ref(ref: Any, *, definitions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ValueError(f"External JSON schema refs are not supported: {ref!r}")
    key = ref.split("/", 2)[-1]
    target = definitions.get(key)
    if not isinstance(target, Mapping):
        raise ValueError(f"Missing local JSON schema ref target: {ref!r}")
    return _normalize_schema(target, definitions=definitions)


def _normalize_nullable_union(
    branches: list[Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    if len(branches) != 2:
        raise ValueError("Only nullable unions are supported.")
    normalized_branches = [
        _normalize_schema(branch, definitions=definitions)
        for branch in branches
        if isinstance(branch, Mapping)
    ]
    if len(normalized_branches) != 2:
        raise ValueError("Union branches must be JSON schema objects.")
    null_branch = next(
        (branch for branch in normalized_branches if branch.get("type") == "null"),
        None,
    )
    non_null_branch = next(
        (branch for branch in normalized_branches if branch.get("type") != "null"),
        None,
    )
    if null_branch is None or non_null_branch is None:
        raise ValueError("Only nullable unions are supported.")
    return _make_schema_nullable(non_null_branch)


def _normalize_object_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        raise ValueError("Object schema properties must be a mapping.")
    normalized_properties: dict[str, Any] = {}
    for key in sorted((properties or {}).keys()):
        property_schema = properties[key]
        if not isinstance(property_schema, Mapping):
            raise ValueError(f"Object property {key!r} must be a schema mapping.")
        normalized_properties[key] = _normalize_schema(
            property_schema,
            definitions=definitions,
        )
    required = schema.get("required")
    required_values = []
    if required is not None:
        if not isinstance(required, list):
            raise ValueError("Object schema required must be a list.")
        required_values = [str(item) for item in required]
    return {
        "type": "object",
        "properties": normalized_properties,
        "required": required_values,
        "additionalProperties": False,
        **_copy_scalar_metadata(schema),
    }


def _normalize_array_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    items = schema.get("items")
    if not isinstance(items, Mapping):
        raise ValueError("Array schema items must be a schema object.")
    normalized = {
        "type": "array",
        "items": _normalize_schema(items, definitions=definitions),
        **_copy_scalar_metadata(schema),
        **_copy_schema_keywords(schema, ARRAY_VALIDATION_KEYWORDS),
    }
    return normalized


def _normalize_type_list_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    schema_type = schema.get("type")
    if not isinstance(schema_type, list):
        raise ValueError("Expected list-based schema type.")
    filtered_types = [str(item) for item in schema_type]
    supported = {"string", "number", "integer", "boolean", "array", "object", "null"}
    if not set(filtered_types) <= supported:
        raise ValueError(f"Unsupported union types: {filtered_types}")
    normalized = _normalize_scalar_schema({**schema, "type": filtered_types})
    if "object" in filtered_types:
        normalized["additionalProperties"] = False
        normalized.setdefault("properties", {})
        normalized.setdefault("required", [])
    return normalized


def _normalize_scalar_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        normalized["type"] = [str(item) for item in schema_type]
    elif schema_type is not None:
        normalized["type"] = _normalize_scalar_type(str(schema_type))
    if "enum" in schema:
        enum_values = schema.get("enum")
        if not isinstance(enum_values, list):
            raise ValueError("Enum schema values must be a list.")
        normalized["enum"] = list(enum_values)
    normalized.update(_copy_scalar_metadata(schema))
    normalized.update(_copy_schema_keywords(schema, SCALAR_VALIDATION_KEYWORDS))
    return normalized


def _normalize_scalar_type(schema_type: str) -> str:
    if schema_type not in {"string", "number", "integer", "boolean", "null"}:
        raise ValueError(f"Unsupported scalar JSON schema type: {schema_type}")
    return schema_type


def _copy_scalar_metadata(schema: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("title", "description"):
        value = schema.get(key)
        if isinstance(value, str) and value.strip():
            metadata[key] = value
    return metadata


def _copy_schema_keywords(
    schema: Mapping[str, Any],
    keywords: tuple[str, ...],
) -> dict[str, Any]:
    return {key: schema[key] for key in keywords if schema.get(key) is not None}


def _build_strict_tool_input_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("Strict schema object properties must be a mapping.")
        original_required = set(schema.get("required", []))
        strict_properties: dict[str, Any] = {}
        for key, value in properties.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"Strict schema property {key!r} must be a mapping.")
            child = _build_strict_tool_input_schema(value)
            if key not in original_required:
                child = _make_schema_nullable(child)
            strict_properties[str(key)] = child
        strict_schema: dict[str, Any] = {
            "type": "object",
            "properties": strict_properties,
            "required": list(strict_properties.keys()),
            "additionalProperties": False,
        }
        strict_schema.update(_copy_scalar_metadata(schema))
        return strict_schema
    if schema.get("type") == "array":
        items = schema.get("items")
        if not isinstance(items, Mapping):
            raise ValueError("Strict schema array items must be a mapping.")
        normalized = {
            "type": "array",
            "items": _build_strict_tool_input_schema(items),
        }
        normalized.update(_copy_scalar_metadata(schema))
        normalized.update(_copy_schema_keywords(schema, ARRAY_VALIDATION_KEYWORDS))
        return normalized
    if "type" in schema:
        normalized = dict(schema)
        if normalized.get("type") == "object":
            normalized["additionalProperties"] = False
            normalized.setdefault("properties", {})
            normalized.setdefault("required", [])
        return normalized
    raise ValueError(f"Unsupported strict schema node: {schema}")


def _make_schema_nullable(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(schema)
    schema_type = normalized.get("type")
    if isinstance(schema_type, list):
        if "null" not in schema_type:
            normalized["type"] = [*schema_type, "null"]
        return normalized
    if isinstance(schema_type, str):
        if schema_type == "null":
            return normalized
        normalized["type"] = [schema_type, "null"]
        return normalized
    raise ValueError(f"Cannot make schema nullable without type: {schema}")
