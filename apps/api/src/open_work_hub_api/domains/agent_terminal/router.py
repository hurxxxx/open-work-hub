from __future__ import annotations

import asyncio
import base64
import binascii
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from open_work_hub_api.core.db import get_db_session, get_session_factory
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.agent_terminal.codex_history import (
    AgentTerminalCodexHistoryError,
    list_codex_threads,
    require_codex_thread,
)
from open_work_hub_api.domains.agent_terminal.git_changes import (
    AgentTerminalGitError,
    get_git_commit_detail,
    get_git_commit_diff,
    get_git_diff,
    get_git_history,
    get_git_status,
    get_git_summary,
)
from open_work_hub_api.domains.agent_terminal.models import (
    AgentTerminalSession,
    utcnow_naive,
)
from open_work_hub_api.domains.agent_terminal.runtime import (
    AgentTerminalRuntime,
    AgentTerminalRuntimeError,
)
from open_work_hub_api.domains.agent_terminal.schemas import (
    AgentTerminalCodexThreadListResponse,
    AgentTerminalCodexThreadResponse,
    AgentTerminalConfigResponse,
    AgentTerminalGitChangeScope,
    AgentTerminalGitCommitDetailResponse,
    AgentTerminalGitCommitDiffResponse,
    AgentTerminalGitDiffResponse,
    AgentTerminalGitHistoryResponse,
    AgentTerminalGitStatusResponse,
    AgentTerminalGitSummaryResponse,
    AgentTerminalRootResponse,
    AgentTerminalSessionCreateRequest,
    AgentTerminalSessionListResponse,
    AgentTerminalSessionResponse,
)
from open_work_hub_api.domains.agent_terminal.service import (
    AgentTerminalConfigurationError,
    configured_roots,
    resolve_codex_binary,
    resolve_root,
    resolve_tmux_binary,
    serialize_session,
)
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
    require_app_access,
)
from open_work_hub_api.domains.auth.dependencies import (
    AuthContext,
    require_any_system_role,
    resolve_auth_context_from_token,
)
from open_work_hub_api.domains.auth.security import new_id

router = APIRouter(prefix="/agent-terminal", tags=["agent-terminal"])
ws_router = APIRouter(prefix="/agent-terminal", tags=["agent-terminal"])
_require_platform_admin = require_any_system_role("platform_admin")
_require_app_enabled = require_app_access("agent-terminal")
_ACTIVE_STATUSES = frozenset({"starting", "running"})
_ACCESS_RECHECK_SECONDS = 60


def _runtime_from_app(app: Any) -> AgentTerminalRuntime:
    runtime = getattr(app.state, "agent_terminal_runtime", None)
    if not isinstance(runtime, AgentTerminalRuntime):
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_terminal.runtime_unavailable",
        )
    return runtime


def _configuration_exception(exc: AgentTerminalConfigurationError) -> HTTPException:
    return localized_http_exception(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=exc.code,
    )


