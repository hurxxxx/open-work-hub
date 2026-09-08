from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import and_, or_, select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.hermes.models import HermesMaintenanceState
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
    HermesTerminalBrokerError,
)
from open_work_hub_api.domains.hermes_terminal.lifecycle import (
    HERMES_TERMINAL_ARCHIVE_FAILURE,
    HERMES_TERMINAL_FINAL_STATUSES,
    fail_missing_terminal_runtime,
    finalize_terminal_session,
    reconcile_terminal_session_if_finished,
    release_terminal_runtime,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HermesTerminalArtifact,
    HermesTerminalSession,
    HermesTerminalToolApproval,
)
from open_work_hub_api.domains.hermes_terminal.storage import remove_object

_IDLE_ELIGIBLE_STATUSES = ("starting", "running", "awaiting_approval")
_RECONCILE_STATUSES = (*_IDLE_ELIGIBLE_STATUSES, "stopping", "archiving")
_ARCHIVE_RETRY_LIMIT = 3
_ARCHIVE_RETRY_DELAY = timedelta(minutes=1)
_ARCHIVE_STALE_AFTER = timedelta(minutes=10)
_STARTING_RUNTIME_GRACE = timedelta(minutes=5)
_ARCHIVE_CLAIM_LEASE = timedelta(minutes=15)
_MAINTENANCE_LEASE = timedelta(minutes=16)
_T = TypeVar("_T")


async def _gather_bounded(
    items: Sequence[_T],
    operation: Callable[[_T], Awaitable[Any]],
) -> list[Any | BaseException]:
    semaphore = asyncio.Semaphore(1)

    async def run(item: _T) -> Any:
        async with semaphore:
            return await operation(item)

    return await asyncio.gather(
        *(run(item) for item in items),
        return_exceptions=True,
    )


def _restore_running_if_no_pending_approval(db, session_id: str, now) -> None:
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


