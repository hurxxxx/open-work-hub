from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)
from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.models import (
    HermesDispatchOutbox,
    HermesJobBinding,
    HermesMaintenanceState,
    HermesProfileBinding,
    HermesRunEvent,
    HermesRunProjection,
    HermesToolApproval,
)
from open_work_hub_api.domains.hermes.repository import (
    ACTIVE_RUN_STATUSES,
    HermesRunRepository,
    utcnow_naive,
)
from open_work_hub_api.domains.hermes.service import job_profile_name, runtime_client

_MAINTENANCE_LEASE = timedelta(minutes=3)


def _maintenance_started() -> str | None:
    now = utcnow_naive()
    with get_session_factory()() as db:
        state = db.scalar(
            select(HermesMaintenanceState)
            .where(HermesMaintenanceState.component == "headless")
            .with_for_update()
        )
        if state is None:
            state = HermesMaintenanceState(component="headless", counters={})
        elif (
            state.lease_token
            and state.lease_expires_at is not None
            and state.lease_expires_at > now
        ):
            return None
        lease_token = uuid4().hex
        state.lease_token = lease_token
        state.lease_expires_at = now + _MAINTENANCE_LEASE
        state.last_started_at = now
        state.updated_at = now
        db.add(state)
        db.commit()
        return lease_token


def _maintenance_finished(
    counters: dict[str, int],
    *,
    error_code: str | None,
    lease_token: str,
) -> bool:
    now = utcnow_naive()
    with get_session_factory()() as db:
        state = db.scalar(
            select(HermesMaintenanceState)
            .where(HermesMaintenanceState.component == "headless")
            .with_for_update()
        )
        if state is None or state.lease_token != lease_token:
            return False
        state.counters = counters
        state.last_error_code = error_code
        if error_code is None:
            state.last_succeeded_at = now
        state.lease_token = None
        state.lease_expires_at = None
        state.updated_at = now
        db.add(state)
        db.commit()
        return True


def _maintenance_state_for_update(db) -> HermesMaintenanceState:
    state = db.scalar(
        select(HermesMaintenanceState)
        .where(HermesMaintenanceState.component == "headless")
        .with_for_update()
    )
    if state is None:
        state = HermesMaintenanceState(component="headless", counters={})
        db.add(state)
        db.flush()
    return state


async def _expire_approvals(*, limit: int) -> tuple[int, int]:
    now = utcnow_naive()
    with get_session_factory()() as db:
        approval_ids = list(
            db.scalars(
                select(HermesToolApproval.id)
                .where(
                    HermesToolApproval.status == "pending",
                    HermesToolApproval.expires_at <= now,
                )
                .order_by(HermesToolApproval.expires_at)
                .limit(limit)
            )
        )

    async def expire_one(approval_id: str) -> tuple[int, int]:
        with get_session_factory()() as db:
            approval = db.scalar(
                select(HermesToolApproval)
                .where(
                    HermesToolApproval.id == approval_id,
                    HermesToolApproval.status == "pending",
                    HermesToolApproval.expires_at <= utcnow_naive(),
                )
                .with_for_update(skip_locked=True)
            )
            if approval is None:
                return 0, 0
            run = db.get(HermesRunProjection, approval.run_id)
            profile = (
                db.get(HermesProfileBinding, run.profile_binding_id) if run is not None else None
            )
            if run is None:
                approval.status = "expired"
                approval.choice = "deny"
                approval.decided_at = utcnow_naive()
                db.add(approval)
                db.commit()
                return 1, 0
            if profile is None or not run.hermes_run_id:
                approval.status = "expired"
                approval.choice = "deny"
                approval.decided_at = utcnow_naive()
                db.add(approval)
                HermesRunRepository(db).append_event(
                    run.id,
                    {
                        "event": "run.failed",
                        "error_code": (
                            "hermes.profile_missing"
                            if profile is None
                            else "hermes.remote_run_missing"
                        ),
                        "error": (
                            "The Hermes profile for this expired approval is missing."
                            if profile is None
                            else "Hermes never recorded a remote run for this expired approval."
                        ),
                    },
                )
                db.commit()
                return 1, 0
            try:
                payload = await runtime_client().resolve_approval(
                    profile.profile_name,
                    run.hermes_run_id,
                    request_id=approval.request_id,
                    choice="deny",
                )
            except HermesClientError as error:
                if error.status_code != 404:
                    db.rollback()
                    return 0, 1
                event_payload = {
                    "event": "run.failed",
                    "error_code": "hermes.remote_run_missing",
                    "error": "Hermes no longer has the run for this expired approval.",
                }
            else:
                event_payload = {
                    "event": "approval.responded",
                    "choice": "deny",
                    "expired": True,
                    **payload,
                }
            approval.status = "expired"
            approval.choice = "deny"
            approval.decided_at = utcnow_naive()
            db.add(approval)
            HermesRunRepository(db).append_event(run.id, event_payload)
            db.commit()
            return 1, 0

    results = await asyncio.gather(*(expire_one(approval_id) for approval_id in approval_ids))
    return sum(item[0] for item in results), sum(item[1] for item in results)


