from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import and_, or_, select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
    HermesTerminalBrokerError,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HermesTerminalArtifact,
    HermesTerminalSession,
    HermesTerminalToolApproval,
)
from open_work_hub_api.domains.hermes_terminal.lifecycle import (
    HERMES_TERMINAL_ARCHIVE_FAILURE,
    HERMES_TERMINAL_FINAL_STATUSES,
    fail_missing_terminal_runtime,
    finalize_terminal_session,
    reconcile_terminal_session_if_finished,
    release_terminal_runtime,
)
from open_work_hub_api.domains.hermes_terminal.storage import remove_object


_IDLE_ELIGIBLE_STATUSES = ("starting", "running", "awaiting_approval")
_RECONCILE_STATUSES = (*_IDLE_ELIGIBLE_STATUSES, "stopping")
_ARCHIVE_RETRY_LIMIT = 3
_ARCHIVE_RETRY_DELAY = timedelta(minutes=1)
_ARCHIVE_STALE_AFTER = timedelta(minutes=10)
_STARTING_RUNTIME_GRACE = timedelta(minutes=5)


def _restore_running_if_no_pending_approval(db, session_id: str, now) -> None:
    has_pending = db.scalar(
        select(HermesTerminalToolApproval.id).where(
            HermesTerminalToolApproval.session_id == session_id,
            HermesTerminalToolApproval.status == "pending",
            HermesTerminalToolApproval.expires_at > now,
        ).limit(1)
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
) -> list[tuple[str, str, int | None, str]]:
    now = utcnow_naive()
    stale_cutoff = now - _ARCHIVE_STALE_AFTER
    retry_cutoff = now - _ARCHIVE_RETRY_DELAY
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
                                ),
                                and_(
                                    HermesTerminalSession.archive_failure_code.is_(
                                        None
                                    ),
                                    or_(
                                        HermesTerminalSession.archive_started_at.is_(
                                            None
                                        ),
                                        HermesTerminalSession.archive_started_at
                                        <= stale_cutoff,
                                    ),
                                ),
                            ),
                        ),
                        and_(
                            HermesTerminalSession.status.in_(
                                HERMES_TERMINAL_FINAL_STATUSES
                            ),
                            HermesTerminalSession.archive_failure_code
                            == HERMES_TERMINAL_ARCHIVE_FAILURE,
                            HermesTerminalSession.updated_at <= retry_cutoff,
                        ),
                    ),
                )
                .order_by(HermesTerminalSession.updated_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        claimed: list[tuple[str, str, int | None, str]] = []
        for session in sessions:
            target_status = session.archive_target_status
            if target_status is None:
                continue
            session.status = "archiving"
            session.archive_started_at = now
            session.updated_at = now
            db.add(session)
            claimed.append(
                (session.id, target_status, session.exit_code, session.user_id)
            )
        db.commit()
        return claimed


async def _retry_archive(
    item: tuple[str, str, int | None, str],
) -> bool:
    session_id, target_status, exit_code, user_id = item
    return await finalize_terminal_session(
        session_id,
        target_status=target_status,
        exit_code=exit_code,
        actor_user_id=user_id,
        resume_archiving=True,
    )


def _abandon_exhausted_archives(*, limit: int) -> int:
    now = utcnow_naive()
    stale_cutoff = now - _ARCHIVE_STALE_AFTER
    retry_cutoff = now - _ARCHIVE_RETRY_DELAY
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
                        ),
                        and_(
                            HermesTerminalSession.archive_failure_code.is_(None),
                            HermesTerminalSession.archive_started_at <= stale_cutoff,
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
                    or_(
                        HermesTerminalSession.archive_failure_code.is_(None),
                        HermesTerminalSession.archive_attempts
                        >= _ARCHIVE_RETRY_LIMIT,
                    ),
                )
                .order_by(HermesTerminalSession.updated_at)
                .limit(limit)
            )
        )
        return [
            (row.id, row.archive_failure_code is not None)
            for row in rows
        ]


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
        for artifact in artifacts:
            remove_object(artifact.object_key)
            db.delete(artifact)
        db.commit()
        return len(artifacts)


async def maintain_hermes_terminal_once(*, limit: int = 20) -> dict[str, int]:
    expired_approvals = await asyncio.to_thread(_expire_approvals, limit=limit * 5)
    idle_session_ids = await asyncio.to_thread(_claim_idle_sessions, limit=limit)
    idle_results = await asyncio.gather(
        *(_stop_idle_session(session_id) for session_id in idle_session_ids)
    )
    reconcile_ids = await asyncio.to_thread(_reconcile_candidates, limit=limit)
    await asyncio.gather(*(_reconcile_session(session_id) for session_id in reconcile_ids))
    archive_retry_items = await asyncio.to_thread(
        _claim_archive_retries,
        limit=limit,
    )
    archive_retry_results = await asyncio.gather(
        *(_retry_archive(item) for item in archive_retry_items)
    )
    abandoned_archives = await asyncio.to_thread(
        _abandon_exhausted_archives,
        limit=limit,
    )
    runtime_release_items = await asyncio.to_thread(
        _runtime_release_candidates,
        limit=limit,
    )
    runtime_release_results = await asyncio.gather(
        *(_release_runtime(item) for item in runtime_release_items)
    )
    deleted_artifacts = await asyncio.to_thread(
        _delete_expired_artifacts,
        limit=limit * 25,
    )
    return {
        "expired_approvals": expired_approvals,
        "idle_sessions_claimed": len(idle_session_ids),
        "idle_sessions_stopped": sum(idle_results),
        "sessions_reconciled": len(reconcile_ids),
        "archive_retries_claimed": len(archive_retry_items),
        "archive_retries_succeeded": sum(archive_retry_results),
        "archives_abandoned": abandoned_archives,
        "runtimes_released": sum(runtime_release_results),
        "artifacts_deleted": deleted_artifacts,
    }
