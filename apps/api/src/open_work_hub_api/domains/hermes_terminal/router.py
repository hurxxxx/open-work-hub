from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
from datetime import timedelta
from pathlib import PurePosixPath
from time import monotonic
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, status
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from open_work_hub_api.core.db import get_db_session, get_session_factory
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.auth.access import (
    load_active_workspace_by_key,
    record_audit_log,
    resolve_workspace_role,
)
from open_work_hub_api.domains.auth.dependencies import (
    resolve_auth_context_from_token,
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.auth.models import User, Workspace, utcnow_naive
from open_work_hub_api.domains.auth.workspace_app_gate import (
    is_app_enabled_for_user_context,
    require_workspace_app_enabled,
    resolve_enabled_app_ids_for_user_context,
)
from open_work_hub_api.domains.hermes.repository import get_or_create_profile_binding
from open_work_hub_api.domains.hermes.research_settings import (
    get_research_source_policy,
)
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
    HermesTerminalBrokerError,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HERMES_TERMINAL_ACTIVE_STATUSES,
    HermesTerminalArtifact,
    HermesTerminalProfileState,
    HermesTerminalSession,
    HermesTerminalToolApproval,
)
from open_work_hub_api.domains.hermes_terminal.lifecycle import (
    fail_missing_terminal_runtime,
    finalize_terminal_session,
    reconcile_terminal_session_if_finished,
)
from open_work_hub_api.domains.hermes_terminal.schemas import (
    HermesTerminalApprovalDecisionRequest,
    HermesTerminalApprovalListResponse,
    HermesTerminalApprovalResponse,
    HermesTerminalConfigResponse,
    HermesTerminalFileEntryResponse,
    HermesTerminalFileListResponse,
    HermesTerminalSessionCreateRequest,
    HermesTerminalSessionListResponse,
    HermesTerminalSessionResponse,
)
from open_work_hub_api.domains.hermes_terminal.security import (
    broker_bearer_token,
    normalize_relative_path,
    terminal_profile_name,
    token_digest,
)
from open_work_hub_api.domains.hermes_terminal.storage import (
    open_object,
    read_object,
)


router = APIRouter(prefix="/hermes-terminal", tags=["hermes-terminal"])
ws_router = APIRouter(prefix="/hermes-terminal", tags=["hermes-terminal"])
_require_app_enabled = require_workspace_app_enabled(
    "hermes-terminal",
    error_code="hermes_terminal.app_disabled",
)
_WS_ACCESS_RECHECK_SECONDS = 60
_WS_ACTIVITY_UPDATE_SECONDS = 15
_TERMINAL_ADMISSION_LOCK = "open-work-hub:hermes-terminal:admission:v1"
_LIVE_WORKSPACE_STATUSES = frozenset({"running", "awaiting_approval"})


def _http_error(code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _broker_error(error: HermesTerminalBrokerError) -> HTTPException:
    if error.status_code == 404:
        status_code = status.HTTP_404_NOT_FOUND
    elif error.status_code in {400, 409}:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return _http_error(error.code, status_code)


def _lock_terminal_admission(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(:identity, CAST(0 AS bigint)))"
        ),
        {"identity": _TERMINAL_ADMISSION_LOCK},
    )