def _claim_revoked_runs(*, limit: int) -> list[tuple[str, str, str]]:
    now = utcnow_naive()
    claimed: list[tuple[str, str, str]] = []
    with get_session_factory()() as db:
        state = _maintenance_state_for_update(db)
        window_size = limit * 5
        statement = select(HermesRunProjection).where(
            HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES)
        )
        if state.run_scan_cursor:
            statement = statement.where(HermesRunProjection.id > state.run_scan_cursor)
        runs = list(
            db.scalars(
                statement.order_by(HermesRunProjection.id)
                .with_for_update(skip_locked=True)
                .limit(window_size)
            )
        )
        if not runs and state.run_scan_cursor:
            state.run_scan_cursor = None
            runs = list(
                db.scalars(
                    select(HermesRunProjection)
                    .where(HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES))
                    .order_by(HermesRunProjection.id)
                    .with_for_update(skip_locked=True)
                    .limit(window_size)
                )
            )
        repository = HermesRunRepository(db)
        last_examined_id: str | None = None
        exhausted_window = True
        for run in runs:
            last_examined_id = run.id
            if can_use_app(
                db,
                app_id=run.owner_app_id,
                user_id=run.user_id,
            ):
                continue
            if run.status != "stopping":
                has_live_claim = bool(
                    run.execution_claim_token
                    and run.execution_claim_expires_at is not None
                    and run.execution_claim_expires_at > now
                )
                repository.append_event(
                    run.id,
                    {
                        "event": "run.stop_requested"
                        if has_live_claim or run.hermes_run_id
                        else "run.cancelled",
                        "status": "stopping"
                        if has_live_claim or run.hermes_run_id
                        else "cancelled",
                        "reason": "access_revoked",
                    },
                )
            profile = db.get(HermesProfileBinding, run.profile_binding_id)
            if profile is not None and run.hermes_run_id:
                claimed.append((run.id, profile.profile_name, run.hermes_run_id))
            if len(claimed) >= limit:
                exhausted_window = False
                break
        state.run_scan_cursor = (
            None if exhausted_window and len(runs) < window_size else last_examined_id
        )
        db.add(state)
        db.commit()
    return claimed


async def _stop_revoked_runs(
    rows: list[tuple[str, str, str]],
) -> tuple[int, int]:
    if not rows:
        return 0, 0
    client = runtime_client()

    async def stop_one(row: tuple[str, str, str]) -> tuple[int, int]:
        run_id, profile_name, hermes_run_id = row
        try:
            await client.stop_run(profile_name, hermes_run_id)
        except HermesClientError as error:
            if error.status_code != 404:
                return 0, 1
            with get_session_factory()() as db:
                run = db.scalar(
                    select(HermesRunProjection)
                    .where(HermesRunProjection.id == run_id)
                    .with_for_update()
                )
                if run is not None and run.status in ACTIVE_RUN_STATUSES:
                    HermesRunRepository(db).append_event(
                        run.id,
                        {
                            "event": "run.cancelled",
                            "reason": "access_revoked_remote_missing",
                        },
                    )
                    db.commit()
        return 1, 0

    results = await asyncio.gather(*(stop_one(row) for row in rows))
    return sum(item[0] for item in results), sum(item[1] for item in results)


