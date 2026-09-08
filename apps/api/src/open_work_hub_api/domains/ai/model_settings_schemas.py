from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

AiModelProviderId = Annotated[
    str,
    Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]{0,31}$"),
]
AiModelRouteMode = Literal["local", "external"]
AiModelCredentialKind = Literal["none", "api_key"]
AiModelEndpointSource = Literal["default", "custom"]
AiModelCatalogSource = Literal["manual", "discovered"]
AiModelDiscoveryStatus = Literal["active", "stale"]
AiModelCapability = Literal[
    "chat",
    "tool_calling",
    "vision",
]


class AiModelProviderResponse(BaseModel):
    provider_id: AiModelProviderId
    display_name: str
    route_mode: AiModelRouteMode
    credential_kind: AiModelCredentialKind
    enabled: bool
    endpoint_url: str | None = None
    endpoint_source: AiModelEndpointSource
    has_api_key: bool
    default_model_id: str | None = None
    version: int
    updated_at: datetime | None = None


class AiModelCatalogEntryResponse(BaseModel):
    id: str
    provider_id: AiModelProviderId
    model_key: str
    display_name: str
    capabilities: list[AiModelCapability]
    enabled: bool
    source: AiModelCatalogSource
    discovery_status: AiModelDiscoveryStatus
    last_seen_at: datetime | None = None
    version: int
    updated_at: datetime | None = None


class AiModelRouteOverrideResponse(BaseModel):
    route_mode: AiModelRouteMode
    provider_id: AiModelProviderId | None = None
    model_ids: dict[str, str] = Field(default_factory=dict)
    local_max_output_tokens: int | None = None
    external_max_output_tokens: int | None = None
    runtime_adapter_id: str | None = None
    version: int
    updated_at: datetime | None = None


class AiModelResolvedRouteResponse(BaseModel):
    model_role: str
    provider_id: AiModelProviderId
    model_key: str
    route_source: Literal["default", "override"]
    config_source: Literal["database", "legacy_env", "database_with_legacy_env"]
    max_output_tokens: int


class AiAgentRuntimeAdapterResponse(BaseModel):
    adapter_id: str
    display_name: str
    allowed_routes: list[AiModelRouteMode]
    allowed_providers: list[str]


class AiModelWorkloadResponse(BaseModel):
    workload_id: str
    task_kind: str
    owner_domain: str
    app_ids: list[str]
    description: str
    label_key: str
    description_key: str
    execution_kind: str
    default_runtime_adapter: str
    effective_runtime_adapter: str
    allowed_runtime_adapters: list[str]
    runtime_adapters: list[AiAgentRuntimeAdapterResponse]
    default_route: AiModelRouteMode
    effective_route: AiModelRouteMode
    allowed_routes: list[AiModelRouteMode]
    allowed_providers: list[str]
    required_capabilities: list[str]
    model_roles: list[str]
    external_data: bool
    local_max_output_tokens: int
    external_max_output_tokens: int
    ready: bool
    readiness_code: str | None = None
    resolved_routes: list[AiModelResolvedRouteResponse] = Field(default_factory=list)
    override: AiModelRouteOverrideResponse | None = None
    management_surface: Literal["llm_routing", "document_processing"]


class AiModelOrphanedOverrideResponse(BaseModel):
    workload_id: str
    route_mode: AiModelRouteMode
    provider_id: AiModelProviderId | None = None
    model_ids: dict[str, str] = Field(default_factory=dict)
    local_max_output_tokens: int | None = None
    external_max_output_tokens: int | None = None
    runtime_adapter_id: str | None = None
    version: int
    updated_at: datetime | None = None


class AiModelSettingsResponse(BaseModel):
    registry_digest: str
    providers: list[AiModelProviderResponse]
    models: list[AiModelCatalogEntryResponse]
    workloads: list[AiModelWorkloadResponse]
    orphaned_overrides: list[AiModelOrphanedOverrideResponse]


class AiModelRegistryMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_registry_digest: str = Field(min_length=64, max_length=64)


class AiModelDiscoveryRequest(AiModelRegistryMutationRequest):
    pass


class AiModelProviderUpdateRequest(AiModelRegistryMutationRequest):
    expected_version: int | None = Field(default=None, ge=0)
    enabled: bool
    endpoint_url: str | None = Field(default=None, max_length=2048)
    default_model_id: str | None = Field(default=None, max_length=64)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192, repr=False)
    clear_api_key: bool = False

    @field_validator("endpoint_url")
    @classmethod
    def _normalize_endpoint_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        return normalized or None

    @model_validator(mode="after")
    def _validate_api_key_action(self) -> "AiModelProviderUpdateRequest":
        if self.api_key is not None and self.clear_api_key:
            raise ValueError("api_key and clear_api_key cannot be used together")
        return self


class AiModelCatalogCreateRequest(AiModelRegistryMutationRequest):
    provider_id: AiModelProviderId
    model_key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    capabilities: list[AiModelCapability] = Field(min_length=1, max_length=10)
    enabled: bool = True

    @field_validator("model_key", "display_name")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("capabilities")
    @classmethod
    def _deduplicate_capabilities(
        cls,
        value: list[AiModelCapability],
    ) -> list[AiModelCapability]:
        return list(dict.fromkeys(value))


class AiModelCatalogUpdateRequest(AiModelRegistryMutationRequest):
    expected_version: int = Field(ge=1)
    model_key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    capabilities: list[AiModelCapability] = Field(min_length=1, max_length=10)
    enabled: bool

    @field_validator("model_key", "display_name")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("capabilities")
    @classmethod
    def _deduplicate_capabilities(
        cls,
        value: list[AiModelCapability],
    ) -> list[AiModelCapability]:
        return list(dict.fromkeys(value))


class AiModelRouteOverrideUpdateRequest(AiModelRegistryMutationRequest):
    expected_version: int | None = Field(default=None, ge=0)
    route_mode: AiModelRouteMode
    provider_id: AiModelProviderId | None = None
    model_ids: dict[str, str] = Field(default_factory=dict, max_length=10)
    local_max_output_tokens: int | None = Field(
        default=None,
        ge=1024,
        le=65536,
        multiple_of=1024,
    )
    external_max_output_tokens: int | None = Field(
        default=None,
        ge=1024,
        le=65536,
        multiple_of=1024,
    )
    runtime_adapter_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]{0,63}$",
    )

    @field_validator("model_ids")
    @classmethod
    def _normalize_model_ids(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {
            str(role).strip().lower(): str(model_id).strip()
            for role, model_id in value.items()
            if str(role).strip() and str(model_id).strip()
        }
        if len(normalized) != len(value):
            raise ValueError("model role and model id must not be blank")
        return normalized


__all__ = [
    "AiModelCatalogCreateRequest",
    "AiModelCatalogEntryResponse",
    "AiModelCatalogUpdateRequest",
    "AiModelProviderResponse",
    "AiModelProviderUpdateRequest",
    "AiModelRouteOverrideResponse",
    "AiModelRouteOverrideUpdateRequest",
    "AiModelSettingsResponse",
]
