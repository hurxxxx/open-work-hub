from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.settings import (
    HERMES_FALLBACK_MODEL,
    HERMES_MODEL,
    HERMES_PROVIDER,
    HERMES_RELEASE,
    get_settings,
)
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_admin_context
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import (
    HermesDispatchOutbox,
    HermesMaintenanceState,
    HermesProfileBinding,
    HermesRunProjection,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.repository import ACTIVE_RUN_STATUSES
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
)
from open_work_hub_api.domains.hermes_terminal.models import HermesTerminalSession
from open_work_hub_api.domains.hermes.research_settings import (
    HermesResearchSettingsConflictError,
    HermesResearchSettingsSnapshot,
    get_research_settings,
    get_research_source_policy,
    update_research_source,
)
from open_work_hub_api.domains.hermes.research_sources import (
    RESEARCH_SOURCE_DEFINITIONS,
    ResearchSourceId,
)
from open_work_hub_api.domains.hermes.service import (
    ensure_profile_binding,
    internal_mcp_server_name,
    is_profile_scoped_mcp_server,
    management_client,
    runtime_client,
    scoped_mcp_server_name,
    invalidate_profile_policy_cache,
)


router = APIRouter(prefix="/admin/hermes", tags=["admin-hermes"])


class AdminHermesSummaryResponse(BaseModel):
    enabled: bool
    release: str
    provider: str
    model: str
    fallback_model: str
    profile_counts: dict[str, int]
    run_counts: dict[str, int]


class AdminHermesMaintenanceStateResponse(BaseModel):
    component: str
    last_started_at: datetime | None = None
    last_succeeded_at: datetime | None = None
    last_error_code: str | None = None
    counters: dict[str, Any] = Field(default_factory=dict)


class AdminHermesRuntimeHealthResponse(BaseModel):
    enabled: bool
    services: dict[str, str]
    active_runs: int
    pending_dispatches: int
    pending_approvals: int
    active_terminal_sessions: int
    quarantined_terminal_workspaces: int
    maintenance: list[AdminHermesMaintenanceStateResponse]


class AdminHermesProfileResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    profile_name: str
    status: str
    provider: str
    model: str
    policy_revision: int
    last_error_code: str | None = None


class AdminHermesProfileListResponse(BaseModel):
    data: list[AdminHermesProfileResponse]


class AdminHermesToolsetResponse(BaseModel):
    name: str
    label: str
    description: str
    enabled: bool
    configured: bool
    tools: list[str] = Field(default_factory=list)


class AdminHermesInventoryResponse(BaseModel):
    profile: AdminHermesProfileResponse
    capabilities: dict[str, Any] = Field(default_factory=dict)
    toolsets: list[AdminHermesToolsetResponse] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)


