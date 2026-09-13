from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session, get_session_factory
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
    require_app_access,
)
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    resolve_auth_context_from_token,
)
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
    HermesTerminalBrokerError,
)
from open_work_hub_api.domains.hermes_terminal.lifecycle import (
    fail_missing_terminal_runtime,
    finalize_terminal_session,
    reconcile_terminal_session_if_finished,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HERMES_TERMINAL_ACTIVE_STATUSES,
    HermesTerminalArtifact,
    HermesTerminalProfileState,
    HermesTerminalSession,
    HermesTerminalToolApproval,
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
    normalize_relative_path,
)
from open_work_hub_api.domains.hermes_terminal.storage import (
    open_object,
    read_object,
)

router = APIRouter(prefix="/hermes-terminal", tags=["hermes-terminal"])
ws_router = APIRouter(prefix="/hermes-terminal", tags=["hermes-terminal"])
_require_app_enabled = require_app_access(
    "chatbot",
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
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, CAST(0 AS bigint)))"),
        {"identity": _TERMINAL_ADMISSION_LOCK},
    )


def _owned_session(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    for_update: bool = False,
) -> HermesTerminalSession:
    statement = select(HermesTerminalSession).where(
        HermesTerminalSession.id == session_id,
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalConfigResponse:
    return HermesTerminalConfigResponse(
        enabled=settings.hermes_enabled,
        idle_timeout_seconds=settings.hermes_terminal_idle_timeout_seconds,
        artifact_retention_days=settings.hermes_terminal_artifact_retention_days,
        max_sessions_per_user=settings.hermes_terminal_max_sessions_per_user,
        workspace_live_max_bytes=settings.hermes_terminal_workspace_archive_max_bytes,
    )


@router.get("/sessions", response_model=HermesTerminalSessionListResponse)
async def list_sessions(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionListResponse:
    rows = list(
        db.scalars(
            select(HermesTerminalSession)
            .where(
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    raise _http_error("hermes_terminal.retired", status.HTTP_410_GONE)


@router.get("/sessions/{session_id}", response_model=HermesTerminalSessionResponse)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    row = _owned_session(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )
    await reconcile_terminal_session_if_finished(row)
    db.expire_all()
    row = _owned_session(
        db,
        session_id=session_id,
        user_id=current_user.id,
    )
    return _session_response(row)


@router.post("/sessions/{session_id}/stop", response_model=HermesTerminalSessionResponse)
async def stop_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalSessionResponse:
    row = _owned_session(
        db,
        session_id=session_id,
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalFileListResponse:
    try:
        relative_path = normalize_relative_path(path)
    except ValueError as error:
        raise _http_error("hermes_terminal.path_invalid", status.HTTP_400_BAD_REQUEST) from error
    row = _owned_session(
        db,
        session_id=session_id,
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
            items=[HermesTerminalFileEntryResponse(**item.model_dump()) for item in payload.items],
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> Response:
    try:
        relative_path = normalize_relative_path(path, allow_root=False)
    except ValueError as error:
        raise _http_error("hermes_terminal.path_invalid", status.HTTP_400_BAD_REQUEST) from error
    row = _owned_session(
        db,
        session_id=session_id,
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalApprovalListResponse:
    row = _owned_session(
        db,
        session_id=session_id,
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
    _app_enabled: None = Depends(_require_app_enabled),
) -> HermesTerminalApprovalResponse:
    row = _owned_session(
        db,
        session_id=session_id,
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


def _authorize_ws(
    token: str,
    *,
    session_id: str,
) -> str:
    with get_session_factory()() as db:
        context = resolve_auth_context_from_token(db, token)
        if not can_use_app(
            db,
            app_id="hermes-terminal",
            user_id=context.user.id,
        ):
            raise _http_error("hermes_terminal.app_disabled", status.HTTP_403_FORBIDDEN)
        row = _owned_session(
            db,
            session_id=session_id,
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
    await websocket.close(code=4403)
