"""Versioned, non-secret deployment defaults; never reads credentials or a DB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class RuntimeConfigError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeConfigError("Runtime config contains a duplicate key.")
        result[key] = value
    return result


def load_runtime_document(root: Path) -> dict[str, Any]:
    try:
        document = json.loads(
            (root / "config/runtime.json").read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
        schema = json.loads((root / "config/runtime.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(document))
    except RuntimeConfigError:
        raise
    except Exception:
        raise RuntimeConfigError("Runtime config or schema is missing or invalid.") from None
    if errors:
        # Validation messages can contain the supplied values, including a misplaced secret.
        raise RuntimeConfigError("Runtime config contains missing, unknown or invalid settings.")
    return document


def runtime_defaults(root: Path, profile: str = "") -> dict[str, Any]:
    document = load_runtime_document(root)
    profile = profile.strip().lower()
    profile = {"development": "dev", "production": "prod"}.get(profile, profile) or "local"
    if profile not in document["profiles"]:
        raise RuntimeConfigError("Runtime config profile is not defined.")
    return {**document["defaults"], **document["profiles"][profile]}