async def _pause_revoked_jobs(*, limit: int) -> tuple[int, int]:
    with get_session_factory()() as db:
        state = _maintenance_state_for_update(db)
        window_size = limit * 5
        statement = select(HermesJobBinding).where(HermesJobBinding.status == "active")
        if state.job_scan_cursor:
            statement = statement.where(HermesJobBinding.id > state.job_scan_cursor)
        jobs = list(db.scalars(statement.order_by(HermesJobBinding.id).limit(window_size)))
        if not jobs and state.job_scan_cursor:
            state.job_scan_cursor = None
            jobs = list(
                db.scalars(
                    select(HermesJobBinding)
                    .where(HermesJobBinding.status == "active")
                    .order_by(HermesJobBinding.id)
                    .limit(window_size)
                )
            )
        job_ids: list[str] = []
        last_examined_id: str | None = None
        exhausted_window = True
        for job in jobs:
            last_examined_id = job.id
            if can_use_app(
                db,
                app_id="chatbot",
                user_id=job.user_id,
            ):
                continue
            job_ids.append(job.id)
            if len(job_ids) >= limit:
                exhausted_window = False
                break
        state.job_scan_cursor = (
            None if exhausted_window and len(jobs) < window_size else last_examined_id
        )
        db.add(state)
        db.commit()
    if not job_ids:
        return 0, 0
    client = runtime_client()

    async def pause_one(job_id: str) -> tuple[int, int]:
        with get_session_factory()() as db:
            job = db.scalar(
                select(HermesJobBinding)
                .where(
                    HermesJobBinding.id == job_id,
                    HermesJobBinding.status == "active",
                )
                .with_for_update(skip_locked=True)
            )
            if job is None or can_use_app(
                db,
                app_id="chatbot",
                user_id=job.user_id,
            ):
                return 0, 0
            profile = db.get(HermesProfileBinding, job.profile_binding_id)
            if profile is None:
                job.status = "error"
                db.add(job)
                db.commit()
                return 0, 1
            try:
                await client.job_action(
                    job_profile_name(profile),
                    job.hermes_job_id,
                    "pause",
                )
            except HermesClientError as error:
                if error.status_code != 404:
                    db.rollback()
                    return 0, 1
            job.status = "paused"
            job.updated_at = utcnow_naive()
            db.add(job)
            db.commit()
            return 1, 0

    results = await asyncio.gather(*(pause_one(job_id) for job_id in job_ids))
    return sum(item[0] for item in results), sum(item[1] for item in results)


def _delete_expired_events(*, retention_days: int, limit: int) -> int:
    cutoff = utcnow_naive() - timedelta(days=retention_days)
    with get_session_factory()() as db:
        run_ids = list(
            db.scalars(
                select(HermesRunProjection.id)
                .where(
                    HermesRunProjection.finished_at.is_not(None),
                    HermesRunProjection.finished_at <= cutoff,
                )
                .order_by(HermesRunProjection.finished_at)
                .limit(limit)
            )
        )
        if not run_ids:
            return 0
        event_count = int(
            db.execute(delete(HermesRunEvent).where(HermesRunEvent.run_id.in_(run_ids))).rowcount
            or 0
        )
        db.execute(delete(HermesDispatchOutbox).where(HermesDispatchOutbox.run_id.in_(run_ids)))
        db.commit()
        return event_count


async def maintain_headless_hermes_once(*, limit: int = 20) -> dict[str, int]:
    limit = max(1, min(limit, 5))
    errors = 0
    try:
        lease_token = await asyncio.to_thread(_maintenance_started)
    except Exception:
        return {"maintenance_skipped": 1, "errors": 1}
    if lease_token is None:
        return {"maintenance_skipped": 1, "errors": 0}

    async def approval_phase() -> tuple[int, int]:
        try:
            return await _expire_approvals(limit=limit)
        except Exception:
            return 0, 1

    async def run_phase() -> tuple[list[tuple[str, str, str]], int, int]:
        try:
            rows = await asyncio.to_thread(_claim_revoked_runs, limit=limit)
            stopped, failures = await _stop_revoked_runs(rows)
            return rows, stopped, failures
        except Exception:
            return [], 0, 1

    async def job_phase() -> tuple[int, int]:
        try:
            return await _pause_revoked_jobs(limit=limit)
        except Exception:
            return 0, 1

    approval_result, run_result, job_result = await asyncio.gather(
        approval_phase(),
        run_phase(),
        job_phase(),
    )
    expired_approvals, approval_failures = approval_result
    revoked_runs, stopped_runs, stop_failures = run_result
    paused_jobs, pause_failures = job_result
    errors += approval_failures + stop_failures + pause_failures

    try:
        deleted_events = await asyncio.to_thread(
            _delete_expired_events,
            retention_days=get_settings().hermes_terminal_artifact_retention_days,
            limit=limit * 25,
        )
    except Exception:
        deleted_events = 0
        errors += 1

    counters = {
        "expired_approvals": expired_approvals,
        "revoked_runs_claimed": len(revoked_runs),
        "revoked_runs_stopped": stopped_runs,
        "revoked_jobs_paused": paused_jobs,
        "events_deleted": deleted_events,
        "errors": errors,
    }
    try:
        finished = await asyncio.to_thread(
            _maintenance_finished,
            counters,
            error_code="hermes.maintenance_partial_failure" if errors else None,
            lease_token=lease_token,
        )
        if not finished:
            counters["errors"] += 1
    except Exception:
        counters["errors"] += 1
    return counters


__all__ = ["maintain_headless_hermes_once"]