def _expire_approvals(*, limit: int) -> int:
    now = utcnow_naive()
    with get_session_factory()() as db:
        approvals = list(
            db.scalars(
                select(HermesTerminalToolApproval)
                .where(
                    HermesTerminalToolApproval.status == "pending",
                    HermesTerminalToolApproval.expires_at <= now,
                )
                .order_by(HermesTerminalToolApproval.expires_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        session_ids: set[str] = set()
        for approval in approvals:
            approval.status = "expired"
            approval.choice = "timeout"
            approval.decided_at = now
            session_ids.add(approval.session_id)
            db.add(approval)
        for session_id in session_ids:
            _restore_running_if_no_pending_approval(db, session_id, now)
        db.commit()
        return len(approvals)


def _claim_idle_sessions(*, limit: int) -> list[str]:
    now = utcnow_naive()
    with get_session_factory()() as db:
        sessions = list(
            db.scalars(
                select(HermesTerminalSession)
                .where(
                    HermesTerminalSession.status.in_(_IDLE_ELIGIBLE_STATUSES),
                    HermesTerminalSession.idle_expires_at <= now,
                )
                .order_by(HermesTerminalSession.idle_expires_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for session in sessions:
            session.status = "stopping"
            session.failure_code = "hermes_terminal.idle_timeout"
            db.add(session)
        db.commit()
        return [session.id for session in sessions]


def _reconcile_candidates(*, limit: int) -> list[str]:
    cutoff = utcnow_naive() - timedelta(seconds=30)
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(HermesTerminalSession.id)
                .where(
                    HermesTerminalSession.status.in_(_RECONCILE_STATUSES),
                    HermesTerminalSession.updated_at <= cutoff,
                )
                .order_by(HermesTerminalSession.updated_at)
                .limit(limit)
            )
        )


async def _stop_idle_session(session_id: str) -> bool:
    broker = HermesTerminalBrokerClient()
    try:
        stopped = await broker.stop_session(session_id)
    except HermesTerminalBrokerError as error:
        if error.status_code == 404:
            await fail_missing_terminal_runtime(
                session_id,
                actor_user_id=None,
            )
            return False
        with get_session_factory()() as db:
            session = db.get(HermesTerminalSession, session_id)
            if session is not None and session.status == "stopping":
                session.failure_code = "hermes_terminal.idle_stop_failed"
                db.add(session)
                db.commit()
        return False
    await finalize_terminal_session(
        session_id,
        target_status="terminated",
        exit_code=stopped.exit_code,
        actor_user_id=None,
    )
    return True


def _claim_revoked_sessions(*, limit: int) -> list[str]:
    with get_session_factory()() as db:
        sessions = list(
            db.scalars(
                select(HermesTerminalSession)
                .where(HermesTerminalSession.status.in_(_IDLE_ELIGIBLE_STATUSES))
                .order_by(HermesTerminalSession.updated_at)
                .with_for_update(skip_locked=True)
                .limit(limit * 5)
            )
        )
        claimed: list[str] = []
        for session in sessions:
            user = db.get(User, session.user_id)
            allowed = bool(
                user is not None
                and user.status == "active"
                and not user.login_blocked
                and can_use_app(
                    db,
                    app_id="hermes-terminal",
                    user_id=user.id,
                )
            )
            if allowed:
                continue
            session.status = "stopping"
            session.failure_code = "hermes_terminal.access_revoked"
            db.add(session)
            claimed.append(session.id)
            if len(claimed) >= limit:
                break
        db.commit()
        return claimed


async def _reconcile_session(session_id: str) -> None:
    with get_session_factory()() as db:
        session = db.get(HermesTerminalSession, session_id)
        if session is None:
            return
        status = session.status
        missing_is_failure = status != "starting" or session.updated_at <= (
            utcnow_naive() - _STARTING_RUNTIME_GRACE
        )
        db.expunge(session)
    if status == "stopping":
        await _stop_idle_session(session_id)
        return
    await reconcile_terminal_session_if_finished(
        session,
        missing_is_failure=missing_is_failure,
    )


def _claim_archive_retries(
    *,
    limit: int,
) -> list[tuple[str, str, int | None, str, str]]:
    now = utcnow_naive()
    stale_cutoff = now - _ARCHIVE_STALE_AFTER
    retry_cutoff = now - _ARCHIVE_RETRY_DELAY
    claim_available = or_(
        HermesTerminalSession.archive_claim_expires_at <= now,
        and_(
            HermesTerminalSession.archive_claim_expires_at.is_(None),
            or_(
                HermesTerminalSession.archive_started_at.is_(None),
                HermesTerminalSession.archive_started_at <= stale_cutoff,
            ),
        ),
    )
    with get_session_factory()() as db:
        sessions = list(
            db.scalars(
                select(HermesTerminalSession)
                .where(
                    HermesTerminalSession.archive_target_status.is_not(None),
                    HermesTerminalSession.archive_attempts < _ARCHIVE_RETRY_LIMIT,
                    or_(
                        and_(
                            HermesTerminalSession.status == "archiving",
                            or_(
                                and_(
                                    HermesTerminalSession.archive_failure_code
                                    == HERMES_TERMINAL_ARCHIVE_FAILURE,
                                    HermesTerminalSession.updated_at <= retry_cutoff,
                                    claim_available,
                                ),
                                and_(
                                    HermesTerminalSession.archive_failure_code.is_(None),
                                    claim_available,
                                ),
                            ),
                        ),
                        and_(
                            HermesTerminalSession.status.in_(HERMES_TERMINAL_FINAL_STATUSES),
                            HermesTerminalSession.archive_failure_code
                            == HERMES_TERMINAL_ARCHIVE_FAILURE,
                            HermesTerminalSession.updated_at <= retry_cutoff,
                            claim_available,
                        ),
                    ),
                )
                .order_by(HermesTerminalSession.updated_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        claimed: list[tuple[str, str, int | None, str, str]] = []
        for session in sessions:
            target_status = session.archive_target_status
            if target_status is None:
                continue
            session.status = "archiving"
            claim_token = uuid4().hex
            session.archive_started_at = now
            session.archive_claim_token = claim_token
            session.archive_claim_expires_at = now + _ARCHIVE_CLAIM_LEASE
            session.updated_at = now
            db.add(session)
            claimed.append(
                (
                    session.id,
                    target_status,
                    session.exit_code,
                    session.user_id,
                    claim_token,
                )
            )
        db.commit()
        return claimed


async def _retry_archive(
    item: tuple[str, str, int | None, str, str],
) -> bool:
    session_id, target_status, exit_code, user_id, claim_token = item
    return await finalize_terminal_session(
        session_id,
        target_status=target_status,
        exit_code=exit_code,
        actor_user_id=user_id,
        resume_archiving=True,
        archive_claim_token=claim_token,
    )


def _abandon_exhausted_archives(*, limit: int) -> int:
    now = utcnow_naive()
    stale_cutoff = now - _ARCHIVE_STALE_AFTER
    retry_cutoff = now - _ARCHIVE_RETRY_DELAY
    claim_available = or_(
        HermesTerminalSession.archive_claim_expires_at <= now,
        and_(
            HermesTerminalSession.archive_claim_expires_at.is_(None),
            or_(
                HermesTerminalSession.archive_started_at.is_(None),
                HermesTerminalSession.archive_started_at <= stale_cutoff,
            ),
        ),
    )
    with get_session_factory()() as db:
        sessions = list(
            db.scalars(
                select(HermesTerminalSession)
                .where(
                    HermesTerminalSession.status == "archiving",
                    HermesTerminalSession.archive_target_status.is_not(None),
                    HermesTerminalSession.archive_attempts >= _ARCHIVE_RETRY_LIMIT,
                    or_(
                        and_(
                            HermesTerminalSession.archive_failure_code
                            == HERMES_TERMINAL_ARCHIVE_FAILURE,
                            HermesTerminalSession.updated_at <= retry_cutoff,
                            claim_available,
                        ),
                        and_(
                            HermesTerminalSession.archive_failure_code.is_(None),
                            claim_available,
                        ),
                    ),
                )
                .order_by(HermesTerminalSession.archive_started_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for session in sessions:
            session.status = session.archive_target_status or "failed"
            session.archive_failure_code = HERMES_TERMINAL_ARCHIVE_FAILURE
            session.archive_claim_token = None
            session.archive_claim_expires_at = None
            session.workspace_retained = True
            session.quarantine_reason = "hermes_terminal.archive_exhausted"
            session.ended_at = session.ended_at or now
            session.updated_at = now
            db.add(session)
        db.commit()
        return len(sessions)


def _runtime_release_candidates(*, limit: int) -> list[tuple[str, bool]]:
    with get_session_factory()() as db:
        rows = list(
            db.scalars(
                select(HermesTerminalSession)
                .where(
                    HermesTerminalSession.status.in_(HERMES_TERMINAL_FINAL_STATUSES),
                    HermesTerminalSession.runtime_handle.is_not(None),
                    HermesTerminalSession.workspace_retained.is_(False),
                    or_(
                        HermesTerminalSession.archive_failure_code.is_(None),
                        HermesTerminalSession.archive_attempts >= _ARCHIVE_RETRY_LIMIT,
                    ),
                )
                .order_by(HermesTerminalSession.updated_at)
                .limit(limit)
            )
        )
        return [(row.id, row.archive_failure_code is not None) for row in rows]


async def _release_runtime(item: tuple[str, bool]) -> bool:
    session_id, abandon_archive = item
    return await release_terminal_runtime(
        session_id,
        abandon_archive=abandon_archive,
    )


def _delete_expired_artifacts(*, limit: int) -> int:
    now = utcnow_naive()
    with get_session_factory()() as db:
        artifacts = list(
            db.scalars(
                select(HermesTerminalArtifact)
                .where(HermesTerminalArtifact.expires_at <= now)
                .order_by(HermesTerminalArtifact.expires_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        deleted = 0
        for artifact in artifacts:
            try:
                remove_object(artifact.object_key)
            except Exception:
                continue
            db.delete(artifact)
            deleted += 1
        db.commit()
        return deleted


def _known_runtime_session_ids() -> set[str]:
    with get_session_factory()() as db:
        return set(
            db.scalars(
                select(HermesTerminalSession.id).where(
                    HermesTerminalSession.runtime_handle.is_not(None)
                )
            )
        )


def _maintenance_started() -> str | None:
    now = utcnow_naive()
    with get_session_factory()() as db:
        state = db.scalar(
            select(HermesMaintenanceState)
            .where(HermesMaintenanceState.component == "terminal")
            .with_for_update()
        )
        if state is None:
            state = HermesMaintenanceState(component="terminal", counters={})
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
            .where(HermesMaintenanceState.component == "terminal")
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


async def maintain_hermes_terminal_once(*, limit: int = 20) -> dict[str, int]:
    errors = 0
    try:
        lease_token = await asyncio.to_thread(_maintenance_started)
    except Exception:
        return {"maintenance_skipped": 1, "errors": 1}
    if lease_token is None:
        return {"maintenance_skipped": 1, "errors": 0}

    async def thread_call(function, *, default, **kwargs):
        nonlocal errors
        try:
            return await asyncio.to_thread(function, **kwargs)
        except Exception:
            errors += 1
            return default

    expired_approvals = await thread_call(
        _expire_approvals,
        default=0,
        limit=limit * 5,
    )
    revoked_session_ids = await thread_call(
        _claim_revoked_sessions,
        default=[],
        limit=limit,
    )
    revoked_results = await _gather_bounded(
        revoked_session_ids,
        _stop_idle_session,
    )
    errors += sum(isinstance(result, BaseException) for result in revoked_results)

    idle_session_ids = await thread_call(
        _claim_idle_sessions,
        default=[],
        limit=limit,
    )
    idle_results = await _gather_bounded(
        idle_session_ids,
        _stop_idle_session,
    )
    errors += sum(isinstance(result, BaseException) for result in idle_results)

    reconcile_ids = await thread_call(
        _reconcile_candidates,
        default=[],
        limit=limit,
    )
    reconcile_results = await _gather_bounded(
        reconcile_ids,
        _reconcile_session,
    )
    errors += sum(isinstance(result, BaseException) for result in reconcile_results)

    archive_retry_items = await thread_call(
        _claim_archive_retries,
        default=[],
        limit=limit,
    )
    archive_retry_results = await _gather_bounded(
        archive_retry_items,
        _retry_archive,
    )
    errors += sum(isinstance(result, BaseException) for result in archive_retry_results)

    abandoned_archives = await thread_call(
        _abandon_exhausted_archives,
        default=0,
        limit=limit,
    )
    runtime_release_items = await thread_call(
        _runtime_release_candidates,
        default=[],
        limit=limit,
    )
    runtime_release_results = await _gather_bounded(
        runtime_release_items,
        _release_runtime,
    )
    errors += sum(isinstance(result, BaseException) for result in runtime_release_results)
    deleted_artifacts = await thread_call(
        _delete_expired_artifacts,
        default=0,
        limit=limit * 25,
    )

    reconciled_resources = {
        "removed_runners": 0,
        "removed_workspaces": 0,
        "removed_utilities": 0,
    }
    try:
        known_session_ids = await asyncio.to_thread(_known_runtime_session_ids)
        reconciled_resources = await HermesTerminalBrokerClient().reconcile_resources(
            known_session_ids
        )
    except Exception:
        errors += 1

    counters = {
        "expired_approvals": int(expired_approvals),
        "revoked_sessions_claimed": len(revoked_session_ids),
        "revoked_sessions_stopped": sum(result is True for result in revoked_results),
        "idle_sessions_claimed": len(idle_session_ids),
        "idle_sessions_stopped": sum(result is True for result in idle_results),
        "sessions_reconciled": len(reconcile_ids),
        "archive_retries_claimed": len(archive_retry_items),
        "archive_retries_succeeded": sum(result is True for result in archive_retry_results),
        "archives_abandoned": int(abandoned_archives),
        "runtimes_released": sum(result is True for result in runtime_release_results),
        "artifacts_deleted": int(deleted_artifacts),
        "orphan_runners_removed": reconciled_resources["removed_runners"],
        "orphan_workspaces_removed": reconciled_resources["removed_workspaces"],
        "stale_utilities_removed": reconciled_resources["removed_utilities"],
        "errors": errors,
    }
    try:
        finished = await asyncio.to_thread(
            _maintenance_finished,
            counters,
            error_code="hermes_terminal.maintenance_partial_failure" if errors else None,
            lease_token=lease_token,
        )
        if not finished:
            counters["errors"] += 1
    except Exception:
        counters["errors"] += 1
    return counters