def _runtime_exception(exc: AgentTerminalRuntimeError) -> HTTPException:
    status_code = (
        status.HTTP_409_CONFLICT
        if exc.code
        in {
            "agent_terminal.session_active",
            "agent_terminal.session_closed",
            "agent_terminal.session_limit",
            "agent_terminal.session_not_local",
        }
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return localized_http_exception(status_code=status_code, code=exc.code)


def _git_exception(exc: AgentTerminalGitError) -> HTTPException:
    if exc.code in {
        "agent_terminal.git_change_not_found",
        "agent_terminal.git_commit_not_found",
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "agent_terminal.git_history_query_invalid",
        "agent_terminal.git_path_invalid",
    }:
        status_code = status.HTTP_400_BAD_REQUEST
    elif exc.code == "agent_terminal.git_repository_unavailable":
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return localized_http_exception(status_code=status_code, code=exc.code)


def _codex_history_exception(exc: AgentTerminalCodexHistoryError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if exc.code == "agent_terminal.codex_thread_not_found"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return localized_http_exception(status_code=status_code, code=exc.code)


def _owned_session(
    db: Session,
    *,
    session_id: str,
    owner_id: str,
) -> AgentTerminalSession:
    row = db.scalar(
        select(AgentTerminalSession).where(
            AgentTerminalSession.id == session_id,
            AgentTerminalSession.owner_id == owner_id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="agent_terminal.session_not_found",
        )
    return row


@router.get("/config", response_model=AgentTerminalConfigResponse)
def get_agent_terminal_config(
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalConfigResponse:
    try:
        roots = configured_roots(settings)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    return AgentTerminalConfigResponse(
        enabled=settings.agent_terminal_enabled,
        codex_available=resolve_codex_binary(settings) is not None,
        tmux_available=resolve_tmux_binary(settings) is not None,
        roots=[
            AgentTerminalRootResponse(
                key=root.key,
                label=root.label,
                path=str(root.path),
            )
            for root in roots
        ],
        max_sessions_per_user=settings.agent_terminal_max_sessions_per_user,
    )


@router.get("/sessions", response_model=AgentTerminalSessionListResponse)
def list_agent_terminal_sessions(
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalSessionListResponse:
    rows = db.scalars(
        select(AgentTerminalSession)
        .where(AgentTerminalSession.owner_id == context.user.id)
        .order_by(AgentTerminalSession.created_at.desc())
        .limit(50)
    ).all()
    return AgentTerminalSessionListResponse(items=[serialize_session(row) for row in rows])


@router.get(
    "/codex/threads",
    response_model=AgentTerminalCodexThreadListResponse,
)
async def list_agent_terminal_codex_threads(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalCodexThreadListResponse:
    codex_binary = resolve_codex_binary(settings)
    if codex_binary is None:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_terminal.codex_unavailable",
        )
    try:
        roots = configured_roots(settings)
        threads = await list_codex_threads(
            codex_binary=codex_binary,
            roots=roots,
            limit=limit,
        )
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalCodexHistoryError as exc:
        raise _codex_history_exception(exc) from exc
    return AgentTerminalCodexThreadListResponse(
        items=[
            AgentTerminalCodexThreadResponse(
                id=thread.id,
                name=thread.name,
                preview=thread.preview,
                root_key=thread.root_key,
                root_path=thread.root_path,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
            )
            for thread in threads
        ]
    )


@router.get(
    "/roots/{root_key}/git/status",
    response_model=AgentTerminalGitStatusResponse,
)
def get_agent_terminal_git_status(
    root_key: str,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitStatusResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_status(root.path)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.get(
    "/roots/{root_key}/git/diff",
    response_model=AgentTerminalGitDiffResponse,
)
def get_agent_terminal_git_diff(
    root_key: str,
    path: Annotated[str, Query(min_length=1, max_length=4_096)],
    scope: AgentTerminalGitChangeScope,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitDiffResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_diff(root.path, path=path, scope=scope)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.get(
    "/roots/{root_key}/git/summary",
    response_model=AgentTerminalGitSummaryResponse,
)
def get_agent_terminal_git_summary(
    root_key: str,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitSummaryResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_summary(root.path)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.get(
    "/roots/{root_key}/git/history",
    response_model=AgentTerminalGitHistoryResponse,
)
def get_agent_terminal_git_history(
    root_key: str,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitHistoryResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_history(root.path, offset=offset, limit=limit)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.get(
    "/roots/{root_key}/git/commits/{commit}",
    response_model=AgentTerminalGitCommitDetailResponse,
)
def get_agent_terminal_git_commit(
    root_key: str,
    commit: str,
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitCommitDetailResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_commit_detail(root.path, commit=commit)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.get(
    "/roots/{root_key}/git/commits/{commit}/diff",
    response_model=AgentTerminalGitCommitDiffResponse,
)
def get_agent_terminal_git_commit_diff(
    root_key: str,
    commit: str,
    path: Annotated[str, Query(min_length=1, max_length=4_096)],
    settings: Settings = Depends(get_settings),
    _context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalGitCommitDiffResponse:
    try:
        root = resolve_root(settings, root_key)
        return get_git_commit_diff(root.path, commit=commit, path=path)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc
    except AgentTerminalGitError as exc:
        raise _git_exception(exc) from exc


@router.post(
    "/sessions",
    response_model=AgentTerminalSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_terminal_session(
    payload: AgentTerminalSessionCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(_require_platform_admin),
    settings: Settings = Depends(get_settings),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalSessionResponse:
    if not settings.agent_terminal_enabled:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_terminal.disabled",
        )
    try:
        root = resolve_root(settings, payload.root_key)
    except AgentTerminalConfigurationError as exc:
        raise _configuration_exception(exc) from exc

    if payload.codex_thread_id is not None:
        codex_binary = resolve_codex_binary(settings)
        if codex_binary is None:
            raise localized_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="agent_terminal.codex_unavailable",
            )
        try:
            await require_codex_thread(
                codex_binary=codex_binary,
                root=root,
                thread_id=payload.codex_thread_id,
            )
        except AgentTerminalCodexHistoryError as exc:
            raise _codex_history_exception(exc) from exc

    runtime = _runtime_from_app(request.app)
    now = utcnow_naive()
    row = AgentTerminalSession(
        id=new_id(),
        owner_id=context.user.id,
        tool="codex",
        root_key=root.key,
        root_path=str(root.path),
        status="starting",
        runtime_instance_id=runtime.instance_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()

    try:
        await runtime.start(
            session_id=row.id,
            owner_id=context.user.id,
            root_path=root.path,
            cols=payload.cols,
            rows=payload.rows,
            codex_thread_id=payload.codex_thread_id,
        )
    except (AgentTerminalRuntimeError, OSError) as exc:
        db.refresh(row)
        row.status = "failed"
        row.failure_code = (
            exc.code
            if isinstance(exc, AgentTerminalRuntimeError)
            else "agent_terminal.start_failed"
        )
        row.ended_at = utcnow_naive()
        row.updated_at = row.ended_at
        record_audit_log(
            db,
            actor_user_id=context.user.id,
            action="agent_terminal.session.start_failed",
            entity_kind="agent_terminal_session",
            entity_id=row.id,
            summary="Failed to start Codex terminal session",
            payload={"root_key": root.key, "failure_code": row.failure_code},
        )
        db.commit()
        if isinstance(exc, AgentTerminalRuntimeError):
            raise _runtime_exception(exc) from exc
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_terminal.start_failed",
        ) from exc

    db.refresh(row)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="agent_terminal.session.start",
        entity_kind="agent_terminal_session",
        entity_id=row.id,
        summary="Started Codex terminal session",
        payload={
            "root_key": root.key,
            "tool": "codex",
            "resumed": payload.codex_thread_id is not None,
        },
    )
    db.commit()
    return serialize_session(row)


@router.post(
    "/sessions/{session_id}/stop",
    response_model=AgentTerminalSessionResponse,
)
async def stop_agent_terminal_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> AgentTerminalSessionResponse:
    row = _owned_session(db, session_id=session_id, owner_id=context.user.id)
    if row.status not in _ACTIVE_STATUSES:
        return serialize_session(row)
    runtime = _runtime_from_app(request.app)
    try:
        await runtime.terminate(row.id)
    except AgentTerminalRuntimeError as exc:
        raise _runtime_exception(exc) from exc
    db.refresh(row)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="agent_terminal.session.stop",
        entity_kind="agent_terminal_session",
        entity_id=row.id,
        summary="Stopped Codex terminal session",
        payload={"root_key": row.root_key},
    )
    db.commit()
    return serialize_session(row)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_agent_terminal_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    context: AuthContext = Depends(_require_platform_admin),
    _app_enabled: None = Depends(_require_app_enabled),
) -> Response:
    row = _owned_session(db, session_id=session_id, owner_id=context.user.id)
    if row.status in _ACTIVE_STATUSES:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="agent_terminal.session_active",
        )

    runtime = _runtime_from_app(request.app)
    try:
        runtime.forget(row.id)
    except AgentTerminalRuntimeError as exc:
        raise _runtime_exception(exc) from exc

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="agent_terminal.session.delete",
        entity_kind="agent_terminal_session",
        entity_id=row.id,
        summary="Deleted Codex terminal session metadata",
        payload={
            "root_key": row.root_key,
            "status": row.status,
            "tool": row.tool,
        },
    )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@ws_router.websocket("/sessions/{session_id}/ws")
async def agent_terminal_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        token = await _resolve_ws_token(websocket)
        owner_id, session_status = await run_in_threadpool(
            _authorize_websocket,
            token,
            session_id,
        )
    except HTTPException as exc:
        await websocket.close(code=_websocket_close_code(exc.status_code))
        return
    except (TimeoutError, ValueError, WebSocketDisconnect):
        await websocket.close(code=4401)
        return

    try:
        runtime = _runtime_from_app(websocket.app)
        queue, replay, active = runtime.subscribe(session_id)
    except HTTPException:
        await websocket.close(code=1013)
        return
    except AgentTerminalRuntimeError as exc:
        if (
            exc.code == "agent_terminal.session_not_local"
            and session_status not in _ACTIVE_STATUSES
        ):
            await websocket.send_json({"type": "ready", "active": False})
            await websocket.send_json({"type": "exit"})
            return
        await websocket.close(code=4409)
        return

    try:
        await websocket.send_json({"type": "ready", "active": active})
        if replay:
            await _send_output(websocket, replay, frame_type="replay")
        if not active:
            await websocket.send_json({"type": "exit"})
            return
        sender_task = asyncio.create_task(_send_terminal_output(websocket, queue))
        receiver_task = asyncio.create_task(_receive_terminal_input(websocket, runtime, session_id))
        monitor_task = asyncio.create_task(
            _monitor_websocket_access(websocket, token, session_id, owner_id)
        )
        done, pending = await asyncio.wait(
            {sender_task, receiver_task, monitor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            try:
                task.result()
            except (AgentTerminalRuntimeError, RuntimeError, WebSocketDisconnect):
                pass
    except asyncio.CancelledError:
        # ASGI runtimes may cancel connection tasks during normal WebSocket
        # teardown. The endpoint owns no durable process because tmux does.
        return
    finally:
        runtime.unsubscribe(session_id, queue)


async def _resolve_ws_token(websocket: WebSocket) -> str:
    message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
    parsed = json.loads(message)
    if not isinstance(parsed, dict) or parsed.get("type") != "auth":
        raise ValueError("invalid auth frame")
    token = parsed.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("missing auth token")
    return token


def _authorize_websocket(token: str, session_id: str) -> tuple[str, str]:
    with get_session_factory()() as db:
        context = resolve_auth_context_from_token(db, token)
        if "platform_admin" not in context.system_roles:
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="auth.system_role_required",
                roles="platform_admin",
            )
        if not can_use_app(db, user_id=context.user.id, app_id="agent-terminal"):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="platform.app_disabled",
            )
        row = _owned_session(db, session_id=session_id, owner_id=context.user.id)
        return context.user.id, row.status


async def _monitor_websocket_access(
    websocket: WebSocket,
    token: str,
    session_id: str,
    owner_id: str,
) -> None:
    while True:
        await asyncio.sleep(_ACCESS_RECHECK_SECONDS)
        try:
            current_owner_id, _session_status = await run_in_threadpool(
                _authorize_websocket,
                token,
                session_id,
            )
        except HTTPException:
            await websocket.close(code=4403)
            return
        if current_owner_id != owner_id:
            await websocket.close(code=4403)
            return


async def _send_terminal_output(
    websocket: WebSocket,
    queue: asyncio.Queue[bytes | None],
) -> None:
    while True:
        data = await queue.get()
        if data is None:
            await websocket.send_json({"type": "exit"})
            return
        await _send_output(websocket, data)


async def _send_output(
    websocket: WebSocket,
    data: bytes,
    *,
    frame_type: Literal["output", "replay"] = "output",
) -> None:
    await websocket.send_json(
        {
            "type": frame_type,
            "data": base64.b64encode(data).decode("ascii"),
        }
    )


async def _receive_terminal_input(
    websocket: WebSocket,
    runtime: AgentTerminalRuntime,
    session_id: str,
) -> None:
    while True:
        raw_payload = await websocket.receive_text()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "code": "agent_terminal.message_invalid"})
            continue
        if not isinstance(payload, dict):
            continue
        message_type = payload.get("type")
        try:
            if message_type == "input":
                encoded = payload.get("data")
                if not isinstance(encoded, str) or len(encoded) > 90_000:
                    raise AgentTerminalRuntimeError("agent_terminal.input_too_large")
                data = base64.b64decode(encoded, validate=True)
                await runtime.write(session_id, data)
            elif message_type == "resize":
                cols = payload.get("cols")
                rows = payload.get("rows")
                if not isinstance(cols, int) or not isinstance(rows, int):
                    raise AgentTerminalRuntimeError("agent_terminal.size_invalid")
                await runtime.resize(session_id, cols=cols, rows=rows)
            elif message_type == "scroll":
                lines = payload.get("lines")
                if isinstance(lines, bool) or not isinstance(lines, int):
                    raise AgentTerminalRuntimeError("agent_terminal.message_invalid")
                await runtime.scroll(session_id, lines=lines)
            elif message_type == "scroll_end":
                await runtime.end_scroll(session_id)
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "code": "agent_terminal.message_invalid"}
                )
        except (AgentTerminalRuntimeError, binascii.Error) as exc:
            code = (
                exc.code
                if isinstance(exc, AgentTerminalRuntimeError)
                else "agent_terminal.message_invalid"
            )
            await websocket.send_json({"type": "error", "code": code})


def _websocket_close_code(status_code: int) -> int:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return 4401
    if status_code == status.HTTP_404_NOT_FOUND:
        return 4404
    return 4403
