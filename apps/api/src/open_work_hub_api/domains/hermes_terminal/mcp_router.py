from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session, get_session_factory
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.mcp import AiMcpClient
from open_work_hub_api.domains.auth.models import User, Workspace, WorkspaceUserBinding, utcnow_naive
from open_work_hub_api.domains.auth.workspace_app_gate import is_app_enabled_for_user_context
from open_work_hub_api.domains.hermes_terminal.models import (
    HERMES_TERMINAL_ACTIVE_STATUSES,
    HermesTerminalSession,
    HermesTerminalToolApproval,
)
from open_work_hub_api.domains.hermes_terminal.security import token_digest


router = APIRouter(prefix="/mcp", tags=["hermes-terminal-mcp"])


@dataclass(frozen=True)
class TerminalMcpIdentity:
    session: HermesTerminalSession
    workspace: Workspace
    user: User


def _rpc_error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _arguments_sha256(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _normalized_call_id(request_id: Any) -> str:
    if request_id is None:
        return f"call_{uuid4().hex}"
    raw = str(request_id)
    if len(raw) <= 256:
        return raw
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _resolve_identity(
    db: Session,
    *,
    session_id: str,
    authorization: str | None,
) -> TerminalMcpIdentity:
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    session = db.scalar(
        select(HermesTerminalSession).where(HermesTerminalSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not hmac.compare_digest(session.mcp_token_digest, token_digest(supplied)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if session.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes_terminal.session_inactive"},
        )
    workspace = db.get(Workspace, session.workspace_id)
    user = db.get(User, session.user_id)
    membership = db.scalar(
        select(WorkspaceUserBinding.id).where(
            WorkspaceUserBinding.workspace_id == session.workspace_id,
            WorkspaceUserBinding.user_id == session.user_id,
        )
    )
    if (
        workspace is None
        or not workspace.active
        or user is None
        or user.status != "active"
        or user.login_blocked
        or membership is None
        or not is_app_enabled_for_user_context(
            db,
            app_id="hermes-terminal",
            user_id=session.user_id,
            workspace_id=session.workspace_id,
        )
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    now = utcnow_naive()
    session.last_activity_at = now
    session.idle_expires_at = now + timedelta(
        seconds=get_settings().hermes_terminal_idle_timeout_seconds
    )
    db.add(session)
    db.commit()
    return TerminalMcpIdentity(session=session, workspace=workspace, user=user)


def _available_tools(db: Session, identity: TerminalMcpIdentity):
    principal = user_principal(
        workspace_id=identity.workspace.id,
        user_id=identity.user.id,
        source="hermes-terminal-mcp",
    )
    tools = AiMcpClient().list_tools(
        db,
        workspace=identity.workspace,
        principal=principal,
        app_ids=identity.session.allowed_app_ids,
        include_meta=True,
        include_approval_required=True,
    )
    return principal, tools


def _approval_for_call(
    db: Session,
    *,
    identity: TerminalMcpIdentity,
    request_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    workspace_app_id: str,
) -> HermesTerminalToolApproval:
    arguments_digest = _arguments_sha256(arguments)
    approval = db.scalar(
        select(HermesTerminalToolApproval).where(
            HermesTerminalToolApproval.session_id == identity.session.id,
            HermesTerminalToolApproval.request_id == request_id,
        )
    )
    if approval is not None:
        if approval.tool_name != tool_name or approval.arguments_sha256 != arguments_digest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "hermes_terminal.approval_request_conflict"},
            )
        return approval
    now = utcnow_naive()
    approval = HermesTerminalToolApproval(
        id=str(uuid4()),
        session_id=identity.session.id,
        request_id=request_id,
        tool_name=tool_name,
        arguments_sha256=arguments_digest,
        request_payload={
            "tool_name": tool_name,
            "arguments": arguments,
            "workspace_app_id": workspace_app_id,
        },
        status="pending",
        expires_at=now
        + timedelta(seconds=get_settings().hermes_terminal_approval_timeout_seconds),
    )
    identity.session.status = "awaiting_approval"
    db.add(approval)
    db.add(identity.session)
    db.commit()
    return approval


def _restore_running_if_no_pending_approval(
    db: Session,
    *,
    session_id: str,
    now,
) -> None:
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
        return
    session = db.get(HermesTerminalSession, session_id)
    if session is not None and session.status == "awaiting_approval":
        session.status = "running"
        db.add(session)


def _consume_approved_call(approval_id: str) -> tuple[str | None, str]:
    with get_session_factory()() as db:
        approval = db.scalar(
            select(HermesTerminalToolApproval)
            .where(HermesTerminalToolApproval.id == approval_id)
            .with_for_update()
        )
        if approval is None:
            return None, "expired"
        now = utcnow_naive()
        if approval.status == "pending" and approval.expires_at <= now:
            approval.status = "expired"
            approval.choice = "timeout"
            approval.decided_at = now
        if approval.status == "approved" and approval.consumed_at is None:
            external_call_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"hermes-terminal-mcp:{approval.id}:{approval.arguments_sha256}",
                )
            )
            approval.consumed_at = now
            approval.external_call_id = external_call_id
            db.add(approval)
            _restore_running_if_no_pending_approval(
                db,
                session_id=approval.session_id,
                now=now,
            )
            db.commit()
            return external_call_id, "approved"
        if approval.status == "approved" and approval.consumed_at is not None:
            _restore_running_if_no_pending_approval(
                db,
                session_id=approval.session_id,
                now=now,
            )
            db.commit()
            return None, "consumed"
        if approval.status in {"denied", "expired"}:
            db.add(approval)
            _restore_running_if_no_pending_approval(
                db,
                session_id=approval.session_id,
                now=now,
            )
            db.commit()
            return None, approval.status
        db.commit()
        return None, "pending"


