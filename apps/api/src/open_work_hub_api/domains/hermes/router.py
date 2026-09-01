from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session, get_session_factory
from open_work_hub_api.core.settings import (
    HERMES_MODEL,
    HERMES_PROVIDER,
    HERMES_RELEASE,
)
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import (
    HermesJobBinding,
    HermesProfileBinding,
    HermesRunProjection,
    HermesSessionBinding,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.publication import publish_pending_hermes_dispatches
from open_work_hub_api.domains.hermes.repository import (
    TERMINAL_RUN_STATUSES,
    HermesRunBusyError,
    HermesRunRepository,
    get_owned_session,
    register_session,
    utcnow_naive,
)
from open_work_hub_api.domains.hermes.schemas import (
    HermesAgentStatusResponse,
    HermesApprovalDecision,
    HermesJobCreate,
    HermesJobListResponse,
    HermesJobResponse,
    HermesRunCreate,
    HermesRunListResponse,
    HermesRunResponse,
    HermesSessionCreate,
    HermesSessionListResponse,
    HermesSessionMessagesResponse,
    HermesSessionResponse,
    HermesSessionUpdate,
    HermesSteerRequest,
)
from open_work_hub_api.domains.hermes.service import (
    HermesIntegrationDisabledError,
    ensure_job_profile,
    ensure_profile_binding,
    runtime_client,
)
from open_work_hub_api.domains.hermes.research_settings import get_research_settings


router = APIRouter(prefix="/agent", tags=["hermes-agent"])


def _raise_integration_error(error: Exception) -> NoReturn:
    if isinstance(error, HermesIntegrationDisabledError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "hermes.disabled"},
        ) from error
    if isinstance(error, HermesClientError):
        status_code = error.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
        if status_code >= 500:
            status_code = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=status_code,
            detail={"code": error.code, "message": str(error)},
        ) from error
    raise error


def _session_row(payload: dict) -> dict:
    value = payload.get("session")
    return value if isinstance(value, dict) else payload


