from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.ai_graph.contracts import (
    AiGraphDispatchCreate,
    AiGraphRunRequest,
    GraphRunStatus,
)
from open_work_hub_api.domains.ai_graph.models import (
    AiGraphDispatchOutbox,
    AiGraphRun,
    AiGraphRunInput,
    AiGraphRunNodeProgress,
)


class AiGraphRunNotFoundError(LookupError):
    pass


class AiGraphRunTransitionError(ValueError):
    pass


class AiGraphDispatchTransitionError(ValueError):
    pass


class AiGraphExecutionLeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiGraphExecutionClaim:
    acquired: bool
    status: str
    reason: str | None = None
    resume_from_checkpoint: bool = False


_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AiGraphRunRepository:
    """Persistence for the UI projection, never for LangGraph node state."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, request: AiGraphRunRequest, *, run_id: str | None = None) -> AiGraphRun:
        resolved_run_id = run_id or str(uuid4())
        run = AiGraphRun(
            id=resolved_run_id,
            workspace_id=request.workspace_id,
            requested_by_user_id=request.requested_by_user_id,
            conversation_id=request.conversation_id,
            app_id=request.app_id,
            graph_id=request.graph.graph_id,
            graph_version=request.graph.graph_version,
            checkpoint_thread_id=resolved_run_id,
            checkpoint_ns=request.checkpoint_ns,
            status="pending",
            current_step=0,
            total_steps=len(request.graph.nodes),
            progress_percent=0,
            visibility=request.visibility,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def get(self, run_id: str) -> AiGraphRun | None:
        return self.db.get(AiGraphRun, run_id)

    def require(self, run_id: str) -> AiGraphRun:
        run = self.get(run_id)
        if run is None:
            raise AiGraphRunNotFoundError(run_id)
        return run

    def get_visible(
        self,
        run_id: str,
        *,
        workspace_id: str,
        user_id: str,
        enabled_app_ids: frozenset[str],
    ) -> AiGraphRun | None:
        predicates = [
                AiGraphRun.id == run_id,
                AiGraphRun.workspace_id == workspace_id,
                or_(
                    AiGraphRun.requested_by_user_id == user_id,
                    AiGraphRun.visibility == "workspace",
                ),
        ]
        predicates.append(AiGraphRun.app_id.in_(enabled_app_ids))
        return self.db.scalar(select(AiGraphRun).where(*predicates))

    def list_visible(
        self,
        *,
        workspace_id: str,
        user_id: str,
        status: str | None = None,
        app_id: str | None = None,
        conversation_id: str | None = None,
        enabled_app_ids: frozenset[str],
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AiGraphRun], int]:
        predicates = [
            AiGraphRun.workspace_id == workspace_id,
            or_(
                AiGraphRun.requested_by_user_id == user_id,
                AiGraphRun.visibility == "workspace",
            ),
        ]
        predicates.append(AiGraphRun.app_id.in_(enabled_app_ids))
        if status:
            predicates.append(AiGraphRun.status == status)
        if app_id:
            predicates.append(AiGraphRun.app_id == app_id)
        if conversation_id:
            predicates.append(AiGraphRun.conversation_id == conversation_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(AiGraphRun).where(*predicates)) or 0
        )
        items = list(
            self.db.scalars(
                select(AiGraphRun)
                .where(*predicates)
                .order_by(AiGraphRun.created_at.desc(), AiGraphRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def transition(
        self,
        run_id: str,
        status: GraphRunStatus,
        *,
        stage: str | None = None,
        current_step: int | None = None,
        progress_percent: int | None = None,
        status_message_key: str | None = None,
        error_code: str | None = None,
        claim_token: str | None = None,
    ) -> AiGraphRun:
        run = self.require(run_id)
        if (
            run.execution_claim_token != claim_token
            and (run.execution_claim_token is not None or claim_token is not None)
        ):
            raise AiGraphExecutionLeaseLostError(run_id)
        if status != run.status:
            if status not in _ALLOWED_TRANSITIONS[run.status]:
                raise AiGraphRunTransitionError(
                    f"cannot transition graph run {run.id} from {run.status} to {status}"
                )
            run.status = status

        now = _utcnow_naive()
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in {"completed", "failed", "cancelled"}:
            run.finished_at = now
            run.execution_claim_token = None
            run.execution_lease_expires_at = None
        if status == "completed":
            run.current_step = run.total_steps
            run.progress_percent = 100
        if stage is not None:
            run.stage = stage
        if current_step is not None:
            if current_step < run.current_step or current_step > run.total_steps:
                raise AiGraphRunTransitionError("current_step must be monotonic and within total_steps")
            run.current_step = current_step
        if progress_percent is not None:
            if progress_percent < run.progress_percent or not 0 <= progress_percent <= 100:
                raise AiGraphRunTransitionError("progress_percent must be monotonic and within 0..100")
            run.progress_percent = progress_percent
        if status_message_key is not None:
            run.status_message_key = status_message_key
        if error_code is not None:
            run.error_code = error_code[:2048]
        run.updated_at = now
        self.db.add(run)
        self.db.flush()
        return run

    def claim_execution(
        self,
        run_id: str,
        *,
        claim_token: str,
        lease_duration: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
    ) -> AiGraphExecutionClaim:
        resolved_now = now or _utcnow_naive()
        run = self.db.scalar(
            select(AiGraphRun).where(AiGraphRun.id == run_id).with_for_update()
        )
        if run is None:
            raise AiGraphRunNotFoundError(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return AiGraphExecutionClaim(
                acquired=False,
                status=run.status,
                reason="terminal",
            )
        resume_from_checkpoint = run.status == "running"
        if (
            run.status == "running"
            and run.execution_lease_expires_at is not None
            and run.execution_lease_expires_at > resolved_now
        ):
            return AiGraphExecutionClaim(
                acquired=False,
                status=run.status,
                reason="active_lease",
            )

        run.status = "running"
        run.execution_claim_token = claim_token
        run.execution_claimed_at = resolved_now
        run.execution_lease_expires_at = resolved_now + lease_duration
        run.execution_attempts += 1
        run.started_at = run.started_at or resolved_now
        run.stage = "graph.running"
        run.status_message_key = "ai.graphRun.running"
        run.updated_at = resolved_now
        self.db.add(run)
        self.db.flush()
        return AiGraphExecutionClaim(
            acquired=True,
            status=run.status,
            reason="stale_lease" if resume_from_checkpoint else None,
            resume_from_checkpoint=resume_from_checkpoint,
        )

    def renew_execution_lease(
        self,
        run_id: str,
        *,
        claim_token: str,
        lease_duration: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
    ) -> AiGraphRun:
        """Extend an active execution lease while fencing stale workers."""

        resolved_now = now or _utcnow_naive()
        run = self.db.scalar(
            select(AiGraphRun).where(AiGraphRun.id == run_id).with_for_update()
        )
        if run is None:
            raise AiGraphRunNotFoundError(run_id)
        if run.status != "running" or run.execution_claim_token != claim_token:
            raise AiGraphExecutionLeaseLostError(run_id)
        run.execution_lease_expires_at = resolved_now + lease_duration
        run.updated_at = resolved_now
        self.db.add(run)
        self.db.flush()
        return run

    def advance(
        self,
        run_id: str,
        *,
        node_id: str,
        claim_token: str | None = None,
        lease_duration: timedelta = timedelta(minutes=15),
    ) -> AiGraphRun:
        run = self.db.scalar(
            select(AiGraphRun).where(AiGraphRun.id == run_id).with_for_update()
        )
        if run is None:
            raise AiGraphRunNotFoundError(run_id)
        if run.status != "running":
            return run
        if (
            run.execution_claim_token != claim_token
            and (run.execution_claim_token is not None or claim_token is not None)
        ):
            raise AiGraphExecutionLeaseLostError(run_id)
        marker = self.db.get(
            AiGraphRunNodeProgress,
            {"graph_run_id": run_id, "node_id": node_id},
        )
        if marker is None:
            self.db.add(
                AiGraphRunNodeProgress(
                    graph_run_id=run_id,
                    node_id=node_id,
                )
            )
            self.db.flush()
        completed = int(
            self.db.scalar(
                select(func.count())
                .select_from(AiGraphRunNodeProgress)
                .where(AiGraphRunNodeProgress.graph_run_id == run_id)
            )
            or 0
        )
        run.current_step = max(run.current_step, min(completed, run.total_steps))
        percent = round((run.current_step / run.total_steps) * 100) if run.total_steps else 0
        run.progress_percent = max(run.progress_percent, min(percent, 99))
        run.stage = node_id
        if claim_token is not None:
            run.execution_lease_expires_at = _utcnow_naive() + lease_duration
        run.updated_at = _utcnow_naive()
        self.db.add(run)
        self.db.flush()
        return run


class AiGraphDispatchRepository:
    """Outbox claim/ack/retry operations for an at-least-once publisher."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(self, request: AiGraphDispatchCreate) -> AiGraphDispatchOutbox:
        outbox = AiGraphDispatchOutbox(
            id=str(uuid4()),
            graph_run_id=request.graph_run_id,
            payload_ref=request.payload_ref,
            queue_name=request.queue_name,
            task_name=request.task_name,
            status="pending",
            attempts=0,
            available_at=_utcnow_naive(),
        )
        self.db.add(outbox)
        self.db.flush()
        return outbox

    def claim_due(
        self,
        *,
        claim_token: str,
        limit: int = 25,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> list[AiGraphDispatchOutbox]:
        resolved_now = now or _utcnow_naive()
        stale_before = resolved_now - stale_after
        statement = (
            select(AiGraphDispatchOutbox)
            .where(
                or_(
                    (
                        (AiGraphDispatchOutbox.status == "pending")
                        & (AiGraphDispatchOutbox.available_at <= resolved_now)
                    ),
                    (
                        (AiGraphDispatchOutbox.status == "claimed")
                        & (AiGraphDispatchOutbox.claimed_at < stale_before)
                    ),
                )
            )
            .order_by(
                AiGraphDispatchOutbox.available_at,
                AiGraphDispatchOutbox.created_at,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        claimed = list(self.db.scalars(statement))
        for item in claimed:
            item.status = "claimed"
            item.claim_token = claim_token
            item.claimed_at = resolved_now
            item.attempts += 1
            item.updated_at = resolved_now
            self.db.add(item)
        self.db.flush()
        return claimed

    def mark_dispatched(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        celery_task_id: str,
    ) -> AiGraphDispatchOutbox:
        item = self.db.get(AiGraphDispatchOutbox, outbox_id)
        if item is None or item.status != "claimed" or item.claim_token != claim_token:
            raise AiGraphDispatchTransitionError("dispatch claim is missing or no longer owned")
        now = _utcnow_naive()
        item.status = "dispatched"
        item.celery_task_id = celery_task_id
        item.dispatched_at = now
        item.claim_token = None
        item.updated_at = now
        self.db.add(item)
        self.db.flush()
        return item

    def mark_cancelled(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        error_code: str = "app_execution_disabled",
    ) -> AiGraphDispatchOutbox:
        item = self.db.get(AiGraphDispatchOutbox, outbox_id)
        if item is None or item.status != "claimed" or item.claim_token != claim_token:
            raise AiGraphDispatchTransitionError("dispatch claim is missing or no longer owned")
        item.status = "cancelled"
        item.last_error_code = error_code[:128]
        item.claim_token = None
        item.claimed_at = None
        item.updated_at = _utcnow_naive()
        self.db.add(item)
        self.db.flush()
        return item

    def mark_retry(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        error_code: str,
        retry_at: datetime,
        max_attempts: int = 10,
    ) -> AiGraphDispatchOutbox:
        item = self.db.get(AiGraphDispatchOutbox, outbox_id)
        if item is None or item.status != "claimed" or item.claim_token != claim_token:
            raise AiGraphDispatchTransitionError("dispatch claim is missing or no longer owned")
        item.status = "dead_letter" if item.attempts >= max_attempts else "pending"
        item.available_at = retry_at
        item.last_error_code = error_code[:128]
        item.claim_token = None
        item.claimed_at = None
        item.updated_at = _utcnow_naive()
        self.db.add(item)
        self.db.flush()
        return item


class AiGraphRunInputRepository:
    """Bootstrap input envelope used only until LangGraph has checkpointed it."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        graph_run_id: str,
        payload: dict,
        schema_version: int,
    ) -> AiGraphRunInput:
        envelope = AiGraphRunInput(
            graph_run_id=graph_run_id,
            payload_json=payload,
            schema_version=schema_version,
        )
        self.db.add(envelope)
        self.db.flush()
        return envelope

    def require(self, graph_run_id: str) -> AiGraphRunInput:
        envelope = self.db.get(AiGraphRunInput, graph_run_id)
        if envelope is None:
            raise LookupError(graph_run_id)
        return envelope

    def delete_after_terminal(self, graph_run_id: str) -> None:
        run = self.db.get(AiGraphRun, graph_run_id)
        if run is None or run.status not in {"completed", "failed", "cancelled"}:
            raise ValueError("graph run input can only be deleted after a terminal status")
        envelope = self.db.get(AiGraphRunInput, graph_run_id)
        if envelope is not None:
            self.db.delete(envelope)
            self.db.flush()