async def _await_approval(approval_id: str) -> tuple[str | None, str]:
    deadline = asyncio.get_running_loop().time() + get_settings().hermes_terminal_approval_timeout_seconds
    while True:
        external_call_id, decision = await asyncio.to_thread(
            _consume_approved_call,
            approval_id,
        )
        if decision != "pending":
            return external_call_id, decision
        if asyncio.get_running_loop().time() >= deadline:
            return await asyncio.to_thread(_consume_approved_call, approval_id)
        await asyncio.sleep(0.5)


def _mcp_tool_result(*, request_id: Any, value: Any, is_error: bool) -> JSONResponse:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": encoded}],
        "isError": is_error,
    }
    if not is_error:
        result["structuredContent"] = value
    return JSONResponse(_rpc_result(request_id, result))


@router.get("")
def reject_standalone_sse(
    session: str = Query(min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
) -> Response:
    _resolve_identity(db, session_id=session, authorization=authorization)
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


@router.post("")
async def handle_mcp_request(
    request: Request,
    session: str = Query(min_length=36, max_length=36),
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    db: Session = Depends(get_db_session),
) -> Response:
    identity = _resolve_identity(db, session_id=session, authorization=authorization)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse(_rpc_error(None, -32600, "Invalid Request"), status_code=400)
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

    if method == "notifications/initialized":
        return Response(status_code=status.HTTP_202_ACCEPTED)
    if method == "initialize":
        resolved_session_id = mcp_session_id or f"mcp_{uuid4().hex}"
        return JSONResponse(
            _rpc_result(
                request_id,
                {
                    "protocolVersion": str(params.get("protocolVersion") or "2025-03-26"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "open-work-hub", "version": "1.0"},
                },
            ),
            headers={"Mcp-Session-Id": resolved_session_id},
        )
    if method == "ping":
        return JSONResponse(_rpc_result(request_id, {}))
    principal, tools = _available_tools(db, identity)
    if method == "tools/list":
        return JSONResponse(
            _rpc_result(request_id, {"tools": [dict(item.mcp_tool) for item in tools]})
        )
    if method != "tools/call":
        return JSONResponse(_rpc_error(request_id, -32601, "Method not found"), status_code=404)

    tool_name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        return JSONResponse(
            _rpc_error(request_id, -32602, "Invalid tool call parameters"),
            status_code=400,
        )
    tool = next((item for item in tools if item.descriptor.name == tool_name), None)
    if tool is None:
        return JSONResponse(
            _rpc_error(request_id, -32602, "Tool is not available in this workspace"),
            status_code=404,
        )

    external_approval_id = None
    call_id = _normalized_call_id(request_id)
    if tool.descriptor.approval_policy == "required":
        approval = _approval_for_call(
            db,
            identity=identity,
            request_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
            workspace_app_id=tool.descriptor.workspace_app_id,
        )
        external_approval_id, decision = await _await_approval(approval.id)
        if external_approval_id is None:
            return _mcp_tool_result(
                request_id=request_id,
                value={
                    "code": f"hermes_terminal.approval_{decision}",
                    "message": "The Open Work Hub write request was not approved.",
                },
                is_error=True,
            )

        # Approval can remain open for several minutes. Re-resolve the
        # session identity and tool surface after consuming the exact
        # one-time evidence so revoked membership/app access cannot race the
        # approval window.
        db.expire_all()
        try:
            identity = _resolve_identity(
                db,
                session_id=session,
                authorization=authorization,
            )
            principal, tools = _available_tools(db, identity)
        except HTTPException as error:
            detail = (
                error.detail
                if isinstance(error.detail, dict)
                else {"message": str(error.detail)}
            )
            return _mcp_tool_result(
                request_id=request_id,
                value={
                    "code": "hermes_terminal.authorization_changed",
                    **detail,
                },
                is_error=True,
            )
        tool = next((item for item in tools if item.descriptor.name == tool_name), None)
        if tool is None:
            return _mcp_tool_result(
                request_id=request_id,
                value={"code": "hermes_terminal.tool_access_changed"},
                is_error=True,
            )

    db.expire_all()
    workspace = db.get(Workspace, identity.workspace.id)
    user = db.get(User, identity.user.id)
    if workspace is None or user is None:
        return _mcp_tool_result(
            request_id=request_id,
            value={"code": "hermes_terminal.identity_unavailable"},
            is_error=True,
        )
    try:
        result = AiMcpClient().call_tool(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source="hermes-terminal-mcp",
            call_id=call_id,
            agent_run_id=identity.session.id,
            conversation_id=None,
            externally_approved_call_id=external_approval_id,
        )
        db.commit()
    except HTTPException as error:
        db.rollback()
        detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
        return _mcp_tool_result(request_id=request_id, value=detail, is_error=True)
    except Exception:
        db.rollback()
        return _mcp_tool_result(
            request_id=request_id,
            value={"code": "hermes_terminal.tool_execution_failed"},
            is_error=True,
        )
    return _mcp_tool_result(request_id=request_id, value=result, is_error=False)