def _session_response(binding: HermesSessionBinding, payload: dict) -> HermesSessionResponse:
    row = _session_row(payload)
    return HermesSessionResponse(
        id=binding.id,
        title=row.get("title") or binding.title,
        source=row.get("source"),
        model=row.get("model"),
        message_count=int(row.get("message_count") or 0),
        started_at=row.get("started_at"),
        last_active=row.get("last_active"),
        preview=row.get("preview"),
        parent_session_id=row.get("parent_session_id"),
        pinned=bool(row.get("pinned")),
        archived=bool(row.get("archived")),
        scope_ref=binding.scope_ref,
        scope_resource_id=binding.scope_resource_id,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _job_id(row: dict) -> str:
    return str(row.get("id") or row.get("job_id") or "")


def _job_response(binding: HermesJobBinding, row: dict) -> HermesJobResponse:
    enabled = row.get("enabled")
    status_value = row.get("status")
    resolved_status = str(status_value or ("active" if enabled is not False else "paused"))
    return HermesJobResponse(
        id=binding.id,
        name=str(row.get("name") or binding.name),
        status=resolved_status,
        schedule=row.get("schedule"),
        prompt=row.get("prompt"),
        next_run=row.get("next_run") or row.get("next_run_at"),
        raw=row,
    )


async def _profile_for_request(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
):
    try:
        return await ensure_profile_binding(db, workspace=workspace, user=user)
    except (HermesIntegrationDisabledError, HermesClientError) as error:
        _raise_integration_error(error)


async def _job_profile_for_request(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> tuple[HermesProfileBinding, str]:
    binding = await _profile_for_request(db, workspace=workspace, user=user)
    try:
        research_settings = get_research_settings(db)
        return binding, await ensure_job_profile(
            binding,
            research_sources=research_settings.policy,
            research_policy_revision=research_settings.revision,
        )
    except (HermesIntegrationDisabledError, HermesClientError) as error:
        _raise_integration_error(error)


@router.get("/status", response_model=HermesAgentStatusResponse)
async def get_agent_status(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesAgentStatusResponse:
    binding = await _profile_for_request(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    client = runtime_client()
    try:
        runtime_payload, capability_payload = await asyncio.gather(
            client.health(binding.profile_name),
            client.capabilities(binding.profile_name),
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    return HermesAgentStatusResponse(
        enabled=True,
        release=HERMES_RELEASE,
        provider=HERMES_PROVIDER,
        model=HERMES_MODEL,
        profile_status=binding.status,
        runtime=runtime_payload,
        capabilities=capability_payload,
    )


@router.get("/sessions", response_model=HermesSessionListResponse)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scope_ref: str | None = Query(default=None, max_length=160),
    scope_resource_id: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesSessionListResponse:
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().list_sessions(
            profile.profile_name,
            limit=limit,
            offset=offset,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    response_rows: list[HermesSessionResponse] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        session = register_session(
            db,
            binding=profile,
            hermes_session_id=row["id"],
            title=row.get("title"),
        )
        if scope_ref is not None and session.scope_ref != scope_ref:
            continue
        if scope_resource_id is not None and session.scope_resource_id != scope_resource_id:
            continue
        response_rows.append(_session_response(session, row))
    db.commit()
    return HermesSessionListResponse(
        data=response_rows,
        limit=limit,
        offset=offset,
        has_more=bool(payload.get("has_more")),
    )


@router.post(
    "/sessions",
    response_model=HermesSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    body: HermesSessionCreate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesSessionResponse:
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    hermes_session_id = f"owh_{uuid4().hex}"
    try:
        payload = await runtime_client().create_session(
            profile.profile_name,
            session_id=hermes_session_id,
            title=body.title,
            system_prompt=body.system_prompt,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    row = _session_row(payload)
    session = register_session(
        db,
        binding=profile,
        hermes_session_id=str(row.get("id") or hermes_session_id),
        title=row.get("title") or body.title,
        scope_ref=body.scope_ref,
        scope_resource_id=body.scope_resource_id,
    )
    db.commit()
    db.refresh(session)
    return _session_response(session, row)


@router.get("/sessions/{session_id}", response_model=HermesSessionResponse)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesSessionResponse:
    session = get_owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().get_session(
            profile.profile_name,
            session.hermes_session_id,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    return _session_response(session, payload)


@router.patch("/sessions/{session_id}", response_model=HermesSessionResponse)
async def update_session(
    session_id: str,
    body: HermesSessionUpdate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesSessionResponse:
    session = get_owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    changes = body.model_dump(exclude_none=True)
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().update_session(
            profile.profile_name,
            session.hermes_session_id,
            changes,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    if "title" in changes:
        session.title = changes["title"]
    session.status = "archived" if changes.get("archived") else "active"
    session.updated_at = utcnow_naive()
    db.add(session)
    db.commit()
    return _session_response(session, payload)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    session = get_owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        await runtime_client().delete_session(profile.profile_name, session.hermes_session_id)
    except HermesClientError as error:
        _raise_integration_error(error)
    session.status = "deleted"
    session.updated_at = utcnow_naive()
    db.add(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=HermesSessionMessagesResponse,
)
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesSessionMessagesResponse:
    session = get_owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().session_messages(
            profile.profile_name,
            session.hermes_session_id,
            limit=limit,
            offset=offset,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    return HermesSessionMessagesResponse(
        session_id=session.id,
        data=[row for row in rows if isinstance(row, dict)],
        pagination=payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {},
    )


@router.post(
    "/sessions/{session_id}/runs",
    response_model=HermesRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    session_id: str,
    body: HermesRunCreate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunResponse:
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    session = get_owned_session(
        db,
        session_id=session_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    try:
        run = HermesRunRepository(db).stage(
            binding=profile,
            session=session,
            input_text=body.input,
            instructions=body.instructions,
            conversation_history=body.conversation_history,
            allowed_app_ids=body.allowed_app_ids,
        )
    except HermesRunBusyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "hermes.profile_run_active"},
        ) from error
    db.commit()
    db.refresh(run)
    publish_pending_hermes_dispatches(db, limit=1)
    db.refresh(run)
    return HermesRunResponse.model_validate(run)


@router.get("/runs", response_model=HermesRunListResponse)
def list_runs(
    run_status: str | None = Query(default=None, alias="status", max_length=32),
    session_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunListResponse:
    predicates = [
        HermesRunProjection.workspace_id == current_workspace.id,
        HermesRunProjection.user_id == current_user.id,
    ]
    if run_status:
        predicates.append(HermesRunProjection.status == run_status)
    if session_id:
        owned_session = get_owned_session(
            db,
            session_id=session_id,
            workspace_id=current_workspace.id,
            user_id=current_user.id,
        )
        if owned_session is None:
            raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
        predicates.append(HermesRunProjection.session_binding_id == owned_session.id)
    total = int(
        db.scalar(select(func.count()).select_from(HermesRunProjection).where(*predicates)) or 0
    )
    rows = list(
        db.scalars(
            select(HermesRunProjection)
            .where(*predicates)
            .order_by(HermesRunProjection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return HermesRunListResponse(
        data=[HermesRunResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=HermesRunResponse)
def get_run(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunResponse:
    run = HermesRunRepository(db).get_owned(
        run_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    return HermesRunResponse.model_validate(run)


async def _event_stream(
    *,
    run_id: str,
    workspace_id: str,
    user_id: str,
    after_sequence: int,
) -> AsyncIterator[str]:
    next_sequence = after_sequence
    idle_ticks = 0
    while True:
        with get_session_factory()() as db:
            repository = HermesRunRepository(db)
            run = repository.get_owned(
                run_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if run is None:
                yield 'event: error\ndata: {"code":"hermes.run_not_found"}\n\n'
                return
            events = repository.list_events_after(run_id, after_sequence=next_sequence)
            terminal = run.status in TERMINAL_RUN_STATUSES
        if events:
            idle_ticks = 0
            for event in events:
                next_sequence = event.sequence
                payload = json.dumps(event.payload, ensure_ascii=False, default=str)
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
        else:
            idle_ticks += 1
            if idle_ticks >= 60:
                idle_ticks = 0
                yield ": keepalive\n\n"
        if terminal and not events:
            yield "event: stream.closed\ndata: {}\n\n"
            return
        await asyncio.sleep(0.5)


@router.get("/runs/{run_id}/events")
def stream_run_events(
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> StreamingResponse:
    run = HermesRunRepository(db).get_owned(
        run_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    try:
        after_sequence = max(0, int(last_event_id or 0))
    except ValueError:
        after_sequence = 0
    return StreamingResponse(
        _event_stream(
            run_id=run.id,
            workspace_id=current_workspace.id,
            user_id=current_user.id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/stop", response_model=HermesRunResponse)
async def stop_run(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunResponse:
    repository = HermesRunRepository(db)
    run = repository.get_owned(
        run_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        for_update=True,
    )
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    if run.status in TERMINAL_RUN_STATUSES:
        return HermesRunResponse.model_validate(run)
    if not run.hermes_run_id:
        now = utcnow_naive()
        execution_active = bool(
            run.execution_claim_token
            and (run.execution_claim_expires_at is None or run.execution_claim_expires_at > now)
        )
        repository.append_event(
            run.id,
            {
                "event": "run.stop_requested" if execution_active else "run.cancelled",
                "status": "stopping" if execution_active else "cancelled",
                "reason": "stopped_during_dispatch"
                if execution_active
                else "stopped_before_dispatch",
            },
        )
        db.commit()
        db.refresh(run)
        return HermesRunResponse.model_validate(run)
    hermes_run_id = run.hermes_run_id
    db.commit()
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().stop_run(profile.profile_name, hermes_run_id)
    except HermesClientError as error:
        _raise_integration_error(error)
    repository.append_event(
        run.id,
        {"event": "run.stop_requested", "status": "stopping", **payload},
    )
    db.commit()
    db.refresh(run)
    return HermesRunResponse.model_validate(run)


@router.post("/runs/{run_id}/steer", response_model=HermesRunResponse)
async def steer_run(
    run_id: str,
    body: HermesSteerRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunResponse:
    repository = HermesRunRepository(db)
    run = repository.get_owned(
        run_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if run is None or not run.hermes_run_id:
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    try:
        payload = await runtime_client().steer_run(
            profile.profile_name,
            run.hermes_run_id,
            body.input,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    repository.append_event(run.id, {"event": "run.steered", **payload})
    db.commit()
    db.refresh(run)
    return HermesRunResponse.model_validate(run)


@router.post("/runs/{run_id}/approval", response_model=HermesRunResponse)
async def resolve_approval(
    run_id: str,
    body: HermesApprovalDecision,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesRunResponse:
    repository = HermesRunRepository(db)
    run = repository.get_owned(
        run_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    if run is None or not run.hermes_run_id:
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    profile = await _profile_for_request(db, workspace=current_workspace, user=current_user)
    approval = db.scalar(
        select(HermesToolApproval)
        .where(
            HermesToolApproval.run_id == run.id,
            HermesToolApproval.request_id == body.request_id,
            HermesToolApproval.status == "pending",
        )
        .with_for_update()
    )
    if approval is None:
        raise HTTPException(status_code=409, detail={"code": "hermes.approval_not_pending"})
    local_run_id = run.id
    hermes_run_id = run.hermes_run_id
    profile_name = profile.profile_name
    decision_user_id = current_user.id
    approval_id = approval.id
    staged_approval = body.choice == "once"
    if staged_approval:
        # Publish the local evidence before waking Hermes. The resumed agent
        # can issue its MCP call immediately, before the runtime request has
        # returned to this process.
        approval.status = "approved"
        approval.choice = body.choice
        approval.decided_by_user_id = decision_user_id
        approval.decided_at = utcnow_naive()
        db.add(approval)
        db.commit()
    try:
        payload = await runtime_client().resolve_approval(
            profile_name,
            hermes_run_id,
            request_id=body.request_id,
            choice=body.choice,
        )
    except (HermesIntegrationDisabledError, HermesClientError) as error:
        db.rollback()
        if staged_approval:
            staged = db.scalar(
                select(HermesToolApproval)
                .where(
                    HermesToolApproval.id == approval_id,
                    HermesToolApproval.status == "approved",
                )
                .with_for_update()
            )
            if staged is not None and staged.consumed_at is None:
                staged.status = "pending"
                staged.choice = None
                staged.decided_by_user_id = None
                staged.decided_at = None
                db.add(staged)
                db.commit()
        _raise_integration_error(error)
    if not staged_approval:
        approval.status = "denied"
        approval.choice = body.choice
        approval.decided_by_user_id = decision_user_id
        approval.decided_at = utcnow_naive()
        db.add(approval)
    repository.append_event(local_run_id, {"event": "approval.responded", **payload})
    db.commit()
    resolved_run = repository.get(local_run_id)
    if resolved_run is None:  # pragma: no cover - protected by the run FK
        raise HTTPException(status_code=404, detail={"code": "hermes.run_not_found"})
    return HermesRunResponse.model_validate(resolved_run)


@router.get("/jobs", response_model=HermesJobListResponse)
async def list_jobs(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesJobListResponse:
    profile, automation_profile = await _job_profile_for_request(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    try:
        payload = await runtime_client().list_jobs(automation_profile)
    except HermesClientError as error:
        _raise_integration_error(error)
    rows = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    result: list[HermesJobResponse] = []
    for row in rows:
        if not isinstance(row, dict) or not _job_id(row):
            continue
        binding = db.scalar(
            select(HermesJobBinding).where(
                HermesJobBinding.profile_binding_id == profile.id,
                HermesJobBinding.hermes_job_id == _job_id(row),
            )
        )
        if binding is None:
            binding = HermesJobBinding(
                id=str(uuid4()),
                profile_binding_id=profile.id,
                workspace_id=current_workspace.id,
                user_id=current_user.id,
                hermes_job_id=_job_id(row),
                name=str(row.get("name") or "Scheduled agent job"),
                status="active" if row.get("enabled") is not False else "paused",
            )
            db.add(binding)
            db.flush()
        result.append(_job_response(binding, row))
    db.commit()
    return HermesJobListResponse(data=result)


@router.post("/jobs", response_model=HermesJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: HermesJobCreate,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesJobResponse:
    profile, automation_profile = await _job_profile_for_request(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    job_payload = {
        "name": body.name,
        "schedule": body.schedule,
        "prompt": body.prompt,
        "deliver": "local",
        "skills": body.skills,
    }
    if body.repeat is not None:
        job_payload["repeat"] = body.repeat
    try:
        payload = await runtime_client().create_job(automation_profile, job_payload)
    except HermesClientError as error:
        _raise_integration_error(error)
    row = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    hermes_job_id = _job_id(row)
    if not hermes_job_id:
        raise HTTPException(status_code=502, detail={"code": "hermes.invalid_job_response"})
    binding = HermesJobBinding(
        id=str(uuid4()),
        profile_binding_id=profile.id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        hermes_job_id=hermes_job_id,
        name=body.name,
        status="active",
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _job_response(binding, row)


def _owned_job(
    db: Session,
    *,
    job_id: str,
    workspace_id: str,
    user_id: str,
) -> HermesJobBinding:
    binding = db.scalar(
        select(HermesJobBinding).where(
            HermesJobBinding.id == job_id,
            HermesJobBinding.workspace_id == workspace_id,
            HermesJobBinding.user_id == user_id,
            HermesJobBinding.status != "deleted",
        )
    )
    if binding is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.job_not_found"})
    return binding


@router.post("/jobs/{job_id}/{action}", response_model=HermesJobResponse)
async def run_job_action(
    job_id: str,
    action: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> HermesJobResponse:
    if action not in {"pause", "resume", "run"}:
        raise HTTPException(status_code=404, detail={"code": "hermes.job_action_not_found"})
    binding = _owned_job(
        db,
        job_id=job_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    _profile, automation_profile = await _job_profile_for_request(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    try:
        payload = await runtime_client().job_action(
            automation_profile,
            binding.hermes_job_id,
            action,
        )
    except HermesClientError as error:
        _raise_integration_error(error)
    row = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    if action == "pause":
        binding.status = "paused"
    elif action == "resume":
        binding.status = "active"
    binding.updated_at = utcnow_naive()
    db.add(binding)
    db.commit()
    return _job_response(binding, row)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    binding = _owned_job(
        db,
        job_id=job_id,
        workspace_id=current_workspace.id,
        user_id=current_user.id,
    )
    _profile, automation_profile = await _job_profile_for_request(
        db,
        workspace=current_workspace,
        user=current_user,
    )
    try:
        await runtime_client().delete_job(automation_profile, binding.hermes_job_id)
    except HermesClientError as error:
        _raise_integration_error(error)
    binding.status = "deleted"
    binding.updated_at = utcnow_naive()
    db.add(binding)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