def _owned_session(
    db: Session,
    *,
    session_id: str,
    workspace_id: str,
    user_id: str,
    for_update: bool = False,
) -> HermesTerminalSession:
    statement = select(HermesTerminalSession).where(
        HermesTerminalSession.id == session_id,
        HermesTerminalSession.workspace_id == workspace_id,
        HermesTerminalSession.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise _http_error("hermes_terminal.session_not_found", status.HTTP_404_NOT_FOUND)
    return row


def _session_response(row: HermesTerminalSession) -> HermesTerminalSessionResponse:
    return HermesTerminalSessionResponse(
        id=row.id,
        title=row.title,
        mode=row.mode,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        cols=row.cols,
        rows=row.rows,
        exit_code=row.exit_code,
        failure_code=row.archive_failure_code or row.failure_code,
        artifact_archived_bytes=row.artifact_archived_bytes,
        artifact_omitted_count=row.artifact_omitted_count,
        workspace_retained=row.workspace_retained,
        quarantine_reason=row.quarantine_reason,
        last_activity_at=row.last_activity_at,
        idle_expires_at=row.idle_expires_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _approval_response(row: HermesTerminalToolApproval) -> HermesTerminalApprovalResponse:
    payload = row.request_payload if isinstance(row.request_payload, dict) else {}
    arguments = payload.get("arguments")
    return HermesTerminalApprovalResponse(
        id=row.id,
        request_id=row.request_id,
        tool_name=row.tool_name,
        arguments=arguments if isinstance(arguments, dict) else {},
        status=row.status,  # type: ignore[arg-type]
        choice=row.choice,
        expires_at=row.expires_at,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


def _restore_running_if_no_pending_approval(
    db: Session,
    *,
    session_id: str,
    now,
) -> bool:
    has_pending = db.scalar(
        select(HermesTerminalToolApproval.id)
        .where(
            HermesTerminalToolApproval.session_id == session_id,
            HermesTerminalToolApproval.status == "pending",
            HermesTerminalToolApproval.expires_at > now,
        )
        .limit(1)
    )
    if has_pending is not None:
        return False
    session = db.get(HermesTerminalSession, session_id)
    if session is None or session.status != "awaiting_approval":
        return False
    session.status = "running"
    db.add(session)
    return True


def _load_profile_archive(state: HermesTerminalProfileState | None) -> bytes | None:
    if state is None or not state.object_key:
        return None
    return read_object(state.object_key)


@router.get("/config", response_model=HermesTerminalConfigResponse)
async def get_config(
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_current_user),
    _workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalConfigResponse:
    return HermesTerminalConfigResponse(
        enabled=settings.hermes_enabled,
        idle_timeout_seconds=settings.hermes_terminal_idle_timeout_seconds,
        artifact_retention_days=settings.hermes_terminal_artifact_retention_days,
        max_sessions_per_user=settings.hermes_terminal_max_sessions_per_user,
        max_sessions_per_workspace_user=(
            settings.hermes_terminal_max_sessions_per_workspace_user
        ),
        workspace_live_max_bytes=settings.hermes_terminal_workspace_archive_max_bytes,
    )


@router.get("/sessions", response_model=HermesTerminalSessionListResponse)
async def list_sessions(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionListResponse:
    rows = list(
        db.scalars(
            select(HermesTerminalSession)
            .where(
                HermesTerminalSession.workspace_id == current_workspace.id,
                HermesTerminalSession.user_id == current_user.id,
            )
            .order_by(HermesTerminalSession.created_at.desc())
            .limit(50)
        )
    )
    for row in rows:
        await reconcile_terminal_session_if_finished(row)
    db.expire_all()
    refreshed = list(
        db.scalars(
            select(HermesTerminalSession)
            .where(
                HermesTerminalSession.workspace_id == current_workspace.id,
                HermesTerminalSession.user_id == current_user.id,
            )
            .order_by(HermesTerminalSession.created_at.desc())
            .limit(50)
        )
    )
    return HermesTerminalSessionListResponse(items=[_session_response(row) for row in refreshed])


@router.post(
    "/sessions",
    response_model=HermesTerminalSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: HermesTerminalSessionCreateRequest,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    if not settings.hermes_enabled:
        raise _http_error("hermes_terminal.disabled", status.HTTP_503_SERVICE_UNAVAILABLE)
    _lock_terminal_admission(db)
    active_clause = HermesTerminalSession.status.in_(HERMES_TERMINAL_ACTIVE_STATUSES)
    workspace_user_count = db.scalar(
        select(func.count(HermesTerminalSession.id)).where(
            HermesTerminalSession.workspace_id == current_workspace.id,
            HermesTerminalSession.user_id == current_user.id,
            active_clause,
        )
    )
    user_count = db.scalar(
        select(func.count(HermesTerminalSession.id)).where(
            HermesTerminalSession.user_id == current_user.id,
            active_clause,
        )
    )
    total_count = db.scalar(
        select(func.count(HermesTerminalSession.id)).where(active_clause)
    )
    if int(workspace_user_count or 0) >= settings.hermes_terminal_max_sessions_per_workspace_user:
        raise _http_error("hermes_terminal.workspace_session_limit", status.HTTP_409_CONFLICT)
    if int(user_count or 0) >= settings.hermes_terminal_max_sessions_per_user:
        raise _http_error("hermes_terminal.user_session_limit", status.HTTP_409_CONFLICT)
    if int(total_count or 0) >= settings.hermes_terminal_max_sessions_total:
        raise _http_error("hermes_terminal.global_session_limit", status.HTTP_503_SERVICE_UNAVAILABLE)

    binding = get_or_create_profile_binding(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    profile_state = db.get(HermesTerminalProfileState, binding.id)
    if profile_state is None:
        profile_state = HermesTerminalProfileState(
            profile_binding_id=binding.id,
            profile_name=terminal_profile_name(binding.id),
        )
        db.add(profile_state)
    now = utcnow_naive()
    session_id = str(uuid4())
    mcp_token = secrets.token_urlsafe(48)
    row = HermesTerminalSession(
        id=session_id,
        profile_binding_id=binding.id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        title=f"Hermes Terminal · {now:%Y-%m-%d %H:%M}",
        mode=payload.mode,
        status="starting",
        allowed_app_ids=sorted(
            resolve_enabled_app_ids_for_user_context(
                db,
                user=current_user,
                workspace_id=current_workspace.id,
            )
        ),
        mcp_token_digest=token_digest(mcp_token),
        cols=payload.cols,
        rows=payload.rows,
        last_activity_at=now,
        idle_expires_at=now
        + timedelta(seconds=settings.hermes_terminal_idle_timeout_seconds),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _http_error("hermes_terminal.session_active", status.HTTP_409_CONFLICT) from error
    db.refresh(row)

    try:
        profile_archive = await asyncio.to_thread(_load_profile_archive, profile_state)
        broker_row = await HermesTerminalBrokerClient(settings).create_session(
            session_id=session_id,
            profile_key=profile_state.profile_name,
            mode=payload.mode,
            cols=payload.cols,
            rows=payload.rows,
            mcp_url=f"{settings.hermes_terminal_mcp_relay_url}/{session_id}",
            mcp_token=mcp_token,
            research_sources=get_research_source_policy(db),
            profile_archive=profile_archive,
        )
    except (HermesTerminalBrokerError, S3Error, OSError) as error:
        broker_result_is_ambiguous = (
            isinstance(error, HermesTerminalBrokerError)
            and error.status_code is None
        )
        row.status = "starting" if broker_result_is_ambiguous else "failed"
        row.failure_code = (
            error.code
            if isinstance(error, HermesTerminalBrokerError)
            else "hermes_terminal.profile_restore_failed"
        )
        if not broker_result_is_ambiguous:
            row.ended_at = utcnow_naive()
        db.add(row)
        db.commit()
        if isinstance(error, HermesTerminalBrokerError):
            raise _broker_error(error) from error
        raise _http_error(
            "hermes_terminal.profile_restore_failed",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from error

    row.status = "running"
    row.runtime_handle = broker_row.runtime_handle
    row.broker_instance_id = broker_row.broker_instance_id
    row.started_at = utcnow_naive()
    row.updated_at = row.started_at
    db.add(row)
    record_audit_log(
        db,
        actor_user_id=current_user.id,
        action="hermes_terminal.session.start",
        entity_kind="hermes_terminal_session",
        entity_id=row.id,
        summary="Started private Hermes terminal session",
        payload={
            "mode": row.mode,
            "workspace_id": current_workspace.id,
            "yolo_acknowledged": payload.mode == "yolo" and payload.risk_acknowledged,
        },
    )
    db.commit()
    db.refresh(row)
    return _session_response(row)


@router.get("/sessions/{session_id}", response_model=HermesTerminalSessionResponse)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    await reconcile_terminal_session_if_finished(row)
    db.expire_all()
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    return _session_response(row)


@router.post("/sessions/{session_id}/stop", response_model=HermesTerminalSessionResponse)
async def stop_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        for_update=True,
    )
    if row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
        return _session_response(row)
    if row.status == "archiving":
        return _session_response(row)
    row.status = "stopping"
    db.add(row)
    db.commit()
    try:
        broker_row = await HermesTerminalBrokerClient().stop_session(row.id)
    except HermesTerminalBrokerError as error:
        if error.status_code == 404:
            await fail_missing_terminal_runtime(
                row.id,
                actor_user_id=current_user.id,
            )
            db.expire_all()
            return _session_response(
                _owned_session(
                    db,
                    session_id=session_id,
                    workspace_id=current_workspace.id,
                    user_id=current_user.id,
                )
            )
        row.failure_code = error.code
        row.updated_at = utcnow_naive()
        db.add(row)
        db.commit()
        raise _broker_error(error) from error
    await finalize_terminal_session(
        row.id,
        target_status="terminated",
        exit_code=broker_row.exit_code,
        actor_user_id=current_user.id,
    )
    db.expire_all()
    return _session_response(
        _owned_session(
            db,
            session_id=session_id,
            workspace_id=current_workspace.id,
            user_id=current_user.id,
        )
    )


def _stored_file_list(
    artifacts: list[HermesTerminalArtifact],
    *,
    path: str,
) -> list[HermesTerminalFileEntryResponse]:
    prefix = f"{path}/" if path else ""
    directories: dict[str, HermesTerminalFileEntryResponse] = {}
    files: list[HermesTerminalFileEntryResponse] = []
    for artifact in artifacts:
        if not artifact.relative_path.startswith(prefix):
            continue
        remainder = artifact.relative_path[len(prefix) :]
        if not remainder:
            continue
        head, separator, _tail = remainder.partition("/")
        child_path = f"{prefix}{head}" if prefix else head
        if separator:
            directories.setdefault(
                child_path,
                HermesTerminalFileEntryResponse(
                    relative_path=child_path,
                    name=head,
                    kind="directory",
                ),
            )
        else:
            files.append(
                HermesTerminalFileEntryResponse(
                    relative_path=artifact.relative_path,
                    name=artifact.display_name,
                    kind="file",
                    size_bytes=artifact.size_bytes,
                    modified_at=artifact.created_at,
                    artifact_id=artifact.id,
                )
            )
    return [*sorted(directories.values(), key=lambda item: item.name.lower()), *files]


@router.get("/sessions/{session_id}/files", response_model=HermesTerminalFileListResponse)
async def list_files(
    session_id: str,
    path: Annotated[str, Query(max_length=1024)] = "",
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalFileListResponse:
    try:
        relative_path = normalize_relative_path(path)
    except ValueError as error:
        raise _http_error("hermes_terminal.path_invalid", status.HTTP_400_BAD_REQUEST) from error
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if row.status in _LIVE_WORKSPACE_STATUSES:
        try:
            payload = await HermesTerminalBrokerClient().list_files(row.id, path=relative_path)
        except HermesTerminalBrokerError as error:
            raise _broker_error(error) from error
        return HermesTerminalFileListResponse(
            path=payload.path,
            active=True,
            items=[
                HermesTerminalFileEntryResponse(**item.model_dump())
                for item in payload.items
            ],
        )
    artifacts = list(
        db.scalars(
            select(HermesTerminalArtifact)
            .where(
                HermesTerminalArtifact.session_id == row.id,
                HermesTerminalArtifact.expires_at > utcnow_naive(),
            )
            .order_by(HermesTerminalArtifact.relative_path)
        )
    )
    return HermesTerminalFileListResponse(
        path=relative_path,
        active=False,
        items=_stored_file_list(artifacts, path=relative_path),
    )


@router.get("/sessions/{session_id}/files/download")
async def download_file(
    session_id: str,
    path: Annotated[str, Query(min_length=1, max_length=1024)],
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> Response:
    try:
        relative_path = normalize_relative_path(path, allow_root=False)
    except ValueError as error:
        raise _http_error("hermes_terminal.path_invalid", status.HTTP_400_BAD_REQUEST) from error
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    filename = PurePosixPath(relative_path).name
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    if row.status in _LIVE_WORKSPACE_STATUSES:
        try:
            data = await HermesTerminalBrokerClient().read_file(row.id, path=relative_path)
        except HermesTerminalBrokerError as error:
            raise _broker_error(error) from error
        return Response(
            data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition},
        )
    artifact = db.scalar(
        select(HermesTerminalArtifact).where(
            HermesTerminalArtifact.session_id == row.id,
            HermesTerminalArtifact.relative_path == relative_path,
            HermesTerminalArtifact.expires_at > utcnow_naive(),
        )
    )
    if artifact is None:
        raise _http_error("hermes_terminal.file_not_found", status.HTTP_404_NOT_FOUND)
    return StreamingResponse(
        open_object(artifact.object_key),
        media_type=artifact.media_type,
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/sessions/{session_id}/approvals",
    response_model=HermesTerminalApprovalListResponse,
)
def list_approvals(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalApprovalListResponse:
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    now = utcnow_naive()
    approvals = list(
        db.scalars(
            select(HermesTerminalToolApproval)
            .where(HermesTerminalToolApproval.session_id == row.id)
            .order_by(HermesTerminalToolApproval.created_at.desc())
            .limit(50)
        )
    )
    changed = False
    for approval in approvals:
        if approval.status == "pending" and approval.expires_at <= now:
            approval.status = "expired"
            approval.choice = "timeout"
            approval.decided_at = now
            db.add(approval)
            changed = True
    changed = (
        _restore_running_if_no_pending_approval(
            db,
            session_id=row.id,
            now=now,
        )
        or changed
    )
    if changed:
        db.commit()
    return HermesTerminalApprovalListResponse(
        items=[_approval_response(approval) for approval in approvals]
    )


@router.post(
    "/sessions/{session_id}/approvals/{approval_id}",
    response_model=HermesTerminalApprovalResponse,
)
def decide_approval(
    session_id: str,
    approval_id: str,
    payload: HermesTerminalApprovalDecisionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalApprovalResponse:
    row = _owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    approval = db.scalar(
        select(HermesTerminalToolApproval)
        .where(
            HermesTerminalToolApproval.id == approval_id,
            HermesTerminalToolApproval.session_id == row.id,
        )
        .with_for_update()
    )
    if approval is None:
        raise _http_error("hermes_terminal.approval_not_found", status.HTTP_404_NOT_FOUND)
    now = utcnow_naive()
    if approval.status != "pending" or approval.expires_at <= now:
        if approval.status == "pending":
            approval.status = "expired"
            approval.choice = "timeout"
            approval.decided_at = now
            db.add(approval)
            db.commit()
        raise _http_error("hermes_terminal.approval_closed", status.HTTP_409_CONFLICT)
    approval.status = "approved" if payload.decision == "approve" else "denied"
    approval.choice = "once" if payload.decision == "approve" else "deny"
    approval.decided_by_user_id = current_user.id
    approval.decided_at = now
    db.add(approval)
    _restore_running_if_no_pending_approval(
        db,
        session_id=row.id,
        now=now,
    )
    record_audit_log(
        db,
        actor_user_id=current_user.id,
        action=f"hermes_terminal.approval.{payload.decision}",
        entity_kind="hermes_terminal_tool_approval",
        entity_id=approval.id,
        summary="Resolved Hermes terminal write-tool approval",
        payload={
            "session_id": row.id,
            "tool_name": approval.tool_name,
            "arguments_sha256": approval.arguments_sha256,
            "decision": payload.decision,
        },
    )
    db.commit()
    db.refresh(approval)
    return _approval_response(approval)


async def _resolve_ws_token(websocket: WebSocket) -> str:
    message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
    if len(message.encode("utf-8")) > 16 * 1024:
        raise ValueError("auth frame too large")
    payload = json.loads(message)
    if not isinstance(payload, dict) or payload.get("type") != "auth":
        raise ValueError("invalid auth frame")
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("missing auth token")
    return token


def _authorize_ws(token: str, *, session_id: str, workspace_slug: str) -> str:
    with get_session_factory()() as db:
        context = resolve_auth_context_from_token(db, token)
        workspace = load_active_workspace_by_key(db, workspace_slug)
        if workspace is None or resolve_workspace_role(db, context.user, workspace.id) is None:
            raise _http_error("hermes_terminal.workspace_forbidden", status.HTTP_403_FORBIDDEN)
        if not is_app_enabled_for_user_context(
            db,
            app_id="hermes-terminal",
            user_id=context.user.id,
            workspace_id=workspace.id,
        ):
            raise _http_error("hermes_terminal.app_disabled", status.HTTP_403_FORBIDDEN)
        row = _owned_session(
            db,
            session_id=session_id,
            workspace_id=workspace.id,
            user_id=context.user.id,
        )
        if row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
            raise _http_error("hermes_terminal.session_inactive", status.HTTP_409_CONFLICT)
        return context.user.id


def _touch_session(session_id: str, *, cols: int | None = None, rows: int | None = None) -> None:
    with get_session_factory()() as db:
        row = db.get(HermesTerminalSession, session_id)
        if row is None or row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
            return
        now = utcnow_naive()
        row.last_activity_at = now
        row.idle_expires_at = now + timedelta(
            seconds=get_settings().hermes_terminal_idle_timeout_seconds
        )
        if cols is not None and rows is not None:
            row.cols = cols
            row.rows = rows
        db.add(row)
        db.commit()


@ws_router.websocket("/sessions/{session_id}/ws")
async def terminal_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    workspace_slug = str(websocket.path_params.get("workspace_slug") or "")
    try:
        token = await _resolve_ws_token(websocket)
        owner_id = await asyncio.to_thread(
            _authorize_ws,
            token,
            session_id=session_id,
            workspace_slug=workspace_slug,
        )
    except (HTTPException, TimeoutError, ValueError, WebSocketDisconnect):
        await websocket.close(code=4403)
        return

    settings = get_settings()
    broker = HermesTerminalBrokerClient(settings)
    try:
        async with websocket_connect(
            broker.websocket_url(session_id),
            additional_headers={
                "Authorization": f"Bearer {broker_bearer_token(settings)}"
            },
            proxy=None,
            max_size=2 * 1024 * 1024,
        ) as upstream:
            exit_code: int | None = None
            exit_status: str | None = None
            exit_failure_code: str | None = None
            saw_exit = False
            last_activity_update = 0.0
            last_resize_forwarded = 0.0

            async def broker_to_browser() -> None:
                nonlocal saw_exit, exit_code, exit_failure_code, exit_status, last_activity_update
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                        continue
                    await websocket.send_text(message)
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") == "output":
                        now = monotonic()
                        if now - last_activity_update >= _WS_ACTIVITY_UPDATE_SECONDS:
                            await asyncio.to_thread(_touch_session, session_id)
                            last_activity_update = now
                    elif payload.get("type") == "exit":
                        saw_exit = True
                        value = payload.get("exit_code")
                        exit_code = value if isinstance(value, int) else None
                        value = payload.get("status")
                        exit_status = value if isinstance(value, str) else None
                        value = payload.get("failure_code")
                        exit_failure_code = value if isinstance(value, str) else None
                        return

            async def browser_to_broker() -> None:
                nonlocal last_activity_update, last_resize_forwarded
                while True:
                    message = await websocket.receive_text()
                    if len(message.encode("utf-8")) > 100_000:
                        await websocket.close(code=4400)
                        return
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        await websocket.close(code=4400)
                        return
                    if not isinstance(payload, dict):
                        await websocket.close(code=4400)
                        return
                    message_type = payload.get("type")
                    if message_type == "input":
                        encoded = payload.get("data")
                        if not isinstance(encoded, str) or len(encoded) > 90_000:
                            await websocket.close(code=4400)
                            return
                        try:
                            decoded = base64.b64decode(encoded, validate=True)
                        except (ValueError, binascii.Error):
                            await websocket.close(code=4400)
                            return
                        if len(decoded) > 64 * 1024:
                            await websocket.close(code=4400)
                            return
                    elif message_type == "resize":
                        cols = payload.get("cols")
                        rows = payload.get("rows")
                        if (
                            not isinstance(cols, int)
                            or not isinstance(rows, int)
                            or not 20 <= cols <= 500
                            or not 5 <= rows <= 300
                        ):
                            await websocket.close(code=4400)
                            return
                        now = monotonic()
                        if now - last_resize_forwarded < 0.1:
                            continue
                        last_resize_forwarded = now
                    elif message_type != "ping":
                        await websocket.close(code=4400)
                        return
                    await upstream.send(message)
                    now = monotonic()
                    if now - last_activity_update < _WS_ACTIVITY_UPDATE_SECONDS:
                        continue
                    if message_type not in {"input", "resize"}:
                        continue
                    cols = payload.get("cols") if message_type == "resize" else None
                    rows = payload.get("rows") if message_type == "resize" else None
                    if not isinstance(cols, int) or not isinstance(rows, int):
                        cols = rows = None
                    await asyncio.to_thread(
                        _touch_session,
                        session_id,
                        cols=cols,
                        rows=rows,
                    )
                    last_activity_update = now

            async def monitor_access() -> None:
                while True:
                    await asyncio.sleep(_WS_ACCESS_RECHECK_SECONDS)
                    current_owner = await asyncio.to_thread(
                        _authorize_ws,
                        token,
                        session_id=session_id,
                        workspace_slug=workspace_slug,
                    )
                    if current_owner != owner_id:
                        raise RuntimeError("terminal owner changed")

            tasks = {
                asyncio.create_task(broker_to_browser()),
                asyncio.create_task(browser_to_broker()),
                asyncio.create_task(monitor_access()),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.result()
            if saw_exit:
                target_status = "failed" if exit_status == "failed" else "exited"
                with get_session_factory()() as db:
                    current = db.get(HermesTerminalSession, session_id)
                    if current is not None and current.status == "stopping":
                        target_status = "terminated"
                await finalize_terminal_session(
                    session_id,
                    target_status=target_status,
                    exit_code=exit_code,
                    actor_user_id=owner_id,
                    failure_code=exit_failure_code,
                )
    except ConnectionClosed as error:
        try:
            await websocket.close(code=error.code if 4000 <= error.code <= 4999 else 1013)
        except RuntimeError:
            pass
    except (HTTPException, RuntimeError, WebSocketDisconnect, WebSocketException, OSError):
        try:
            await websocket.close(code=1013)
        except RuntimeError:
            pass
