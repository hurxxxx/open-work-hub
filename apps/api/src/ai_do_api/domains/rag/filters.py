from __future__ import annotations

import re
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError


FilterScalar: TypeAlias = str | int | bool
FilterValue: TypeAlias = FilterScalar | list[FilterScalar]
_METADATA_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_:-]+$")
_RESERVED_FILTER_KEYS = {
    "workspace_id",
    "resource_type",
    "resource_id",
    "source_kind",
    "visibility_refs_contains",
}


class RagQueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    resource_id: str | None = Field(default=None, min_length=1, max_length=255)
    visibility_refs_contains: str | None = Field(default=None, min_length=1, max_length=256)
    metadata: dict[str, FilterValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, FilterValue]) -> dict[str, FilterValue]:
        for key, item in value.items():
            if not key or len(key) > 64:
                raise PydanticCustomError(
                    "rag.metadata_filter_key_length",
                    "Metadata filter keys must be between 1 and 64 characters.",
                    {},
                )
            if key in _RESERVED_FILTER_KEYS:
                raise PydanticCustomError(
                    "rag.metadata_filter_key_reserved",
                    "Metadata filter key is reserved: {key}",
                    {"key": key},
                )
            if key.startswith("metadata.") or not _METADATA_KEY_PATTERN.fullmatch(key):
                raise PydanticCustomError(
                    "rag.metadata_filter_key_invalid",
                    "Invalid metadata filter key: {key}",
                    {"key": key},
                )
            _validate_filter_value(item)
        return value

    def to_flat_dict(self) -> dict[str, FilterValue]:
        flattened: dict[str, FilterValue] = {}
        if self.resource_type is not None:
            flattened["resource_type"] = self.resource_type
        if self.resource_id is not None:
            flattened["resource_id"] = self.resource_id
        if self.visibility_refs_contains is not None:
            flattened["visibility_refs_contains"] = self.visibility_refs_contains
        flattened.update(self.metadata)
        return flattened


def _validate_filter_value(value: FilterValue) -> None:
    if isinstance(value, bool | int | str):
        return
    if isinstance(value, list):
        if not value:
            raise PydanticCustomError(
                "rag.metadata_filter_list_empty",
                "Metadata filter lists must not be empty.",
                {},
            )
        if not all(isinstance(item, bool | int | str) for item in value):
            raise PydanticCustomError(
                "rag.metadata_filter_list_scalar_required",
                "Metadata filter lists must contain only string/int/bool values.",
                {},
            )
        return
    raise PydanticCustomError(
        "rag.metadata_filter_value_invalid",
        "Metadata filter values must be string/int/bool or a list of those values.",
        {},
    )
