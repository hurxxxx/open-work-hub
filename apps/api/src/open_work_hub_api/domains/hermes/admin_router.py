from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.settings import (
    HERMES_MODEL,
    HERMES_PROVIDER,
    HERMES_RELEASE,
    get_settings,
)
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_admin_context
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import (
    HermesProfileBinding,
    HermesRunProjection,
)
from open_work_hub_api.domains.hermes.service import (
    ensure_profile_binding,
    internal_mcp_server_name,
    is_profile_scoped_mcp_server,
    management_client,
    runtime_client,
    scoped_mcp_server_name,
)


router = APIRouter(prefix="/admin/hermes", tags=["admin-hermes"])


class AdminHermesSummaryResponse(BaseModel):
    enabled: bool
    release: str
    provider: str
    model: str
    profile_counts: dict[str, int]
    run_counts: dict[str, int]


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


class AdminHermesInventoryResponse(BaseModel):
    profile: AdminHermesProfileResponse
    capabilities: dict[str, Any] = Field(default_factory=dict)
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
        profile_counts=profile_counts,
        run_counts=run_counts,
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
        capabilities, mcp_payload, skills_payload = await asyncio.gather(
            runtime_client().capabilities(binding.profile_name),
            management_client().list_mcp_servers(binding.profile_name),
            management_client().list_skills(binding.profile_name),
        )
    except HermesClientError as error:
        _raise_client_error(error)
    return AdminHermesInventoryResponse(
        profile=_profile_response(binding),
        capabilities=capabilities,
        mcp_servers=(
            mcp_payload.get("servers", []) if isinstance(mcp_payload, dict) else []
        ),
        skills=(skills_payload.get("skills", []) if isinstance(skills_payload, dict) else []),
    )


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
        await management_client().set_profile_model(binding.profile_name)
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
