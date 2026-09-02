from __future__ import annotations

import asyncio
import hashlib
import tarfile
from datetime import timedelta
from pathlib import PurePosixPath
from uuid import uuid4

from minio.error import MinioException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.hermes_terminal.broker_client import (
    HermesTerminalBrokerClient,
    HermesTerminalBrokerError,
)
from open_work_hub_api.domains.hermes_terminal.models import (
    HERMES_TERMINAL_ACTIVE_STATUSES,
    HermesTerminalArtifact,
    HermesTerminalProfileState,
    HermesTerminalSession,
)
from open_work_hub_api.domains.hermes_terminal.security import terminal_profile_name
from open_work_hub_api.domains.hermes_terminal.storage import (
    artifact_storage_key,
    collect_workspace_artifacts,
    profile_storage_key,
    put_object,
    remove_object,
)


HERMES_TERMINAL_FINAL_STATUSES = frozenset({"exited", "terminated", "failed"})
HERMES_TERMINAL_ARCHIVE_FAILURE = "hermes_terminal.archive_failed"
_ARCHIVE_CLAIM_LEASE = timedelta(minutes=15)


def _persist_archive_objects(
    *,
    workspace_id: str,
    user_id: str,
    session_id: str,
    profile_archive: bytes,
    workspace_archive: bytes,
    workspace_archive_max_bytes: int,
    attempt_id: str,
) -> tuple[
    str,
    str,
    list[tuple[str, int, str, str, str]],
    int,
    int,
    list[str],
]:
    scan = collect_workspace_artifacts(
        workspace_archive,
        max_total_bytes=workspace_archive_max_bytes,
    )
    profile_key = profile_storage_key(
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        attempt_id=attempt_id,
    )
    uploaded_keys: list[str] = []
    artifacts: list[tuple[str, int, str, str, str]] = []
    try:
        # Record the immutable destination before each PUT. A transport error can
        # arrive after object storage accepted the body, so cleanup must also try
        # the key whose PUT had an ambiguous result.
        uploaded_keys.append(profile_key)
        put_object(key=profile_key, data=profile_archive, content_type="application/gzip")
        for relative_path, data, media_type, digest in scan.items:
            object_key = artifact_storage_key(
                workspace_id=workspace_id,
                user_id=user_id,
                session_id=session_id,
                attempt_id=attempt_id,
                path=relative_path,
            )
            uploaded_keys.append(object_key)
            put_object(key=object_key, data=data, content_type=media_type)
            artifacts.append((relative_path, len(data), media_type, digest, object_key))
    except Exception:
        # The caller cannot observe a partially constructed uploaded_keys result.
        # Clean the immutable attempt prefix here before propagating the failure.
        _remove_uploaded_objects(uploaded_keys)
        raise
    return (
        profile_key,
        hashlib.sha256(profile_archive).hexdigest(),
        artifacts,
        scan.archived_bytes,
        scan.omitted_count,
        uploaded_keys,
    )


def _remove_uploaded_objects(keys: list[str]) -> None:
    for key in keys:
        try:
            remove_object(key)
        except Exception:
            # Cleanup is best effort after an already-failed immutable attempt.
            # A second transport/client failure must not hide the archive state
            # transition; unreferenced keys remain safe to reap independently.
            continue


