from __future__ import annotations

from datetime import datetime
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


MAX_RAW_JSON_BYTES = 64 * 1024
MAX_RESOLVED_GRANTS = 500
MAX_SEARCHABLE_CONTENT_BYTES = 120 * 1024 * 1024
MAX_EXTERNAL_ID_LENGTH = 1024
MAX_DELIVERY_ID_LENGTH = 1024
MAX_OPAQUE_VALUE_LENGTH = 4096

NonEmptyIdentifier = Annotated[str, Field(min_length=1, max_length=MAX_EXTERNAL_ID_LENGTH)]
OpaqueValue = Annotated[str, Field(min_length=1, max_length=MAX_OPAQUE_VALUE_LENGTH)]


class ResolvedGrant(BaseModel):
    """An upstream read grant already mapped to an authoritative AI-DO principal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_type: Literal["workspace", "company", "user", "org_unit", "team"]
    principal_id: Annotated[str, Field(min_length=1, max_length=36)] | None = None
    permission: Literal["read"] = "read"

    @model_validator(mode="after")
    def _validate_principal_identity(self) -> Self:
        if self.principal_type == "company":
            if self.principal_id is not None:
                raise ValueError("company grant is a singleton and must not have principal_id")
            return self
        if self.principal_id is None:
            raise ValueError(f"{self.principal_type} grant requires principal_id")
        return self


class McloudocChange(BaseModel):
    """Transport-neutral delivery accepted from a future mcloudoc adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["upsert", "delete"]
    external_id: NonEmptyIdentifier
    delivery_id: Annotated[str, Field(min_length=1, max_length=MAX_DELIVERY_ID_LENGTH)]
    opaque_revision: OpaqueValue | None = None
    checksum: OpaqueValue | None = None
    filename: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    content_type: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    size_bytes: Annotated[int, Field(ge=0, le=MAX_SEARCHABLE_CONTENT_BYTES)] | None = None
    searchable_content: (
        Annotated[
            bytes,
            Field(max_length=MAX_SEARCHABLE_CONTENT_BYTES),
        ]
        | None
    ) = None
    title: Annotated[str, Field(min_length=1, max_length=1024)] | None = None
    author: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    authored_at: datetime | None = None
    department: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    document_type: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    source_updated_at: datetime | None = None
    source_uri: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    raw_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    raw_acl: dict[str, JsonValue] | list[JsonValue] | None = None
    resolved_grants: tuple[ResolvedGrant, ...] = Field(
        default_factory=tuple,
        max_length=MAX_RESOLVED_GRANTS,
    )
    acl_resolution_complete: bool = False

    @field_validator("external_id", "delivery_id", "opaque_revision", "checksum")
    @classmethod
    def _reject_surrounding_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("identifier and opaque values must not have surrounding whitespace")
        return value

    @field_validator("raw_metadata", "raw_acl")
    @classmethod
    def _bound_raw_json(cls, value: object) -> object:
        if value is None:
            return value
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_RAW_JSON_BYTES:
            raise ValueError(f"raw JSON exceeds {MAX_RAW_JSON_BYTES} bytes")
        return value

    @model_validator(mode="after")
    def _validate_operation_shape(self) -> Self:
        if self.operation == "delete":
            if self.searchable_content is not None:
                raise ValueError("delete delivery must not include searchable_content")
            return self

        missing = [
            field
            for field in ("checksum", "filename", "content_type", "size_bytes")
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(f"upsert delivery is missing required fields: {', '.join(missing)}")
        if self.searchable_content is None:
            raise ValueError("upsert delivery is missing searchable_content")
        if self.size_bytes != len(self.searchable_content):
            raise ValueError("size_bytes does not match searchable_content length")
        return self


class StartIngestRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Annotated[str, Field(min_length=1, max_length=36)]
    mode: Literal["incremental", "snapshot"]
    delivery_id: Annotated[str, Field(min_length=1, max_length=MAX_DELIVERY_ID_LENGTH)]
    continuation: Annotated[str, Field(max_length=MAX_OPAQUE_VALUE_LENGTH)] | None = None


class CompleteIngestRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    continuation: Annotated[str, Field(max_length=MAX_OPAQUE_VALUE_LENGTH)] | None = None
    complete_snapshot: bool = False
