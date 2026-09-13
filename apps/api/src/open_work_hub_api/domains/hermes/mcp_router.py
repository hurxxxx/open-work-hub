from __future__ import annotations

from itertools import islice

import hashlib
import hmac
import json
import base64
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from jsonschema import Draft202012Validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.core.settings import HERMES_IMAGE, get_settings
from open_work_hub_api.domains.ai.mcp import AiMcpClient
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.hermes.models import (
    HermesProfileBinding,
    HermesRunProjection,
    HermesRunEvent,
    HermesSessionBinding,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.repository import (
    ACTIVE_RUN_STATUSES,
    MAX_RESULT_BYTES,
    HermesRunRepository,
)
from open_work_hub_api.domains.hermes.files import MAX_FILE_BYTES, list_files, read_file, save_file
from open_work_hub_api.domains.hermes.schemas import HermesFileResponse
from open_work_hub_api.domains.hermes.research_settings import get_research_settings
from open_work_hub_api.domains.hermes.research_sources import disabled_research_source_domains
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
    arguments: dict[str, Any],
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
        and payload.get("description")
        == f"Approve this call once. Arguments SHA-256: {_arguments_sha256(arguments)}"
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
                arguments=arguments,
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
    if user is None or user.status != "active" or user.login_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return binding, user


def _available_tools(
    db: Session,
    *,
    binding: HermesProfileBinding,
    user: User,
    apply_run_scope: bool = True,
    hermes_run_id: str | None = None,
):
    if apply_run_scope and not hermes_run_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes.active_run_required"},
        )
    active_run = (
        db.scalar(
            select(HermesRunProjection).where(
                HermesRunProjection.profile_binding_id == binding.id,
                HermesRunProjection.hermes_run_id == hermes_run_id,
                HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES - {"stopping"}),
            )
        )
        if hermes_run_id
        else None
    )
    if apply_run_scope and active_run is None:
        # Only the trusted runtime transport can select a run. Profile-wide
        # discovery is harmless; executing against a guessed latest run is not.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes.active_run_required"},
        )
    if active_run is not None and not can_use_app(
        db,
        user_id=user.id,
        app_id=active_run.owner_app_id,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    principal = user_principal(
        user_id=user.id,
        source="hermes-mcp",
    )
    return (
        principal,
        AiMcpClient().list_tools(
            db,
            principal=principal,
            app_ids=active_run.allowed_app_ids if active_run is not None else None,
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
    hermes_run_id: str | None = Header(default=None, alias="X-Hermes-Run-Id"),
    db: Session = Depends(get_db_session),
) -> Response:
    binding, user = _resolve_mcp_identity(
        db,
        profile_name=profile,
        authorization=authorization,
    )
    try:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_FILE_BYTES * 4 // 3 + 65_536:
                return JSONResponse(
                    _rpc_error(None, -32600, "Request exceeds size limit"), status_code=413
                )
        payload = json.loads(raw)
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

    if method in {
        "owh/context",
        "owh/submit",
        "owh/native_admit",
        "owh/files/list",
        "owh/files/read",
        "owh/files/write",
    }:
        _principal, _tools, run = _available_tools(
            db,
            binding=binding,
            user=user,
            hermes_run_id=hermes_run_id,
        )
        workload = get_ai_capability_registry().get_llm_workload(run.workload_id or "")
        native_tools = sorted(
            set(run.runtime_options.get("native_tools", []))
            & set(workload.native_tools if workload else ())
        )
        if method == "owh/native_admit":
            repository = HermesRunRepository(db)
            run = repository.get(run.id, for_update=True)
            if (
                run.status not in ACTIVE_RUN_STATUSES - {"stopping"}
                or params.get("tool") not in native_tools
            ):
                return JSONResponse(_rpc_error(request_id, -32602, "Tool is not available"))
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(HermesRunEvent)
                    .where(
                        HermesRunEvent.run_id == run.id,
                        HermesRunEvent.event_type == "workload.tool_admitted",
                    )
                )
                or 0
            )
            if count >= min(20, run.runtime_options.get("native_tool_limit", 0)):
                return JSONResponse(_rpc_result(request_id, {"accepted": False}))
            repository.append_event(
                run.id, {"event": "workload.tool_admitted", "tool": params["tool"]}
            )
            db.commit()
            return JSONResponse(_rpc_result(request_id, {"accepted": True}))
        if method == "owh/context":
            namespace = get_settings().hermes_terminal_resource_namespace
            return JSONResponse(
                _rpc_result(
                    request_id,
                    {
                        "allow_native_tools": run.kind == "interactive",
                        "native_tools": native_tools,
                        "output_schema": run.output_schema,
                        "sandbox": {
                            "image": HERMES_IMAGE,
                            "network": f"open-work-hub-{namespace}-hermes-terminal-sandbox",
                            "ca_volume": f"open-work-hub-{namespace}-hermes-terminal-egress-client",
                            "no_proxy": ",".join(
                                [
                                    "localhost",
                                    "127.0.0.1",
                                    "::1",
                                    *disabled_research_source_domains(
                                        get_research_settings(db).policy
                                    ),
                                ]
                            ),
                        },
                    },
                )
            )
        if method.startswith("owh/files/"):
            session = (
                db.get(HermesSessionBinding, run.session_binding_id)
                if run.session_binding_id
                else None
            )
            if session is None or run.kind != "interactive" or session.user_id != user.id:
                return JSONResponse(
                    _rpc_error(request_id, -32602, "Interactive session files required")
                )
            files = list_files(db, session_id=session.id)
            if method == "owh/files/list":
                return JSONResponse(
                    _rpc_result(
                        request_id,
                        {
                            "files": [
                                HermesFileResponse.model_validate(row).model_dump(mode="json")
                                for row in files
                            ],
                        },
                    )
                )
            if method == "owh/files/read":
                row = next((row for row in files if row.id == params.get("id")), None)
                if row is None:
                    return JSONResponse(_rpc_error(request_id, -32602, "File is not available"))
                return JSONResponse(
                    _rpc_result(request_id, {"data": base64.b64encode(read_file(row)).decode()})
                )
            try:
                encoded = params.get("data")
                if not isinstance(encoded, str) or len(encoded) > MAX_FILE_BYTES * 4 // 3 + 4:
                    raise ValueError("Invalid file data")
                row = save_file(
                    db,
                    session=session,
                    path=params["path"],
                    data=base64.b64decode(encoded, validate=True),
                )
            except (ValueError, KeyError, TypeError):
                return JSONResponse(
                    _rpc_error(request_id, -32602, "File path, data or size is invalid")
                )
            return JSONResponse(
                _rpc_result(
                    request_id, HermesFileResponse.model_validate(row).model_dump(mode="json")
                )
            )
        if run.output_schema is None:
            return JSONResponse(
                _rpc_error(request_id, -32602, "No structured result was requested")
            )
        result = params.get("result")
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
            return JSONResponse(
                _rpc_error(request_id, -32602, "Structured result exceeds size limit")
            )
        errors = list(islice(Draft202012Validator(run.output_schema).iter_errors(result), 20))
        if errors:
            # Paths and validator names suffice for correction without echoing
            # supplied values or potentially sensitive source data into logs.
            return JSONResponse(
                _rpc_result(
                    request_id,
                    {
                        "accepted": False,
                        "errors": [
                            {"path": list(error.path), "validator": error.validator}
                            for error in errors
                        ],
                    },
                )
            )
        try:
            get_ai_capability_registry().validate_llm_output(
                run.workload_id or "", result, run.output_schema
            )
        except (ValueError, TypeError, KeyError):
            return JSONResponse(
                _rpc_result(
                    request_id,
                    {
                        "accepted": False,
                        "errors": [{"validator": "workload_contract", "path": []}],
                    },
                )
            )
        run.output_payload = result
        db.add(run)
        db.commit()
        return JSONResponse(_rpc_result(request_id, {"accepted": True}))

    if method == "tools/list":
        _principal, tools, _active_run = _available_tools(
            db,
            binding=binding,
            user=user,
            apply_run_scope=hermes_run_id is not None,
            hermes_run_id=hermes_run_id,
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
        hermes_run_id=hermes_run_id,
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
        result = await run_in_threadpool(
            AiMcpClient().call_tool,
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
