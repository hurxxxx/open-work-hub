from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)
from open_work_hub_api.domains.hermes.client import HermesClientError, HermesRuntimeClient
from open_work_hub_api.domains.hermes.models import (
    HermesProfileBinding,
    HermesRunInput,
    HermesSessionBinding,
)
from open_work_hub_api.domains.hermes.repository import (
    TERMINAL_RUN_STATUSES,
    HermesDispatchRepository,
    HermesRunNotFoundError,
    HermesRunRepository,
)


class HermesExecutionConfigurationError(RuntimeError):
    pass


STATUS_POLL_SECONDS = 5.0


def hermes_run_access_allowed(db: Session, run: Any) -> bool:
    return can_use_app(
        db,
        app_id=run.owner_app_id,
        user_id=run.user_id,
    )


async def _stream_hermes_events(
    client: HermesRuntimeClient,
    *,
    profile_name: str,
    hermes_run_id: str,
    queue: asyncio.Queue[tuple[str, object]],
) -> None:
    try:
        async for event in client.iter_run_events(profile_name, hermes_run_id):
            await queue.put(("event", event))
    except Exception as error:
        await queue.put(("error", error))
    else:
        await queue.put(("closed", None))


async def execute_hermes_run(
    db: Session,
    *,
    run_id: str,
    runtime_base_url: str,
    api_key: str,
    request_timeout_seconds: float,
    lease_seconds: int,
    max_concurrent_runs: int = 10,
) -> str:
    repository = HermesRunRepository(db)
    claim_token = uuid4().hex
    claim = repository.claim_execution(
        run_id,
        claim_token=claim_token,
        lease_seconds=lease_seconds,
        max_concurrent_runs=max_concurrent_runs,
    )
    db.commit()
    if not claim.acquired:
        if claim.reason in {"capacity", "session_busy"}:
            HermesDispatchRepository(db).defer(run_id, reason=claim.reason)
            db.commit()
        return claim.reason or claim.status

    client = HermesRuntimeClient(
        base_url=runtime_base_url,
        api_key=api_key,
        timeout_seconds=request_timeout_seconds,
    )
    try:
        run = repository.get(run_id)
        if run is None:
            raise HermesRunNotFoundError(run_id)
        profile = db.get(HermesProfileBinding, run.profile_binding_id)
        if profile is None or (profile.status != "active" and run.status != "stopping"):
            raise HermesExecutionConfigurationError("Hermes profile is not active.")
        if run.status != "stopping" and not hermes_run_access_allowed(db, run):
            repository.mark_failure(
                run.id,
                claim_token=claim_token,
                code="hermes.access_revoked",
                message="Hermes access was revoked before execution.",
            )
            db.commit()
            return "failed"
        session = (
            db.get(HermesSessionBinding, run.session_binding_id)
            if run.session_binding_id is not None
            else None
        )

        if run.hermes_run_id is None:
            run_input = db.get(HermesRunInput, run.id)
            if run_input is None:
                raise HermesExecutionConfigurationError("Hermes run input is missing.")
            hermes_session_id = (
                session.hermes_session_id if session is not None else f"owh_workload_{run.id}"
            )
            accepted = await client.create_run(
                profile.profile_name,
                input_text=run_input.input_text,
                session_id=hermes_session_id,
                idempotency_key=run.id,
                instructions=run_input.instructions,
                conversation_history=run_input.conversation_history,
                runtime_options=run.runtime_options,
                **({"cancel_admission": True} if run.status == "stopping" else {}),
            )
            hermes_run_id = accepted.get("run_id")
            if not isinstance(hermes_run_id, str) or not hermes_run_id:
                raise HermesClientError(
                    operation="create_run",
                    status_code=202,
                    code="hermes.invalid_run_response",
                    message="Hermes accepted a run without returning a run ID.",
                )
            accepted_status = repository._normalize_status(str(accepted.get("status")))
            repository.attach_hermes_run(
                run.id,
                claim_token=claim_token,
                hermes_run_id=hermes_run_id,
                status="running" if accepted_status in TERMINAL_RUN_STATUSES else accepted_status,
            )
            repository.append_event(
                run.id,
                {
                    "event": "run.accepted",
                    **accepted,
                    "status": "running"
                    if accepted_status in TERMINAL_RUN_STATUSES
                    else accepted_status,
                },
                claim_token=claim_token,
            )
            db.delete(run_input)
            db.commit()
            # Cancellation can reserve a terminal native admission without
            # starting a model, or recover an already terminal remote run.
            if accepted_status in TERMINAL_RUN_STATUSES:
                # Admission responses contain only identity/status. Fetch the
                # durable result before projecting output, usage, or errors.
                status_payload = await client.get_run(profile.profile_name, hermes_run_id)
                repository.apply_status(run_id, status_payload, claim_token=claim_token)
                db.commit()
                if run.status in TERMINAL_RUN_STATUSES:
                    return run.status
        else:
            hermes_run_id = run.hermes_run_id

            # Hermes exposes durable pollable status, but its live SSE queue
            # is intentionally single-consumer and is removed after a client
            # disconnects. Recover terminal/approval state before attempting
            # a new live subscription after a worker retry.
            status_payload = await client.get_run(profile.profile_name, hermes_run_id)
            repository.apply_status(
                run_id,
                status_payload,
                claim_token=claim_token,
            )
            db.commit()
            current = repository.get(run_id)
            if current is not None and current.status in TERMINAL_RUN_STATUSES:
                return current.status

        stop_relayed = False
        current = repository.get(run_id)
        if current is not None and current.status == "stopping":
            stop_payload = await client.stop_run(profile.profile_name, hermes_run_id)
            stop_status = repository._normalize_status(str(stop_payload.get("status")))
            terminal_stop = stop_status in TERMINAL_RUN_STATUSES
            if terminal_stop:
                status_payload = await client.get_run(profile.profile_name, hermes_run_id)
                repository.apply_status(run_id, status_payload, claim_token=claim_token)
            else:
                repository.append_event(
                    run_id,
                    {**stop_payload, "event": "run.stop_requested", "status": "stopping"},
                    claim_token=claim_token,
                )
            db.commit()
            if current.status in TERMINAL_RUN_STATUSES:
                return current.status
            stop_relayed = True

        event_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue(maxsize=200)
        stream_task = asyncio.create_task(
            _stream_hermes_events(
                client,
                profile_name=profile.profile_name,
                hermes_run_id=hermes_run_id,
                queue=event_queue,
            )
        )
        stream_error: HermesClientError | None = None
        next_status_poll = time.monotonic() + STATUS_POLL_SECONDS

        async def preserve_pending_events(item_kind: str, item: object) -> None:
            # Freeze the producer before draining its bounded queue. Durable
            # status supplies the final event after all available live evidence.
            if not stream_task.done():
                stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await stream_task
            pending = [(item_kind, item)]
            while not event_queue.empty():
                pending.append(event_queue.get_nowait())
            db.expire_all()
            latest = repository.get(run_id, for_update=True)
            if latest is None:
                raise HermesRunNotFoundError(run_id)
            pending_claim = None if latest.status in TERMINAL_RUN_STATUSES else claim_token
            for kind, event in pending:
                if (
                    kind == "event" and isinstance(event, dict)
                    and event.get("event") not in {f"run.{s}" for s in TERMINAL_RUN_STATUSES}
                ):
                    # A maintenance poll may already have released the claim;
                    # the repository retains terminal state while appending.
                    repository.append_event(run_id, event, claim_token=pending_claim)
            db.commit()

        try:
            while True:
                try:
                    item_kind, item = await asyncio.wait_for(event_queue.get(), timeout=2.0)
                except TimeoutError:
                    item_kind, item = "tick", None

                db.expire_all()
                current = repository.get(run_id)
                if current is None:
                    raise HermesRunNotFoundError(run_id)
                if current.status in TERMINAL_RUN_STATUSES:
                    await preserve_pending_events(item_kind, item)
                    break

                # Native SSE is a live, single-consumer queue, not the durable
                # source of truth. A lost final event must not hold the worker
                # and conversation open while keepalives continue to arrive.
                if time.monotonic() >= next_status_poll:
                    try:
                        payload = await client.get_run(profile.profile_name, hermes_run_id)
                    except HermesClientError:
                        # This poll supplements the live stream. Preserve the
                        # dequeued event and retry after the normal interval.
                        pass
                    else:
                        if repository._normalize_status(str(payload.get("status"))) in TERMINAL_RUN_STATUSES:
                            await preserve_pending_events(item_kind, item)
                            if current.status in TERMINAL_RUN_STATUSES:
                                break
                        if (
                            repository._normalize_status(str(payload.get("status")))
                            in TERMINAL_RUN_STATUSES
                            or payload.get("last_event") == "approval.request"
                            and current.pending_approval is None
                        ):
                            repository.apply_status(run_id, payload, claim_token=claim_token)
                        db.commit()
                    next_status_poll = time.monotonic() + STATUS_POLL_SECONDS
                    if current.status in TERMINAL_RUN_STATUSES:
                        break

                access_allowed = hermes_run_access_allowed(db, current)
                if not access_allowed and current.status != "stopping":
                    repository.append_event(
                        run_id,
                        {
                            "event": "run.stop_requested",
                            "status": "stopping",
                            "reason": "access_revoked",
                        },
                        claim_token=claim_token,
                    )
                    db.commit()
                    current = repository.get(run_id)

                if current is not None and current.status == "stopping" and not stop_relayed:
                    try:
                        stop_payload = await client.stop_run(
                            profile.profile_name,
                            hermes_run_id,
                        )
                    except HermesClientError:
                        # Keep the durable stop request and retry it on the next
                        # control tick while the event stream remains attached.
                        pass
                    else:
                        repository.append_event(
                            run_id,
                            {
                                **stop_payload,
                                "event": "run.stop_requested",
                                "status": "stopping",
                            },
                            claim_token=claim_token,
                        )
                        db.commit()
                        stop_relayed = True

                if item_kind == "event":
                    if not isinstance(item, dict):
                        continue
                    repository.append_event(run_id, item, claim_token=claim_token)
                    db.commit()
                    continue
                if item_kind == "error":
                    if isinstance(item, HermesClientError):
                        stream_error = item
                    else:
                        raise (
                            item
                            if isinstance(item, Exception)
                            else RuntimeError("Hermes event stream failed.")
                        )
                    break
                if item_kind == "closed":
                    break
        finally:
            if not stream_task.done():
                stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await stream_task

        if stream_error is not None:
            error = stream_error
            if error.status_code != 404:
                raise error
            # The prior subscriber may have consumed and closed Hermes' live
            # queue. Poll once now and let Celery retry this lightweight
            # recovery loop until the durable status becomes terminal.
            status_payload = await client.get_run(profile.profile_name, hermes_run_id)
            repository.apply_status(
                run_id,
                status_payload,
                claim_token=claim_token,
            )
            db.commit()
            current = repository.get(run_id)
            if current is not None and current.status in TERMINAL_RUN_STATUSES:
                return current.status
            repository.release_execution_claim(
                run_id,
                claim_token=claim_token,
                status=current.status if current is not None else "running",
            )
            db.commit()
            return "incomplete"

        current = repository.get(run_id)
        if current is None:
            raise HermesRunNotFoundError(run_id)
        if current.status in TERMINAL_RUN_STATUSES:
            return current.status

        status_payload = await client.get_run(profile.profile_name, hermes_run_id)
        repository.apply_status(
            run_id,
            status_payload,
            claim_token=claim_token,
        )
        db.commit()
        current = repository.get(run_id)
        if current is not None and current.status in TERMINAL_RUN_STATUSES:
            return current.status
        repository.release_execution_claim(
            run_id,
            claim_token=claim_token,
            status=current.status if current is not None else "running",
        )
        db.commit()
        return "incomplete"
    except (Exception, asyncio.CancelledError):
        db.rollback()
        current = repository.get(run_id)
        if current is not None and current.execution_claim_token == claim_token:
            repository.release_execution_claim(
                run_id,
                claim_token=claim_token,
                status=current.status,
            )
            db.commit()
        raise


def mark_hermes_run_terminal_failure(
    db: Session,
    *,
    run_id: str,
    error_code: str,
    error_message: str,
) -> None:
    repository = HermesRunRepository(db)
    claim_token = uuid4().hex
    claim = repository.claim_execution(
        run_id,
        claim_token=claim_token,
        lease_seconds=60,
    )
    if not claim.acquired:
        db.commit()
        return
    if claim.status == "stopping":
        # An exhausted worker retry is not evidence that native work stopped.
        # Keep compensation on the durable outbox, with its normal backoff.
        repository.release_execution_claim(run_id, claim_token=claim_token, status="stopping")
        HermesDispatchRepository(db).defer(run_id, reason="stop_unconfirmed")
        db.commit()
        return
    repository.mark_failure(
        run_id,
        claim_token=claim_token,
        code=error_code,
        message=error_message,
    )
    db.commit()