class AdminHermesSkillToggle(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    enabled: bool


class AdminHermesMcpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    command: str | None = Field(default=None, max_length=1024)
    args: list[str] = Field(default_factory=list, max_length=100)
    env: dict[str, str] = Field(default_factory=dict)
    auth: Literal["none", "oauth", "header"] | None = None
    bearer_token: SecretStr | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def _validate_transport(self) -> "AdminHermesMcpServerCreate":
        if bool(self.url) == bool(self.command):
            raise ValueError("Exactly one of url or command is required.")
        return self


class AdminHermesMcpToggle(BaseModel):
    enabled: bool


class AdminHermesResearchSourceResponse(BaseModel):
    id: ResearchSourceId
    display_name: str
    enabled: bool
    domains: list[str]


class AdminHermesResearchSettingsResponse(BaseModel):
    revision: int
    sources: list[AdminHermesResearchSourceResponse]
    updated_at: str | None = None
    updated_by: str | None = None


class AdminHermesResearchSourceUpdate(BaseModel):
    enabled: bool
    expected_revision: int = Field(ge=0)


def _profile_response(binding: HermesProfileBinding) -> AdminHermesProfileResponse:
    return AdminHermesProfileResponse.model_validate(
        {
            "id": binding.id,
            "workspace_id": binding.workspace_id,
            "user_id": binding.user_id,
            "profile_name": binding.profile_name,
            "status": binding.status,
            "provider": binding.provider,
            "model": binding.model,
            "policy_revision": binding.policy_revision,
            "last_error_code": binding.last_error_code,
        }
    )


def _require_profile(db: Session, binding_id: str) -> HermesProfileBinding:
    binding = db.get(HermesProfileBinding, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.profile_not_found"})
    return binding


def _research_settings_response(
    snapshot: HermesResearchSettingsSnapshot,
) -> AdminHermesResearchSettingsResponse:
    return AdminHermesResearchSettingsResponse(
        revision=snapshot.revision,
        sources=[
            AdminHermesResearchSourceResponse(
                id=source.id,
                display_name=source.display_name,
                enabled=snapshot.policy[source.id],
                domains=list(source.domains),
            )
            for source in RESEARCH_SOURCE_DEFINITIONS
        ],
        updated_at=(
            snapshot.updated_at.isoformat() if snapshot.updated_at is not None else None
        ),
        updated_by=snapshot.updated_by,
    )


def _raise_client_error(error: HermesClientError) -> None:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": error.code, "message": str(error)},
    ) from error


@router.get("", response_model=AdminHermesSummaryResponse)
def get_hermes_summary(
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesSummaryResponse:
    profile_counts = {
        row[0]: int(row[1])
        for row in db.execute(
            select(HermesProfileBinding.status, func.count())
            .group_by(HermesProfileBinding.status)
        )
    }
    run_counts = {
        row[0]: int(row[1])
        for row in db.execute(
            select(HermesRunProjection.status, func.count()).group_by(
                HermesRunProjection.status
            )
        )
    }
    return AdminHermesSummaryResponse(
        enabled=get_settings().hermes_enabled,
        release=HERMES_RELEASE,
        provider=HERMES_PROVIDER,
        model=HERMES_MODEL,
        fallback_model=HERMES_FALLBACK_MODEL,
        profile_counts=profile_counts,
        run_counts=run_counts,
    )


@router.get("/runtime-health", response_model=AdminHermesRuntimeHealthResponse)
async def get_hermes_runtime_health(
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesRuntimeHealthResponse:
    settings = get_settings()
    profile = db.scalar(
        select(HermesProfileBinding)
        .where(HermesProfileBinding.status == "active")
        .order_by(HermesProfileBinding.updated_at.desc())
        .limit(1)
    )
    services = {
        "headless": "disabled" if not settings.hermes_enabled else "not_configured",
        "terminal_broker": "disabled" if not settings.hermes_enabled else "checking",
    }
    if settings.hermes_enabled:
        checks = []
        check_names = []
        if profile is not None:
            checks.append(runtime_client().health(profile.profile_name))
            check_names.append("headless")
        checks.append(HermesTerminalBrokerClient(settings).health())
        check_names.append("terminal_broker")
        results = await asyncio.gather(*checks, return_exceptions=True)
        for check_name, result in zip(check_names, results, strict=True):
            services[check_name] = "offline" if isinstance(result, BaseException) else "online"

    maintenance = list(
        db.scalars(
            select(HermesMaintenanceState).order_by(HermesMaintenanceState.component)
        )
    )
    return AdminHermesRuntimeHealthResponse(
        enabled=settings.hermes_enabled,
        services=services,
        active_runs=int(
            db.scalar(
                select(func.count())
                .select_from(HermesRunProjection)
                .where(HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES))
            )
            or 0
        ),
        pending_dispatches=int(
            db.scalar(
                select(func.count())
                .select_from(HermesDispatchOutbox)
                .where(HermesDispatchOutbox.status.in_({"pending", "claimed"}))
            )
            or 0
        ),
        pending_approvals=int(
            db.scalar(
                select(func.count())
                .select_from(HermesToolApproval)
                .where(HermesToolApproval.status == "pending")
            )
            or 0
        ),
        active_terminal_sessions=int(
            db.scalar(
                select(func.count())
                .select_from(HermesTerminalSession)
                .where(
                    HermesTerminalSession.status.in_(
                        {"starting", "running", "awaiting_approval", "stopping", "archiving"}
                    )
                )
            )
            or 0
        ),
        quarantined_terminal_workspaces=int(
            db.scalar(
                select(func.count())
                .select_from(HermesTerminalSession)
                .where(HermesTerminalSession.workspace_retained.is_(True))
            )
            or 0
        ),
        maintenance=[
            AdminHermesMaintenanceStateResponse.model_validate(state, from_attributes=True)
            for state in maintenance
        ],
    )


@router.get("/profiles", response_model=AdminHermesProfileListResponse)
def list_hermes_profiles(
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesProfileListResponse:
    rows = list(
        db.scalars(
            select(HermesProfileBinding).order_by(
                HermesProfileBinding.updated_at.desc(),
                HermesProfileBinding.id,
            )
        )
    )
    return AdminHermesProfileListResponse(data=[_profile_response(row) for row in rows])


@router.post(
    "/profiles/{binding_id}/reconcile",
    response_model=AdminHermesProfileResponse,
)
async def reconcile_hermes_profile(
    binding_id: str,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesProfileResponse:
    binding = _require_profile(db, binding_id)
    workspace = db.get(Workspace, binding.workspace_id)
    user = db.get(User, binding.user_id)
    if workspace is None or user is None:
        raise HTTPException(status_code=409, detail={"code": "hermes.profile_owner_missing"})
    binding.status = "provisioning"
    db.add(binding)
    db.commit()
    try:
        binding = await ensure_profile_binding(db, workspace=workspace, user=user)
    except HermesClientError as error:
        _raise_client_error(error)
    return _profile_response(binding)


@router.get(
    "/profiles/{binding_id}/inventory",
    response_model=AdminHermesInventoryResponse,
)
async def get_hermes_profile_inventory(
    binding_id: str,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesInventoryResponse:
    binding = _require_profile(db, binding_id)
    try:
        capabilities, toolsets_payload, mcp_payload, skills_payload = await asyncio.gather(
            runtime_client().capabilities(binding.profile_name),
            runtime_client().toolsets(binding.profile_name),
            management_client().list_mcp_servers(binding.profile_name),
            management_client().list_skills(binding.profile_name),
        )
    except HermesClientError as error:
        _raise_client_error(error)
    return AdminHermesInventoryResponse(
        profile=_profile_response(binding),
        capabilities=capabilities,
        toolsets=(
            toolsets_payload.get("data", [])
            if isinstance(toolsets_payload, dict)
            else []
        ),
        mcp_servers=(
            mcp_payload.get("servers", []) if isinstance(mcp_payload, dict) else []
        ),
        skills=(skills_payload.get("skills", []) if isinstance(skills_payload, dict) else []),
    )


@router.get(
    "/research-sources",
    response_model=AdminHermesResearchSettingsResponse,
)
def get_hermes_research_sources(
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesResearchSettingsResponse:
    return _research_settings_response(get_research_settings(db))


@router.put(
    "/research-sources/{source_id}",
    response_model=AdminHermesResearchSettingsResponse,
)
def put_hermes_research_source(
    source_id: ResearchSourceId,
    body: AdminHermesResearchSourceUpdate,
    db: Session = Depends(get_db_session),
    admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesResearchSettingsResponse:
    try:
        snapshot = update_research_source(
            db,
            source_id=source_id,
            enabled=body.enabled,
            expected_revision=body.expected_revision,
            actor_user_id=admin.user.id,
        )
    except HermesResearchSettingsConflictError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes.research_settings_conflict"},
        ) from error
    record_audit_log(
        db,
        actor_user_id=admin.user.id,
        action="admin.hermes.research_source.update",
        entity_kind="hermes_research_source",
        entity_id=source_id,
        summary=f"Updated Hermes research source {source_id}",
        payload={"source_id": source_id, "enabled": body.enabled},
    )
    db.commit()
    invalidate_profile_policy_cache()
    return _research_settings_response(snapshot)


@router.post(
    "/profiles/{binding_id}/model/enforce",
    response_model=AdminHermesProfileResponse,
)
async def enforce_hermes_profile_model(
    binding_id: str,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> AdminHermesProfileResponse:
    binding = _require_profile(db, binding_id)
    try:
        await management_client().set_profile_model(
            binding.profile_name,
            research_sources=get_research_source_policy(db),
        )
    except HermesClientError as error:
        _raise_client_error(error)
    binding.provider = HERMES_PROVIDER
    binding.model = HERMES_MODEL
    binding.policy_revision += 1
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _profile_response(binding)


@router.put("/profiles/{binding_id}/skills")
async def toggle_hermes_skill(
    binding_id: str,
    body: AdminHermesSkillToggle,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> dict[str, Any]:
    binding = _require_profile(db, binding_id)
    try:
        return await management_client().set_skill_enabled(
            binding.profile_name,
            body.name,
            enabled=body.enabled,
        )
    except HermesClientError as error:
        _raise_client_error(error)


@router.post("/profiles/{binding_id}/mcp-servers", status_code=status.HTTP_201_CREATED)
async def add_hermes_mcp_server(
    binding_id: str,
    body: AdminHermesMcpServerCreate,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> dict[str, Any]:
    binding = _require_profile(db, binding_id)
    payload = body.model_dump(exclude_none=True)
    payload["name"] = scoped_mcp_server_name(binding.profile_name, body.name)
    if body.bearer_token is not None:
        payload["bearer_token"] = body.bearer_token.get_secret_value()
    try:
        result = await management_client().add_mcp_server(binding.profile_name, payload)
        await management_client().set_profile_mcp_trust(
            binding.profile_name,
            payload["name"],
        )
        return result
    except HermesClientError as error:
        _raise_client_error(error)


@router.put("/profiles/{binding_id}/mcp-servers/{server_name}")
async def toggle_hermes_mcp_server(
    binding_id: str,
    server_name: str,
    body: AdminHermesMcpToggle,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> dict[str, Any]:
    binding = _require_profile(db, binding_id)
    if (
        server_name == internal_mcp_server_name(binding.profile_name)
        and not body.enabled
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "hermes.internal_mcp_required"},
        )
    if body.enabled and not is_profile_scoped_mcp_server(
        binding.profile_name,
        server_name,
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "hermes.mcp_server_not_profile_scoped"},
        )
    try:
        return await management_client().set_mcp_server_enabled(
            binding.profile_name,
            server_name,
            enabled=body.enabled,
        )
    except HermesClientError as error:
        _raise_client_error(error)


@router.delete("/profiles/{binding_id}/mcp-servers/{server_name}")
async def remove_hermes_mcp_server(
    binding_id: str,
    server_name: str,
    db: Session = Depends(get_db_session),
    _admin: AuthContext = Depends(require_admin_context),
) -> dict[str, Any]:
    binding = _require_profile(db, binding_id)
    if server_name == internal_mcp_server_name(binding.profile_name):
        raise HTTPException(
            status_code=409,
            detail={"code": "hermes.internal_mcp_required"},
        )
    try:
        return await management_client().remove_mcp_server(
            binding.profile_name,
            server_name,
        )
    except HermesClientError as error:
        _raise_client_error(error)
