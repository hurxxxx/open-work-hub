from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from open_work_hub_api.domains.hermes.client import HermesClientError, HermesRuntimeClient
from open_work_hub_api.domains.hermes.models import (
    HermesProfileBinding,
    HermesRunInput,
    HermesSessionBinding,
)
from open_work_hub_api.domains.hermes.repository import (
    TERMINAL_RUN_STATUSES,
    HermesRunNotFoundError,
    HermesRunRepository,
)


class HermesExecutionConfigurationError(RuntimeError):
    pass


async def execute_hermes_run(
    db: Session,
    *,
    run_id: str,
    runtime_base_url: str,
    api_key: str,
    request_timeout_seconds: float,
    lease_seconds: int,
) -> str:
    repository = HermesRunRepository(db)
    claim_token = uuid4().hex
    claim = repository.claim_execution(
        run_id,
        claim_token=claim_token,
        lease_seconds=lease_seconds,
    )
    db.commit()
    if not claim.acquired:
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
        if profile is None or profile.status != "active":
            raise HermesExecutionConfigurationError("Hermes profile is not active.")
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
            )
            hermes_run_id = accepted.get("run_id")
            if not isinstance(hermes_run_id, str) or not hermes_run_id:
                raise HermesClientError(
                    operation="create_run",
                    status_code=202,
                    code="hermes.invalid_run_response",
                    message="Hermes accepted a run without returning a run ID.",
                )
            repository.attach_hermes_run(
                run.id,
                claim_token=claim_token,
                hermes_run_id=hermes_run_id,
                status=str(accepted.get("status") or "queued"),
            )
            repository.append_event(
                run.id,
                {"event": "run.accepted", **accepted},
                claim_token=claim_token,
            )
            db.delete(run_input)
            db.commit()
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

        current = repository.get(run_id)
        if current is not None and current.status == "stopping":
            stop_payload = await client.stop_run(profile.profile_name, hermes_run_id)
            repository.append_event(
                run_id,
                {**stop_payload, "event": "run.stop_requested", "status": "stopping"},
                claim_token=claim_token,
            )
            db.commit()

        try:
            async for event in client.iter_run_events(profile.profile_name, hermes_run_id):
                current = repository.get(run_id)
                if current is None:
                    raise HermesRunNotFoundError(run_id)
                if current.status in TERMINAL_RUN_STATUSES:
                    break
                repository.append_event(run_id, event, claim_token=claim_token)
                db.commit()
        except HermesClientError as error:
            if error.status_code != 404:
                raise
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
    except Exception:
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
    repository.mark_failure(
        run_id,
        claim_token=claim_token,
        code=error_code,
        message=error_message,
    )
    db.commit()