async def finalize_terminal_session(
    session_id: str,
    *,
    target_status: str,
    exit_code: int | None,
    actor_user_id: str | None,
    resume_archiving: bool = False,
    archive_claim_token: str | None = None,
    failure_code: str | None = None,
) -> bool:
    if target_status not in HERMES_TERMINAL_FINAL_STATUSES:
        raise ValueError("Hermes terminal final status is invalid.")
    with get_session_factory()() as db:
        row = db.scalar(
            select(HermesTerminalSession)
            .where(HermesTerminalSession.id == session_id)
            .with_for_update()
        )
        if row is None:
            return False
        if resume_archiving:
            if (
                row.status != "archiving"
                or row.archive_target_status is None
                or not archive_claim_token
                or row.archive_claim_token != archive_claim_token
            ):
                return False
            target_status = row.archive_target_status
        elif row.status == "archiving" or row.status in HERMES_TERMINAL_FINAL_STATUSES:
            return False
        now = utcnow_naive()
        claim_token = archive_claim_token or uuid4().hex
        row.status = "archiving"
        row.archive_target_status = target_status
        row.archive_attempts += 1
        row.archive_started_at = now
        row.archive_claim_token = claim_token
        row.archive_claim_expires_at = now + _ARCHIVE_CLAIM_LEASE
        row.archive_failure_code = None
        if failure_code:
            row.failure_code = failure_code[:160]
        db.add(row)
        db.commit()
        workspace_id = row.workspace_id
        user_id = row.user_id
        profile_binding_id = row.profile_binding_id

    broker = HermesTerminalBrokerClient()
    archive_failure: str | None = None
    uploaded_keys: list[str] = []
    stale_object_keys: list[str] = []
    try:
        profile_archive, workspace_archive = await asyncio.gather(
            broker.export_profile(session_id),
            broker.export_workspace(session_id),
        )
        settings = get_settings()
        if len(profile_archive) > settings.hermes_terminal_profile_archive_max_bytes:
            raise ValueError("profile archive too large")
        (
            profile_key,
            profile_digest,
            artifact_rows,
            artifact_archived_bytes,
            artifact_omitted_count,
            uploaded_keys,
        ) = await asyncio.to_thread(
            _persist_archive_objects,
            workspace_id=workspace_id,
            user_id=user_id,
            session_id=session_id,
            profile_archive=profile_archive,
            workspace_archive=workspace_archive,
            workspace_archive_max_bytes=settings.hermes_terminal_workspace_archive_max_bytes,
            attempt_id=claim_token,
        )
        now = utcnow_naive()
        expires_at = now + timedelta(days=settings.hermes_terminal_artifact_retention_days)
        with get_session_factory()() as db:
            row = db.scalar(
                select(HermesTerminalSession)
                .where(HermesTerminalSession.id == session_id)
                .with_for_update()
            )
            if row is None or row.status != "archiving" or row.archive_claim_token != claim_token:
                await asyncio.to_thread(_remove_uploaded_objects, uploaded_keys)
                return False
            state = db.get(HermesTerminalProfileState, profile_binding_id)
            if state is None:
                state = HermesTerminalProfileState(
                    profile_binding_id=profile_binding_id,
                    profile_name=terminal_profile_name(profile_binding_id),
                )
            if state.object_key and state.object_key != profile_key:
                stale_object_keys.append(state.object_key)
            state.object_key = profile_key
            state.archive_sha256 = profile_digest
            state.archive_size_bytes = len(profile_archive)
            state.revision += 1
            state.exported_at = now
            db.add(state)
            existing = {
                item.relative_path: item
                for item in db.scalars(
                    select(HermesTerminalArtifact).where(
                        HermesTerminalArtifact.session_id == session_id
                    )
                )
            }
            for relative_path, size_bytes, media_type, digest, object_key in artifact_rows:
                artifact = existing.pop(relative_path, None)
                if artifact is None:
                    artifact = HermesTerminalArtifact(
                        id=str(uuid4()),
                        session_id=session_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        relative_path=relative_path,
                        display_name=PurePosixPath(relative_path).name,
                        size_bytes=size_bytes,
                        media_type=media_type,
                        sha256=digest,
                        object_key=object_key,
                        expires_at=expires_at,
                    )
                else:
                    if artifact.object_key != object_key:
                        stale_object_keys.append(artifact.object_key)
                    artifact.size_bytes = size_bytes
                    artifact.media_type = media_type
                    artifact.sha256 = digest
                    artifact.object_key = object_key
                    artifact.expires_at = expires_at
                db.add(artifact)
            for stale in existing.values():
                stale_object_keys.append(stale.object_key)
                db.delete(stale)
            row.status = target_status
            if exit_code is not None:
                row.exit_code = exit_code
            row.archive_target_status = None
            row.archive_started_at = None
            row.archive_claim_token = None
            row.archive_claim_expires_at = None
            row.archive_failure_code = None
            row.artifact_archived_bytes = artifact_archived_bytes
            row.artifact_omitted_count = artifact_omitted_count
            row.workspace_retained = False
            row.quarantine_reason = None
            row.ended_at = row.ended_at or now
            row.updated_at = now
            db.add(row)
            record_audit_log(
                db,
                actor_user_id=actor_user_id or user_id,
                action="hermes_terminal.session.finish",
                entity_kind="hermes_terminal_session",
                entity_id=session_id,
                summary="Finished private Hermes terminal session",
                payload={
                    "mode": row.mode,
                    "status": row.status,
                    "target_status": target_status,
                    "exit_code": exit_code,
                    "archive_attempts": row.archive_attempts,
                    "artifact_archived_bytes": artifact_archived_bytes,
                    "artifact_omitted_count": artifact_omitted_count,
                },
            )
            db.commit()
    except (
        HermesTerminalBrokerError,
        MinioException,
        OSError,
        SQLAlchemyError,
        tarfile.TarError,
        ValueError,
    ):
        archive_failure = HERMES_TERMINAL_ARCHIVE_FAILURE

    if archive_failure is not None:
        if uploaded_keys:
            await asyncio.to_thread(_remove_uploaded_objects, uploaded_keys)
        now = utcnow_naive()
        with get_session_factory()() as db:
            row = db.scalar(
                select(HermesTerminalSession)
                .where(HermesTerminalSession.id == session_id)
                .with_for_update()
            )
            if row is None or row.archive_claim_token != claim_token:
                return False
            row.status = "archiving"
            if exit_code is not None:
                row.exit_code = exit_code
            row.archive_failure_code = archive_failure
            row.archive_claim_expires_at = now
            row.ended_at = row.ended_at or now
            row.updated_at = now
            db.add(row)
            record_audit_log(
                db,
                actor_user_id=actor_user_id or user_id,
                action="hermes_terminal.session.archive_failed",
                entity_kind="hermes_terminal_session",
                entity_id=session_id,
                summary="Hermes terminal archive attempt failed",
                payload={
                    "mode": row.mode,
                    "status": row.status,
                    "target_status": target_status,
                    "exit_code": exit_code,
                    "archive_failure": archive_failure,
                    "archive_attempts": row.archive_attempts,
                },
            )
            db.commit()
    elif stale_object_keys:
        await asyncio.to_thread(_remove_uploaded_objects, stale_object_keys)
    if archive_failure is None:
        await release_terminal_runtime(session_id)
    return archive_failure is None


