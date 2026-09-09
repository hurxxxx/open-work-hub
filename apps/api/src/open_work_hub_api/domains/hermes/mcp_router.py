from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.mcp import AiMcpClient
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.hermes.models import (
    HermesProfileBinding,
    HermesRunProjection,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.repository import ACTIVE_RUN_STATUSES
from open_work_hub_api.domains.hermes.service import (
    internal_mcp_server_name,
    mcp_profile_bearer_secret,
)

router = APIRouter(prefix="/internal/hermes/mcp", tags=["hermes-mcp"])
_APPROVAL_EVIDENCE_MAX_AGE = timedelta(minutes=5)


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


def _approval_matches_mcp_tool(
    approval: HermesToolApproval,
    *,
    profile_name: str,
    tool_name: str,
) -> bool:
    payload = approval.request_payload
    if not isinstance(payload, dict):
        return False
    command = payload.get("command")
    pattern_key = payload.get("pattern_key")
    pattern_keys = payload.get("pattern_keys")
    expected_prefix = (
        f"MCP tool '{tool_name}' on UNTRUSTED server "
        f"'{internal_mcp_server_name(profile_name)}' wants to run."
    )
    return (
        isinstance(command, str)
        and command.startswith(expected_prefix)
        and pattern_key == "mcp_elicitation"
        and isinstance(pattern_keys, list)
        and "mcp_elicitation" in pattern_keys
    )


def _consume_external_tool_approval(
    db: Session,
    *,
    run_id: str,
    profile_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    now = utcnow_naive()
    approvals = list(
        db.scalars(
            select(HermesToolApproval)
            .where(
                HermesToolApproval.run_id == run_id,
                HermesToolApproval.status == "approved",
                HermesToolApproval.choice == "once",
                HermesToolApproval.decided_by_user_id.is_not(None),
                HermesToolApproval.decided_at.is_not(None),
                HermesToolApproval.decided_at >= now - _APPROVAL_EVIDENCE_MAX_AGE,
                HermesToolApproval.consumed_at.is_(None),
            )
            .order_by(
                HermesToolApproval.decided_at.desc(),
                HermesToolApproval.created_at.desc(),
            )
            .with_for_update()
        )
    )
    approval = next(
        (
            candidate
            for candidate in approvals
            if candidate.consumed_at is None
            and _approval_matches_mcp_tool(
                candidate,
                profile_name=profile_name,
                tool_name=tool_name,
            )
        ),
        None,
    )
    if approval is None:
        return None

    arguments_digest = _arguments_sha256(arguments)
    external_call_id = str(
        uuid5(
            NAMESPACE_URL,
            f"hermes-mcp:{approval.id}:{tool_name}:{arguments_digest}",
        )
    )
    approval.consumed_at = now
    approval.consumed_tool_name = tool_name
    approval.consumed_arguments_sha256 = arguments_digest
    approval.external_call_id = external_call_id
    db.add(approval)
    # Commit the one-time evidence before the tool starts. A failed tool call
    # must not make the same human approval replayable.
    db.commit()
    return external_call_id


def _resolve_mcp_identity(
    db: Session,
    *,
    profile_name: str,
    authorization: str | None,
) -> tuple[HermesProfileBinding, User]:
    settings = get_settings()
    expected = mcp_profile_bearer_secret(settings, profile_name)
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    binding = db.scalar(
        select(HermesProfileBinding).where(
            HermesProfileBinding.profile_name == profile_name,
            HermesProfileBinding.status == "active",
        )
    )
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    user = db.get(User, binding.user_id)
    if (
        user is None
        or user.status != "active"
        or user.login_blocked
        or not can_use_app(db, user_id=binding.user_id, app_id="chatbot")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return binding, user


def _available_tools(
    db: Session,
    *,
    binding: HermesProfileBinding,
    user: User,
    apply_run_scope: bool = True,
):
    active_run = db.scalar(
        select(HermesRunProjection)
        .where(
            HermesRunProjection.profile_binding_id == binding.id,
            HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(HermesRunProjection.created_at.desc())
    )
    if active_run is None:
        # The profile credential identifies an owner, but only a staged run
        # carries the caller-selected app scope. Never interpret a missing
        # run as an unrestricted tool request.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes.active_run_required"},
        )
    principal = user_principal(
        user_id=user.id,
        source="hermes-mcp",
    )
    return (
        principal,
        AiMcpClient().list_tools(
            db,
            principal=principal,
            app_ids=active_run.allowed_app_ids if apply_run_scope else None,
            include_meta=True,
            include_approval_required=True,
        ),
        active_run,
    )


@router.get("")
def reject_standalone_sse(
    profile: str = Query(min_length=1, max_length=63),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db_session),
) -> Response:
    _resolve_mcp_identity(db, profile_name=profile, authorization=authorization)
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


@router.post("")
async def handle_mcp_request(
    request: Request,
    profile: str = Query(min_length=1, max_length=63),
    authorization: str | None = Header(default=None),
    mcp_session_id: str | None = Header(default=None, alias="Mcp-Session-Id"),
    db: Session = Depends(get_db_session),
) -> Response:
    binding, user = _resolve_mcp_identity(
        db,
        profile_name=profile,
        authorization=authorization,
    )
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
        session_id = mcp_session_id or f"mcp_{uuid4().hex}"
        return JSONResponse(
            _rpc_result(
                request_id,
                {
                    "protocolVersion": str(params.get("protocolVersion") or "2025-03-26"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "open-work-hub", "version": "1.0"},
                },
            ),
            headers={"Mcp-Session-Id": session_id},
        )
    if method == "ping":
        return JSONResponse(_rpc_result(request_id, {}))

    if method == "tools/list":
        _principal, tools, _active_run = _available_tools(
            db,
            binding=binding,
            user=user,
            apply_run_scope=False,
        )
        return JSONResponse(
            _rpc_result(
                request_id,
                {"tools": [dict(item.mcp_tool) for item in tools]},
            )
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
    principal, tools, active_run = _available_tools(
        db,
        binding=binding,
        user=user,
        apply_run_scope=True,
    )
    tool = next((item for item in tools if item.descriptor.name == tool_name), None)
    if tool is None:
        return JSONResponse(
            _rpc_error(request_id, -32602, "Tool is not available for this user"),
            status_code=404,
        )

    external_approval_id = None
    if tool.descriptor.approval_policy == "required":
        external_approval_id = _consume_external_tool_approval(
            db,
            run_id=active_run.id,
            profile_name=profile,
            tool_name=tool_name,
            arguments=arguments,
        )
        if external_approval_id is None:
            return JSONResponse(
                _rpc_result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "code": "hermes.approval_evidence_required",
                                        "message": (
                                            "This write-capable tool needs a matching "
                                            "one-time approval from Open Work Hub."
                                        ),
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        ],
                        "isError": True,
                    },
                )
            )
    try:
        result = AiMcpClient().call_tool(
            db,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source="hermes-mcp",
            call_id=str(request_id) if request_id is not None else None,
            agent_run_id=active_run.id,
            conversation_id=active_run.session_binding_id,
            externally_approved_call_id=external_approval_id,
        )
        db.commit()
    except HTTPException as error:
        db.rollback()
        detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
        return JSONResponse(
            _rpc_result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(detail, ensure_ascii=False, default=str),
                        }
                    ],
                    "isError": True,
                },
            )
        )
    except Exception:
        db.rollback()
        return JSONResponse(
            _rpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": "Tool execution failed."}],
                    "isError": True,
                },
            )
        )
    encoded = json.dumps(result, ensure_ascii=False, default=str)
    return JSONResponse(
        _rpc_result(
            request_id,
            {
                "content": [{"type": "text", "text": encoded}],
                "structuredContent": result,
                "isError": False,
            },
        )
    )
