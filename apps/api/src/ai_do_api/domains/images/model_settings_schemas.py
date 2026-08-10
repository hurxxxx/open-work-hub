from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


ImageProviderId = Annotated[
    str,
    Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]{0,31}$"),
]
ImageProviderRouteMode = Literal["local", "external"]
ImageProviderCredentialKind = Literal["none", "api_key"]
ImageProviderEndpointSource = Literal["default", "custom"]


class ImageModelProviderResponse(BaseModel):
    provider_id: ImageProviderId
    display_name: str
    route_mode: ImageProviderRouteMode
    credential_kind: ImageProviderCredentialKind
    enabled: bool
    endpoint_url: str | None = None
    endpoint_source: ImageProviderEndpointSource
    has_api_key: bool
    supervisor_model_id: str | None = None
    generation_model_id: str | None = None
    ready: bool
    readiness_code: str | None = None
    version: int
    updated_at: datetime | None = None


class ImageModelProfileResponse(BaseModel):
    active_provider_id: ImageProviderId | None = None
    brief_web_search_enabled: bool
    generation_web_search_enabled: bool
    max_iterations: int
    version: int
    updated_at: datetime | None = None


class ImageModelSettingsResponse(BaseModel):
    registry_digest: str
    deployment_enabled: bool
    ready: bool
    readiness_code: str | None = None
    providers: list[ImageModelProviderResponse]
    profile: ImageModelProfileResponse


class ImageModelRegistryMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_registry_digest: str = Field(min_length=64, max_length=64)


class ImageModelProviderUpdateRequest(ImageModelRegistryMutationRequest):
    expected_version: int = Field(ge=0)
    enabled: bool
    endpoint_url: str | None = Field(default=None, max_length=2048)
    supervisor_model_id: str | None = Field(default=None, max_length=160)
    generation_model_id: str | None = Field(default=None, max_length=160)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192, repr=False)
    clear_api_key: bool = False

    @field_validator("endpoint_url")
    @classmethod
    def _normalize_endpoint_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().rstrip("/") or None

    @field_validator("supervisor_model_id", "generation_model_id")
    @classmethod
    def _normalize_model_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def _validate_api_key_action(self) -> "ImageModelProviderUpdateRequest":
        if self.api_key is not None and self.clear_api_key:
            raise ValueError("api_key and clear_api_key cannot be used together")
        return self


class ImageModelProfileUpdateRequest(ImageModelRegistryMutationRequest):
    expected_version: int = Field(ge=1)
    active_provider_id: ImageProviderId | None = None
    brief_web_search_enabled: bool
    generation_web_search_enabled: bool
    max_iterations: int = Field(ge=1, le=20)


__all__ = [
    "ImageModelProfileResponse",
    "ImageModelProfileUpdateRequest",
    "ImageModelProviderResponse",
    "ImageModelProviderUpdateRequest",
    "ImageModelSettingsResponse",
    "ImageProviderId",
]