def _adopt_terminal_runtime(session_id: str, broker_row) -> None:
    with get_session_factory()() as db:
        row = db.scalar(
            select(HermesTerminalSession)
            .where(HermesTerminalSession.id == session_id)
            .with_for_update()
        )
        if row is None or row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
            return
        now = utcnow_naive()
        row.runtime_handle = broker_row.runtime_handle
        row.broker_instance_id = broker_row.broker_instance_id
        if row.status == "starting" and broker_row.status == "running":
            row.status = "running"
            row.failure_code = None
            row.started_at = row.started_at or now
        elif (
            row.status == "archiving"
            and row.archive_target_status == "exited"
            and broker_row.status == "running"
        ):
            # Docker can report a brief exit while an operator restarts the
            # container. If that same runtime is running again, keep the live
            # terminal instead of retrying an archive that requires it stopped.
            row.status = "running"
            row.failure_code = None
            row.exit_code = None
            row.ended_at = None
            row.archive_target_status = None
            row.archive_attempts = 0
            row.archive_started_at = None
            row.archive_claim_token = None
            row.archive_claim_expires_at = None
            row.archive_failure_code = None
        row.updated_at = now
        db.add(row)
        db.commit()


async def fail_missing_terminal_runtime(
    session_id: str,
    *,
    actor_user_id: str | None,
) -> bool:
    with get_session_factory()() as db:
        row = db.scalar(
            select(HermesTerminalSession)
            .where(HermesTerminalSession.id == session_id)
            .with_for_update()
        )
        if row is None or row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
            return False
        now = utcnow_naive()
        retain_workspace = row.status != "starting"
        row.status = "failed"
        row.failure_code = "hermes_terminal.runtime_missing"
        row.archive_target_status = None
        row.archive_started_at = None
        row.archive_claim_token = None
        row.archive_claim_expires_at = None
        if retain_workspace:
            # A disappeared runner may leave its named workspace volume behind.
            # Keep the runtime identity in the known-resource set so orphan
            # reconciliation cannot erase user results before an operator can
            # inspect/recover the quarantined volume.
            row.workspace_retained = True
            row.quarantine_reason = "hermes_terminal.runtime_missing"
        row.ended_at = row.ended_at or now
        row.updated_at = now
        db.add(row)
        record_audit_log(
            db,
            actor_user_id=actor_user_id or row.user_id,
            action="hermes_terminal.session.runtime_missing",
            entity_kind="hermes_terminal_session",
            entity_id=session_id,
            summary="Closed a Hermes terminal session whose runtime was missing",
            payload={
                "mode": row.mode,
                "status": row.status,
                "workspace_retained": retain_workspace,
            },
        )
        db.commit()
    if not retain_workspace:
        await release_terminal_runtime(session_id, abandon_archive=True)
    return True


