from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import HERMES_MODEL, HERMES_PROVIDER, get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.hermes.models import (
    HermesDispatchOutbox,
    HermesProfileBinding,
    HermesRunEvent,
    HermesRunInput,
    HermesRunProjection,
    HermesSessionBinding,
    HermesToolApproval,
)


TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "invalid_output"}
)
ACTIVE_RUN_STATUSES = frozenset(
    {"pending", "dispatching", "queued", "running", "awaiting_approval", "stopping"}
)


class HermesRunNotFoundError(LookupError):
    pass


class HermesSessionNotFoundError(LookupError):
    pass


class HermesRunBusyError(RuntimeError):
    pass


class HermesRunIdempotencyConflict(RuntimeError):
    pass


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def deterministic_profile_name(workspace_id: str, user_id: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{workspace_id}:{user_id}".encode()).hexdigest()[:32]
    return f"owh-{digest}"


def _redact_event_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            if any(
                marker in normalized
                for marker in ("authorization", "api_key", "password", "secret", "cookie", "token")
            ):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_event_value(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_redact_event_value(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, str):
        return value[:32_768]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1000]


def sanitize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _redact_event_value(payload)
    if not isinstance(sanitized, dict):
        return {"value": sanitized}
    encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
    if len(encoded.encode()) <= 65_536:
        return sanitized
    return {
        "event": str(payload.get("event") or "hermes.event")[:160],
        "run_id": str(payload.get("run_id") or "")[:80],
        "truncated": True,
    }


def get_or_create_profile_binding(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> HermesProfileBinding:
    # Serialize the first binding creation for a workspace. Without this lock,
    # simultaneous status/session requests can both miss the unique row and
    # race into a constraint violation.
    db.execute(
        select(Workspace.id).where(Workspace.id == workspace.id).with_for_update()
    ).scalar_one()
    binding = db.scalar(
        select(HermesProfileBinding).where(
            HermesProfileBinding.workspace_id == workspace.id,
            HermesProfileBinding.user_id == user.id,
        )
    )
    if binding is not None:
        return binding
    binding = HermesProfileBinding(
        id=str(uuid4()),
        workspace_id=workspace.id,
        user_id=user.id,
        profile_name=deterministic_profile_name(workspace.id, user.id),
        status="provisioning",
        provider=HERMES_PROVIDER,
        model=HERMES_MODEL,
    )
    db.add(binding)
    db.flush()
    return binding


def get_owned_session(
    db: Session,
    *,
    session_id: str,
    workspace_id: str,
    user_id: str,
) -> HermesSessionBinding | None:
    return db.scalar(
        select(HermesSessionBinding).where(
            HermesSessionBinding.id == session_id,
            HermesSessionBinding.workspace_id == workspace_id,
            HermesSessionBinding.user_id == user_id,
            HermesSessionBinding.status != "deleted",
        )
    )


def register_session(
    db: Session,
    *,
    binding: HermesProfileBinding,
    hermes_session_id: str,
    title: str | None,
    scope_ref: str | None = None,
    scope_resource_id: str | None = None,
    local_id: str | None = None,
) -> HermesSessionBinding:
    existing = db.scalar(
        select(HermesSessionBinding).where(
            HermesSessionBinding.profile_binding_id == binding.id,
            HermesSessionBinding.hermes_session_id == hermes_session_id,
        )
    )
    if existing is not None:
        existing.title = title or existing.title
        existing.scope_ref = scope_ref or existing.scope_ref
        existing.scope_resource_id = scope_resource_id or existing.scope_resource_id
        existing.status = "active"
        existing.updated_at = utcnow_naive()
        db.add(existing)
        db.flush()
        return existing
    session = HermesSessionBinding(
        id=local_id or str(uuid4()),
        profile_binding_id=binding.id,
        workspace_id=binding.workspace_id,
        user_id=binding.user_id,
        hermes_session_id=hermes_session_id,
        title=title,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        status="active",
    )
    db.add(session)
    db.flush()
    return session


@dataclass(frozen=True)
class HermesExecutionClaim:
    acquired: bool
    status: str
    reason: str | None = None


class HermesRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stage(
        self,
        *,
        binding: HermesProfileBinding,
        session: HermesSessionBinding | None,
        input_text: str,
        instructions: str | None,
        conversation_history: list[dict[str, Any]],
        allowed_app_ids: list[str] | None = None,
        kind: str = "interactive",
        workload_id: str | None = None,
        client_request_id: str | None = None,
        request_sha256: str | None = None,
    ) -> HermesRunProjection:
        # Serialize run admission per Hermes profile so the MCP tool scope can
        # always be resolved to exactly one active Open Work Hub run.
        self.db.execute(
            select(HermesProfileBinding.id)
            .where(HermesProfileBinding.id == binding.id)
            .with_for_update()
        ).scalar_one()
        if client_request_id is not None:
            existing = self.db.scalar(
                select(HermesRunProjection).where(
                    HermesRunProjection.profile_binding_id == binding.id,
                    HermesRunProjection.client_request_id == client_request_id,
                )
            )
            if existing is not None:
                if existing.request_sha256 == request_sha256:
                    return existing
                raise HermesRunIdempotencyConflict(client_request_id)
        active = self.db.scalar(
            select(HermesRunProjection.id).where(
                HermesRunProjection.profile_binding_id == binding.id,
                HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        if active is not None:
            raise HermesRunBusyError(binding.id)
        run_id = str(uuid4())
        run = HermesRunProjection(
            id=run_id,
            profile_binding_id=binding.id,
            session_binding_id=session.id if session is not None else None,
            workspace_id=binding.workspace_id,
            user_id=binding.user_id,
            kind=kind,
            workload_id=workload_id,
            client_request_id=client_request_id,
            request_sha256=request_sha256,
            status="pending",
            stage="dispatch.pending",
            current_activity="Waiting for an agent worker.",
            allowed_app_ids=allowed_app_ids,
        )
        self.db.add(run)
        # The child rows below reference the new run. There are deliberately no
        # ORM relationships between these projection/outbox models, so flush
        # the parent explicitly before SQLAlchemy schedules their INSERTs.
        # This remains inside the same transaction and preserves atomic staging.
        self.db.flush([run])
        self.db.add(
            HermesRunInput(
                run_id=run_id,
                input_text=input_text,
                instructions=instructions,
                conversation_history=conversation_history,
            )
        )
        self.db.add(
            HermesDispatchOutbox(
                id=str(uuid4()),
                run_id=run_id,
                status="pending",
            )
        )
        self.db.add(
            HermesRunEvent(
                id=str(uuid4()),
                run_id=run_id,
                sequence=1,
                event_type="run.created",
                payload={"event": "run.created", "run_id": run_id, "status": "pending"},
            )
        )
        self.db.flush()
        return run

    def get(self, run_id: str, *, for_update: bool = False) -> HermesRunProjection | None:
        query = select(HermesRunProjection).where(HermesRunProjection.id == run_id)
        if for_update:
            query = query.with_for_update()
        return self.db.scalar(query)

    def get_owned(
        self,
        run_id: str,
        *,
        workspace_id: str,
        user_id: str,
        for_update: bool = False,
    ) -> HermesRunProjection | None:
        query = select(HermesRunProjection).where(
            HermesRunProjection.id == run_id,
            HermesRunProjection.workspace_id == workspace_id,
            HermesRunProjection.user_id == user_id,
        )
        if for_update:
            query = query.with_for_update()
        return self.db.scalar(query)

    def claim_execution(
        self,
        run_id: str,
        *,
        claim_token: str,
        lease_seconds: int,
    ) -> HermesExecutionClaim:
        now = utcnow_naive()
        run = self.get(run_id, for_update=True)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return HermesExecutionClaim(False, run.status, "terminal")
        if (
            run.execution_claim_token
            and run.execution_claim_token != claim_token
            and run.execution_claim_expires_at is not None
            and run.execution_claim_expires_at > now
        ):
            return HermesExecutionClaim(False, run.status, "active_lease")
        if run.status == "stopping" and run.hermes_run_id is None:
            # A stop arrived while a prior dispatch lease was active, but the
            # lease has now expired without producing a Hermes run. Complete
            # the cancellation locally instead of dispatching a new run.
            self.append_event(
                run_id,
                {
                    "event": "run.cancelled",
                    "status": "cancelled",
                    "reason": "stopped_before_dispatch",
                },
            )
            return HermesExecutionClaim(False, "cancelled", "terminal")
        run.execution_claim_token = claim_token
        run.execution_claimed_at = now
        run.execution_claim_expires_at = now + timedelta(seconds=lease_seconds)
        run.execution_attempts += 1
        if run.status != "stopping":
            run.status = "dispatching" if run.hermes_run_id is None else "running"
            run.stage = "dispatch.submitting" if run.hermes_run_id is None else "run.recovering"
            run.current_activity = "Connecting to Hermes."
        run.started_at = run.started_at or now
        run.updated_at = now
        self.db.add(run)
        self.db.flush()
        return HermesExecutionClaim(True, run.status)

    def attach_hermes_run(
        self,
        run_id: str,
        *,
        claim_token: str,
        hermes_run_id: str,
        status: str = "queued",
    ) -> HermesRunProjection:
        run = self.get(run_id, for_update=True)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        self._assert_claim(run, claim_token)
        stop_requested = run.status == "stopping"
        run.hermes_run_id = hermes_run_id
        run.status = "stopping" if stop_requested else self._normalize_status(status)
        run.stage = "run.stopping" if stop_requested else "run.queued"
        run.current_activity = "Stopping Hermes." if stop_requested else "Hermes accepted the run."
        run.updated_at = utcnow_naive()
        self.db.add(run)
        self.db.flush()
        return run

    def append_event(
        self,
        run_id: str,
        payload: dict[str, Any],
        *,
        claim_token: str | None = None,
    ) -> HermesRunEvent:
        run = self.get(run_id, for_update=True)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        if claim_token is not None:
            self._assert_claim(run, claim_token)
        sequence = (
            int(
                self.db.scalar(
                    select(func.max(HermesRunEvent.sequence)).where(HermesRunEvent.run_id == run_id)
                )
                or 0
            )
            + 1
        )
        sanitized = sanitize_event_payload(payload)
        event_type = str(sanitized.get("event") or "hermes.event")[:160]
        event = HermesRunEvent(
            id=str(uuid4()),
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload=sanitized,
        )
        self.db.add(event)
        self._apply_event(run, event_type, sanitized, sequence=sequence)
        self.db.flush()
        return event

    def apply_status(
        self,
        run_id: str,
        payload: dict[str, Any],
        *,
        claim_token: str,
    ) -> HermesRunProjection:
        status = self._normalize_status(str(payload.get("status") or "running"))
        event_type = str(payload.get("last_event") or f"run.{status}")
        event_payload = {"event": event_type, **payload}
        # Polling is the recovery path after Hermes' single-consumer SSE
        # stream has been disconnected. Approval details live under the
        # status payload's ``approval`` key, while live SSE emits them at the
        # top level. Normalize both transports into the same durable event.
        if event_type == "approval.request" and isinstance(payload.get("approval"), dict):
            event_payload = {
                "event": event_type,
                **payload,
                **payload["approval"],
            }
        self.append_event(run_id, event_payload, claim_token=claim_token)
        run = self.get(run_id)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        return run

    def mark_failure(
        self,
        run_id: str,
        *,
        claim_token: str,
        code: str,
        message: str,
    ) -> None:
        self.append_event(
            run_id,
            {
                "event": "run.failed",
                "run_id": run_id,
                "error": message[:1000],
                "error_code": code[:160],
            },
            claim_token=claim_token,
        )

    def release_execution_claim(
        self,
        run_id: str,
        *,
        claim_token: str,
        status: str | None = None,
    ) -> None:
        run = self.get(run_id, for_update=True)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        self._assert_claim(run, claim_token)
        if status is not None and run.status not in TERMINAL_RUN_STATUSES:
            run.status = self._normalize_status(status)
        run.execution_claim_token = None
        run.execution_claim_expires_at = None
        run.updated_at = utcnow_naive()
        self.db.add(run)
        self.db.flush()

    def list_events_after(
        self,
        run_id: str,
        *,
        after_sequence: int,
        limit: int = 200,
    ) -> list[HermesRunEvent]:
        return list(
            self.db.scalars(
                select(HermesRunEvent)
                .where(
                    HermesRunEvent.run_id == run_id,
                    HermesRunEvent.sequence > after_sequence,
                )
                .order_by(HermesRunEvent.sequence)
                .limit(limit)
            )
        )

    @staticmethod
    def _assert_claim(run: HermesRunProjection, claim_token: str) -> None:
        if run.execution_claim_token != claim_token:
            raise RuntimeError(f"Hermes run execution lease lost: {run.id}")

    @staticmethod
    def _normalize_status(status: str) -> str:
        return {
            "started": "queued",
            "waiting_for_approval": "awaiting_approval",
            "canceled": "cancelled",
        }.get(
            status, status if status in ACTIVE_RUN_STATUSES | TERMINAL_RUN_STATUSES else "running"
        )

    def _apply_event(
        self,
        run: HermesRunProjection,
        event_type: str,
        payload: dict[str, Any],
        *,
        sequence: int,
    ) -> None:
        now = utcnow_naive()
        stop_requested = run.status == "stopping"
        run.updated_at = now
        if event_type == "message.delta":
            run.status = "running"
            run.stage = "agent.responding"
            run.current_activity = "Hermes is composing a response."
        elif event_type == "reasoning.available":
            run.status = "running"
            run.stage = "agent.reasoning"
            run.current_activity = "Hermes is reasoning about the task."
        elif event_type == "subagent.start":
            run.status = "running"
            run.stage = "subagent.running"
            run.current_activity = "Hermes delegated part of the task."
        elif event_type == "subagent.complete":
            run.status = "running"
            run.stage = "subagent.completed"
            run.current_activity = "A delegated task finished."
        elif event_type == "approval.request":
            run.status = "awaiting_approval"
            run.stage = "approval.required"
            run.current_activity = "Waiting for your approval."
            run.pending_approval = {**payload, "sequence": sequence}
            request_id = str(payload.get("request_id") or f"event-{sequence}")[:256]
            approval = self.db.scalar(
                select(HermesToolApproval).where(
                    HermesToolApproval.run_id == run.id,
                    HermesToolApproval.request_id == request_id,
                )
            )
            if approval is None:
                self.db.add(
                    HermesToolApproval(
                        id=str(uuid4()),
                        run_id=run.id,
                        request_id=request_id,
                        status="pending",
                        request_payload=payload,
                        expires_at=now
                        + timedelta(
                            seconds=get_settings().hermes_terminal_approval_timeout_seconds
                        ),
                    )
                )
        elif event_type == "approval.responded":
            run.status = "running"
            run.stage = "agent.running"
            run.current_activity = "Approval resolved; Hermes resumed."
            run.pending_approval = None
        elif event_type == "run.completed":
            run.status = "completed"
            run.stage = "run.completed"
            run.progress_percent = 100
            run.current_activity = "Completed."
            run.output_text = str(payload.get("output") or "")
            usage = payload.get("usage")
            run.usage = usage if isinstance(usage, dict) else {}
            run.finished_at = now
            run.pending_approval = None
            run.execution_claim_token = None
            run.execution_claim_expires_at = None
        elif event_type in {"run.cancelled", "run.interrupted"}:
            run.status = "cancelled" if event_type == "run.cancelled" else "interrupted"
            run.stage = event_type
            run.current_activity = "Stopped." if event_type == "run.cancelled" else "Interrupted."
            run.finished_at = now
            run.pending_approval = None
            run.execution_claim_token = None
            run.execution_claim_expires_at = None
        elif event_type == "run.failed":
            run.status = "failed"
            run.stage = "run.failed"
            run.current_activity = "Failed."
            run.error_code = str(payload.get("error_code") or "hermes.run_failed")[:160]
            run.error_message = str(payload.get("error") or "Hermes run failed.")[:2000]
            run.finished_at = now
            run.pending_approval = None
            run.execution_claim_token = None
            run.execution_claim_expires_at = None
        elif event_type.startswith("tool."):
            run.status = "running"
            run.stage = event_type[:160]
            tool_name = str(payload.get("tool") or payload.get("name") or "tool")[:120]
            run.current_activity = f"Using {tool_name}."
        elif event_type == "run.steered":
            run.status = "running"
            run.stage = "agent.steered"
            run.current_activity = "Guidance accepted."
        else:
            incoming_status = payload.get("status")
            if isinstance(incoming_status, str):
                run.status = self._normalize_status(incoming_status)
            run.stage = event_type[:160]
        if stop_requested and event_type not in {
            "run.completed",
            "run.cancelled",
            "run.interrupted",
            "run.failed",
        }:
            # Events already in flight must not erase a user's stop request.
            # The worker will relay the request as soon as a remote run ID is
            # available and a terminal Hermes event will end this state.
            run.status = "stopping"
            run.stage = "run.stopping"
            run.current_activity = "Stopping Hermes."
        if run.status in TERMINAL_RUN_STATUSES:
            self.db.execute(
                update(HermesToolApproval)
                .where(
                    HermesToolApproval.run_id == run.id,
                    HermesToolApproval.status.in_({"pending", "approved"}),
                    HermesToolApproval.consumed_at.is_(None),
                )
                .values(status="expired")
            )
        self.db.add(run)


class HermesDispatchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def claim_due(
        self,
        *,
        claim_token: str,
        limit: int,
        lease_seconds: int = 120,
    ) -> list[HermesDispatchOutbox]:
        now = utcnow_naive()
        rows = list(
            self.db.scalars(
                select(HermesDispatchOutbox)
                .where(
                    HermesDispatchOutbox.available_at <= now,
                    or_(
                        HermesDispatchOutbox.status == "pending",
                        (
                            (HermesDispatchOutbox.status == "claimed")
                            & (HermesDispatchOutbox.claim_expires_at <= now)
                        ),
                    ),
                )
                .order_by(HermesDispatchOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status = "claimed"
            row.claim_token = claim_token
            row.claimed_at = now
            row.claim_expires_at = now + timedelta(seconds=lease_seconds)
            row.attempts += 1
            row.updated_at = now
            self.db.add(row)
        self.db.flush()
        return rows

    def requeue_stale_dispatched(
        self,
        *,
        limit: int,
        stale_after_seconds: int = 120,
    ) -> int:
        now = utcnow_naive()
        cutoff = now - timedelta(seconds=stale_after_seconds)
        rows = list(
            self.db.scalars(
                select(HermesDispatchOutbox)
                .join(HermesRunProjection, HermesRunProjection.id == HermesDispatchOutbox.run_id)
                .where(
                    HermesDispatchOutbox.status == "dispatched",
                    HermesDispatchOutbox.dispatched_at <= cutoff,
                    HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES),
                    or_(
                        HermesRunProjection.execution_claim_token.is_(None),
                        HermesRunProjection.execution_claim_expires_at <= now,
                    ),
                )
                .order_by(HermesDispatchOutbox.dispatched_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status = "pending"
            row.available_at = now
            row.celery_task_id = None
            row.last_error_code = "dispatch.stale_requeued"
            row.dispatched_at = None
            row.updated_at = now
            self.db.add(row)
        self.db.flush()
        return len(rows)

    def mark_dispatched(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        celery_task_id: str,
    ) -> None:
        row = self._require_claim(outbox_id, claim_token)
        now = utcnow_naive()
        row.status = "dispatched"
        row.celery_task_id = celery_task_id[:128] or None
        row.dispatched_at = now
        row.claim_token = None
        row.claim_expires_at = None
        row.updated_at = now
        self.db.add(row)
        self.db.flush()

    def mark_retry(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        error_code: str,
        retry_at: datetime,
    ) -> None:
        row = self._require_claim(outbox_id, claim_token)
        row.status = "dead_letter" if row.attempts >= 20 else "pending"
        row.available_at = retry_at
        row.last_error_code = error_code[:160]
        row.claim_token = None
        row.claim_expires_at = None
        row.updated_at = utcnow_naive()
        self.db.add(row)
        if row.status == "dead_letter":
            run = self.db.get(HermesRunProjection, row.run_id)
            if run is not None and run.status not in TERMINAL_RUN_STATUSES:
                HermesRunRepository(self.db).append_event(
                    run.id,
                    {
                        "event": "run.failed",
                        "error_code": "hermes.dispatch_exhausted",
                        "error": "Hermes dispatch retries were exhausted.",
                    },
                )
        self.db.flush()

    def mark_cancelled(self, outbox_id: str, *, claim_token: str, error_code: str) -> None:
        row = self._require_claim(outbox_id, claim_token)
        row.status = "cancelled"
        row.last_error_code = error_code[:160]
        row.claim_token = None
        row.claim_expires_at = None
        row.updated_at = utcnow_naive()
        self.db.add(row)
        self.db.flush()

    def _require_claim(self, outbox_id: str, claim_token: str) -> HermesDispatchOutbox:
        row = self.db.get(HermesDispatchOutbox, outbox_id)
        if row is None or row.claim_token != claim_token:
            raise RuntimeError(f"Hermes dispatch claim lost: {outbox_id}")
        return row