async def release_terminal_runtime(
    session_id: str,
    *,
    abandon_archive: bool = False,
) -> bool:
    try:
        await HermesTerminalBrokerClient().forget_session(session_id)
    except HermesTerminalBrokerError as error:
        if error.status_code != 404:
            return False
    with get_session_factory()() as db:
        row = db.scalar(
            select(HermesTerminalSession)
            .where(HermesTerminalSession.id == session_id)
            .with_for_update()
        )
        if row is None:
            return True
        row.runtime_handle = None
        row.broker_instance_id = None
        if abandon_archive:
            row.archive_target_status = None
            row.archive_started_at = None
            row.archive_claim_token = None
            row.archive_claim_expires_at = None
        db.add(row)
        db.commit()
    return True


async def reconcile_terminal_session_if_finished(
    row: HermesTerminalSession,
    *,
    missing_is_failure: bool = False,
) -> None:
    if row.status not in HERMES_TERMINAL_ACTIVE_STATUSES:
        return
    try:
        broker_row = await HermesTerminalBrokerClient().get_session(row.id)
    except HermesTerminalBrokerError as error:
        if error.status_code == 404 and missing_is_failure:
            await fail_missing_terminal_runtime(
                row.id,
                actor_user_id=row.user_id,
            )
        return
    if (
        row.status == "archiving"
        and row.archive_target_status != "exited"
        and broker_row.status in {"starting", "running"}
    ):
        # A manually stopped/failed runner can be restarted by Docker while an
        # archive is being recovered. Keep the requested terminal outcome and
        # stop the runner again before the expired archive lease is retried.
        try:
            await HermesTerminalBrokerClient().stop_session(row.id)
        except HermesTerminalBrokerError:
            return
        return
    if broker_row.status in {"starting", "running"}:
        await asyncio.to_thread(_adopt_terminal_runtime, row.id, broker_row)
        return
    if broker_row.status in {"exited", "failed"}:
        await finalize_terminal_session(
            row.id,
            target_status=(
                "terminated"
                if row.status == "stopping"
                else "exited"
                if broker_row.status == "exited"
                else "failed"
            ),
            exit_code=broker_row.exit_code,
            actor_user_id=row.user_id,
            failure_code=broker_row.failure_code,
        )
