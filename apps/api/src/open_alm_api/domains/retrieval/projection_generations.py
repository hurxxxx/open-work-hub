from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.retrieval.models import (
    RetrievalProjectionBackend,
    RetrievalProjectionEvent,
    RetrievalProjectionGeneration,
    RetrievalProjectionGenerationState,
    RetrievalProjectionValidationState,
)


_GENERATION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class RetrievalProjectionGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RetrievalProjectionGenerationCutoverTarget:
    """One external alias operation in a paired cutover plan."""

    backend: str
    generation_id: str
    alias_name: str
    physical_name: str
    previous_generation_id: str | None
    previous_physical_name: str | None


@dataclass(frozen=True, slots=True)
class RetrievalProjectionGenerationPairCutoverPlan:
    """Immutable hand-off between DB prepare and external alias operations."""

    generation_key: str
    opensearch: RetrievalProjectionGenerationCutoverTarget
    qdrant: RetrievalProjectionGenerationCutoverTarget


@dataclass(frozen=True, slots=True)
class RetrievalProjectionGenerationPair:
    generation_key: str
    opensearch: RetrievalProjectionGeneration
    qdrant: RetrievalProjectionGeneration


_PAIR_SCHEMA_VERSIONS = {
    RetrievalProjectionBackend.OPENSEARCH.value: 3,
    RetrievalProjectionBackend.QDRANT.value: 1,
}


def create_projection_generation(
    db: Session,
    *,
    backend: RetrievalProjectionBackend | str,
    generation_key: str,
    physical_name: str,
    alias_name: str,
    schema_version: int,
    baseline_event_sequence: int | None = None,
) -> RetrievalProjectionGeneration:
    """Capture a baseline watermark while registering an isolated generation.

    Generic callers retain the global event watermark default.  A source-scoped
    projection may provide its own watermark, expressed in the same global event
    sequence, as long as it does not claim an event that has not been persisted.
    """

    normalized_backend = _backend_value(backend)
    normalized_key = _generation_key(generation_key)
    normalized_physical_name = _required_name(physical_name, field="physical_name")
    normalized_alias_name = _required_name(alias_name, field="alias_name")
    if schema_version < 1:
        raise ValueError("schema_version must be greater than zero")
    _lock_backend_control_plane(db, normalized_backend)
    watermark = _validated_required_event_sequence(
        db,
        required_event_sequence=baseline_event_sequence,
    )
    generation = RetrievalProjectionGeneration(
        backend=normalized_backend,
        generation_key=normalized_key,
        physical_name=normalized_physical_name,
        alias_name=normalized_alias_name,
        schema_version=schema_version,
        state=RetrievalProjectionGenerationState.PREPARING.value,
        baseline_event_sequence=watermark,
        replay_event_sequence=watermark,
        validation_state=RetrievalProjectionValidationState.PENDING.value,
    )
    db.add(generation)
    db.flush()
    return generation


def mark_generation_baselining(
    db: Session,
    *,
    generation_id: str,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(generation, RetrievalProjectionGenerationState.PREPARING)
    generation.state = RetrievalProjectionGenerationState.BASELINING.value
    _touch(generation)
    db.flush()
    return generation


def mark_generation_replaying(
    db: Session,
    *,
    generation_id: str,
    expected_projection_count: int,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(generation, RetrievalProjectionGenerationState.BASELINING)
    if expected_projection_count < 0:
        raise ValueError("expected_projection_count must not be negative")
    generation.expected_projection_count = expected_projection_count
    generation.state = RetrievalProjectionGenerationState.REPLAYING.value
    _touch(generation)
    db.flush()
    return generation


def advance_generation_replay_checkpoint(
    db: Session,
    *,
    generation_id: str,
    event_sequence: int,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(
        generation,
        RetrievalProjectionGenerationState.REPLAYING,
        RetrievalProjectionGenerationState.VALIDATING,
    )
    if event_sequence < generation.replay_event_sequence:
        raise RetrievalProjectionGenerationError("replay checkpoint cannot move backwards")
    current_watermark = _current_event_watermark(db)
    if event_sequence > current_watermark:
        raise RetrievalProjectionGenerationError(
            "replay checkpoint cannot exceed the persisted event watermark"
        )
    generation.replay_event_sequence = event_sequence
    _touch(generation)
    db.flush()
    return generation


def mark_generation_validating(
    db: Session,
    *,
    generation_id: str,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(generation, RetrievalProjectionGenerationState.REPLAYING)
    generation.state = RetrievalProjectionGenerationState.VALIDATING.value
    generation.validation_state = RetrievalProjectionValidationState.PENDING.value
    generation.validation_details = None
    _touch(generation)
    db.flush()
    return generation


def record_generation_validation(
    db: Session,
    *,
    generation_id: str,
    passed: bool,
    details: dict[str, Any],
    content_checksum: str | None = None,
    config_checksum: str | None = None,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(generation, RetrievalProjectionGenerationState.VALIDATING)
    normalized_details = dict(details)
    if (
        "release_cohort" in normalized_details
        and str(normalized_details["release_cohort"] or "").strip() != generation.generation_key
    ):
        raise RetrievalProjectionGenerationError(
            "generation validation release cohort must match generation_key"
        )
    normalized_details["release_cohort"] = generation.generation_key
    generation.validation_details = normalized_details
    generation.content_checksum = _optional_checksum(content_checksum)
    generation.config_checksum = _optional_checksum(config_checksum)
    generation.validated_at = utcnow_naive()
    if passed:
        generation.validation_state = RetrievalProjectionValidationState.PASSED.value
        generation.state = RetrievalProjectionGenerationState.READY.value
        generation.failure_reason = None
    else:
        generation.validation_state = RetrievalProjectionValidationState.FAILED.value
        generation.state = RetrievalProjectionGenerationState.FAILED.value
        generation.failure_reason = "generation_validation_failed"
    _touch(generation)
    db.flush()
    return generation


def begin_generation_cutover(
    db: Session,
    *,
    generation_id: str,
    writes_quiesced: bool,
) -> RetrievalProjectionGeneration:
    """Fence the DB side before the caller performs the external alias switch."""

    if not writes_quiesced:
        raise RetrievalProjectionGenerationError(
            "generation cutover requires writers to be quiesced until online replay exists"
        )
    generation = _locked_generation(db, generation_id)
    _lock_backend_control_plane(db, generation.backend)
    _require_state(generation, RetrievalProjectionGenerationState.READY)
    if generation.validation_state != RetrievalProjectionValidationState.PASSED.value:
        raise RetrievalProjectionGenerationError("generation must pass validation before cutover")
    current_watermark = _current_event_watermark(db)
    if generation.replay_event_sequence < current_watermark:
        raise RetrievalProjectionGenerationError(
            "generation replay checkpoint is behind the current event watermark"
        )
    previous = db.scalar(
        select(RetrievalProjectionGeneration)
        .where(
            RetrievalProjectionGeneration.backend == generation.backend,
            RetrievalProjectionGeneration.state == RetrievalProjectionGenerationState.ACTIVE.value,
        )
        .with_for_update()
    )
    generation.previous_generation_id = previous.id if previous is not None else None
    generation.state = RetrievalProjectionGenerationState.ACTIVATING.value
    _touch(generation)
    db.flush()
    return generation


def complete_generation_cutover(
    db: Session,
    *,
    generation_id: str,
    rollback_expires_at: datetime,
) -> RetrievalProjectionGeneration:
    """Record successful alias activation after the external operation returns."""

    generation = _locked_generation(db, generation_id)
    _lock_backend_control_plane(db, generation.backend)
    _require_state(generation, RetrievalProjectionGenerationState.ACTIVATING)
    previous = None
    if generation.previous_generation_id is not None:
        previous = _locked_generation(db, generation.previous_generation_id)
        _require_state(previous, RetrievalProjectionGenerationState.ACTIVE)
        previous.state = RetrievalProjectionGenerationState.ROLLBACK.value
        previous.rollback_expires_at = rollback_expires_at
        _touch(previous)
        # Release the partial unique active-backend slot before promoting the
        # new row; SQLAlchemy does not guarantee UPDATE ordering in one flush.
        db.flush([previous])
    generation.state = RetrievalProjectionGenerationState.ACTIVE.value
    generation.activated_at = utcnow_naive()
    generation.rollback_expires_at = rollback_expires_at
    generation.failure_reason = None
    _touch(generation)
    db.flush()
    return generation


def mark_generation_cutover_failed(
    db: Session,
    *,
    generation_id: str,
    reason: str,
    alias_may_have_moved: bool,
) -> RetrievalProjectionGeneration:
    generation = _locked_generation(db, generation_id)
    _require_state(generation, RetrievalProjectionGenerationState.ACTIVATING)
    generation.state = (
        RetrievalProjectionGenerationState.COMPENSATION_REQUIRED.value
        if alias_may_have_moved
        else RetrievalProjectionGenerationState.FAILED.value
    )
    generation.failure_reason = _required_name(reason, field="reason", max_length=2000)
    _touch(generation)
    db.flush()
    return generation


def prepare_generation_pair_cutover(
    db: Session,
    *,
    opensearch_generation_id: str,
    qdrant_generation_id: str,
    writes_quiesced: bool,
    required_event_sequence: int | None = None,
) -> RetrievalProjectionGenerationPairCutoverPlan:
    """Prepare an OpenSearch+Qdrant release cohort for external alias switching.

    The caller owns the surrounding transaction and must commit it before changing
    either external alias.  After both aliases are switched, call
    :func:`complete_generation_pair_cutover` in a new transaction.  If either
    external operation fails, restore both aliases to the previous physical names
    in this plan and call :func:`compensate_generation_pair_cutover` instead.

    No row is mutated until the complete pair and current active pair have passed
    every fence, so a validation error fails closed without a partial DB state.
    """

    if not writes_quiesced:
        raise RetrievalProjectionGenerationError(
            "generation pair cutover requires writers to be quiesced until online replay exists"
        )
    _lock_pair_control_plane(db)
    _require_no_conflicting_pair_control_plane_rows(db)
    targets = _locked_pair(
        db,
        opensearch_generation_id=opensearch_generation_id,
        qdrant_generation_id=qdrant_generation_id,
    )
    _validate_release_pair(
        targets,
        required_state=RetrievalProjectionGenerationState.READY,
    )
    _require_pair_replayed_to_watermark(
        db,
        targets,
        required_event_sequence=required_event_sequence,
    )

    active = _locked_active_pair(db)
    _validate_optional_previous_pair(active, targets=targets)
    previous_by_backend = (
        {}
        if active is None
        else {
            active.opensearch.backend: active.opensearch,
            active.qdrant.backend: active.qdrant,
        }
    )
    for generation in (targets.opensearch, targets.qdrant):
        previous = previous_by_backend.get(generation.backend)
        generation.previous_generation_id = previous.id if previous is not None else None
        generation.state = RetrievalProjectionGenerationState.ACTIVATING.value
        _touch(generation)
    db.flush()
    return _pair_cutover_plan(targets, active)


def complete_generation_pair_cutover(
    db: Session,
    *,
    plan: RetrievalProjectionGenerationPairCutoverPlan,
    rollback_expires_at: datetime,
    required_event_sequence: int | None = None,
) -> RetrievalProjectionGenerationPair:
    """Complete both DB promotions after both external aliases switched.

    This function does not commit.  The two previous rows are moved to rollback
    and the two prepared rows are promoted to active in the caller's single DB
    transaction.  A stale or partial plan is rejected before any state changes.
    """

    _lock_pair_control_plane(db)
    _require_no_conflicting_pair_control_plane_rows(
        db,
        allowed_activating_ids={
            plan.opensearch.generation_id,
            plan.qdrant.generation_id,
        },
    )
    targets = _locked_pair(
        db,
        opensearch_generation_id=plan.opensearch.generation_id,
        qdrant_generation_id=plan.qdrant.generation_id,
    )
    _validate_release_pair(
        targets,
        required_state=RetrievalProjectionGenerationState.ACTIVATING,
    )
    _require_plan_matches_pair(plan, targets)
    _require_pair_replayed_to_watermark(
        db,
        targets,
        required_event_sequence=required_event_sequence,
    )
    previous = _locked_plan_previous_pair(db, plan=plan, targets=targets)

    if previous is not None:
        for generation in (previous.opensearch, previous.qdrant):
            generation.state = RetrievalProjectionGenerationState.ROLLBACK.value
            generation.rollback_expires_at = rollback_expires_at
            _touch(generation)
        # Free both partial unique active-backend slots before promotion.  This
        # remains part of the caller's same uncommitted transaction.
        db.flush([previous.opensearch, previous.qdrant])

    activated_at = utcnow_naive()
    for generation in (targets.opensearch, targets.qdrant):
        generation.state = RetrievalProjectionGenerationState.ACTIVE.value
        generation.activated_at = activated_at
        generation.rollback_expires_at = rollback_expires_at
        generation.failure_reason = None
        _touch(generation)
    db.flush()
    return targets


def compensate_generation_pair_cutover(
    db: Session,
    *,
    plan: RetrievalProjectionGenerationPairCutoverPlan,
    reason: str,
    aliases_restored: bool,
) -> RetrievalProjectionGenerationPair:
    """Close both prepared rows after an external alias failure.

    ``aliases_restored`` may be true only after the caller confirms that both
    aliases point at their ``previous_physical_name`` values from ``plan`` (or
    are absent when the plan has no previous pair).  Unconfirmed external state
    puts both rows into ``compensation_required`` so operators cannot mistake a
    partially switched release for a retryable failed generation.
    """

    _lock_pair_control_plane(db)
    targets = _locked_pair(
        db,
        opensearch_generation_id=plan.opensearch.generation_id,
        qdrant_generation_id=plan.qdrant.generation_id,
    )
    target_ids = {targets.opensearch.id, targets.qdrant.id}
    states = {targets.opensearch.state, targets.qdrant.state}
    allowed_states = {
        RetrievalProjectionGenerationState.ACTIVATING.value,
        RetrievalProjectionGenerationState.COMPENSATION_REQUIRED.value,
    }
    if len(states) != 1 or not states.issubset(allowed_states):
        raise RetrievalProjectionGenerationError(
            "generation pair compensation requires both targets in the same unresolved state"
        )
    current_state = RetrievalProjectionGenerationState(next(iter(states)))
    _require_no_conflicting_pair_control_plane_rows(
        db,
        allowed_activating_ids=(
            target_ids if current_state is RetrievalProjectionGenerationState.ACTIVATING else set()
        ),
        allowed_compensation_ids=(
            target_ids
            if current_state is RetrievalProjectionGenerationState.COMPENSATION_REQUIRED
            else set()
        ),
    )
    _validate_release_pair(
        targets,
        required_state=current_state,
    )
    _require_plan_matches_pair(plan, targets)
    _locked_plan_previous_pair(db, plan=plan, targets=targets)
    state = (
        RetrievalProjectionGenerationState.FAILED.value
        if aliases_restored
        else RetrievalProjectionGenerationState.COMPENSATION_REQUIRED.value
    )
    normalized_reason = _required_name(reason, field="reason", max_length=2000)
    for generation in (targets.opensearch, targets.qdrant):
        generation.state = state
        generation.failure_reason = normalized_reason
        _touch(generation)
    db.flush()
    return targets


def _locked_pair(
    db: Session,
    *,
    opensearch_generation_id: str,
    qdrant_generation_id: str,
) -> RetrievalProjectionGenerationPair:
    requested_ids = {opensearch_generation_id, qdrant_generation_id}
    rows = tuple(
        db.scalars(
            select(RetrievalProjectionGeneration)
            .where(RetrievalProjectionGeneration.id.in_(requested_ids))
            .with_for_update()
        ).all()
    )
    if len(requested_ids) != 2 or len(rows) != 2:
        raise RetrievalProjectionGenerationError(
            "generation pair must contain exactly one OpenSearch and one Qdrant generation"
        )
    by_backend = {generation.backend: generation for generation in rows}
    if set(by_backend) != set(_PAIR_SCHEMA_VERSIONS) or len(by_backend) != 2:
        raise RetrievalProjectionGenerationError(
            "generation pair must contain exactly one OpenSearch and one Qdrant generation"
        )
    opensearch = by_backend[RetrievalProjectionBackend.OPENSEARCH.value]
    qdrant = by_backend[RetrievalProjectionBackend.QDRANT.value]
    if opensearch.id != opensearch_generation_id or qdrant.id != qdrant_generation_id:
        raise RetrievalProjectionGenerationError(
            "generation pair IDs do not match their declared backends"
        )
    return RetrievalProjectionGenerationPair(
        generation_key=opensearch.generation_key,
        opensearch=opensearch,
        qdrant=qdrant,
    )


def _validate_release_pair(
    pair: RetrievalProjectionGenerationPair,
    *,
    required_state: RetrievalProjectionGenerationState,
) -> None:
    generations = (pair.opensearch, pair.qdrant)
    keys = {generation.generation_key for generation in generations}
    if len(keys) != 1:
        raise RetrievalProjectionGenerationError(
            "generation pair must share the same generation_key release cohort"
        )
    pair_key = next(iter(keys))
    for generation in generations:
        _require_state(generation, required_state)
        expected_schema = _PAIR_SCHEMA_VERSIONS[generation.backend]
        if generation.schema_version != expected_schema:
            raise RetrievalProjectionGenerationError(
                f"{generation.backend} generation schema_version must be {expected_schema}"
            )
        if generation.validation_state != RetrievalProjectionValidationState.PASSED.value:
            raise RetrievalProjectionGenerationError(
                "generation pair must pass validation before cutover"
            )
        if generation.validated_at is None:
            raise RetrievalProjectionGenerationError(
                "generation pair must have a persisted validation timestamp before cutover"
            )
        details = generation.validation_details
        cohort = details.get("release_cohort") if isinstance(details, dict) else None
        if cohort != pair_key:
            raise RetrievalProjectionGenerationError(
                "generation pair validation release cohort must match generation_key"
            )


def _locked_active_pair(db: Session) -> RetrievalProjectionGenerationPair | None:
    rows = tuple(
        db.scalars(
            select(RetrievalProjectionGeneration)
            .where(
                RetrievalProjectionGeneration.backend.in_(tuple(_PAIR_SCHEMA_VERSIONS)),
                RetrievalProjectionGeneration.state
                == RetrievalProjectionGenerationState.ACTIVE.value,
            )
            .with_for_update()
        ).all()
    )
    if not rows:
        return None
    if len(rows) != 2:
        raise RetrievalProjectionGenerationError(
            "active generation pair is partial or contains multiple backend rows"
        )
    by_backend = {generation.backend: generation for generation in rows}
    if set(by_backend) != set(_PAIR_SCHEMA_VERSIONS) or len(by_backend) != 2:
        raise RetrievalProjectionGenerationError(
            "active generation pair is partial or contains multiple backend rows"
        )
    return RetrievalProjectionGenerationPair(
        generation_key=by_backend[RetrievalProjectionBackend.OPENSEARCH.value].generation_key,
        opensearch=by_backend[RetrievalProjectionBackend.OPENSEARCH.value],
        qdrant=by_backend[RetrievalProjectionBackend.QDRANT.value],
    )


def _require_pair_replayed_to_watermark(
    db: Session,
    pair: RetrievalProjectionGenerationPair,
    *,
    required_event_sequence: int | None = None,
) -> None:
    watermark = _validated_required_event_sequence(
        db,
        required_event_sequence=required_event_sequence,
    )
    for generation in (pair.opensearch, pair.qdrant):
        if required_event_sequence is None and generation.replay_event_sequence < watermark:
            raise RetrievalProjectionGenerationError(
                "generation pair replay checkpoint is behind the current event watermark"
            )
        if required_event_sequence is not None and generation.replay_event_sequence != watermark:
            raise RetrievalProjectionGenerationError(
                "generation pair replay checkpoint does not match the required event watermark"
            )


def _validate_optional_previous_pair(
    previous: RetrievalProjectionGenerationPair | None,
    *,
    targets: RetrievalProjectionGenerationPair,
) -> None:
    if previous is None:
        return
    _validate_release_pair(
        previous,
        required_state=RetrievalProjectionGenerationState.ACTIVE,
    )
    for old, new in (
        (previous.opensearch, targets.opensearch),
        (previous.qdrant, targets.qdrant),
    ):
        if old.alias_name != new.alias_name:
            raise RetrievalProjectionGenerationError(
                "generation pair aliases must match the current active pair"
            )


def _pair_cutover_plan(
    targets: RetrievalProjectionGenerationPair,
    previous: RetrievalProjectionGenerationPair | None,
) -> RetrievalProjectionGenerationPairCutoverPlan:
    previous_by_backend = (
        {}
        if previous is None
        else {
            previous.opensearch.backend: previous.opensearch,
            previous.qdrant.backend: previous.qdrant,
        }
    )

    def _target(
        generation: RetrievalProjectionGeneration,
    ) -> RetrievalProjectionGenerationCutoverTarget:
        old = previous_by_backend.get(generation.backend)
        return RetrievalProjectionGenerationCutoverTarget(
            backend=generation.backend,
            generation_id=generation.id,
            alias_name=generation.alias_name,
            physical_name=generation.physical_name,
            previous_generation_id=old.id if old is not None else None,
            previous_physical_name=old.physical_name if old is not None else None,
        )

    return RetrievalProjectionGenerationPairCutoverPlan(
        generation_key=targets.generation_key,
        opensearch=_target(targets.opensearch),
        qdrant=_target(targets.qdrant),
    )


def _require_plan_matches_pair(
    plan: RetrievalProjectionGenerationPairCutoverPlan,
    targets: RetrievalProjectionGenerationPair,
) -> None:
    if plan.generation_key != targets.generation_key:
        raise RetrievalProjectionGenerationError("generation pair cutover plan is stale")
    for planned, generation in (
        (plan.opensearch, targets.opensearch),
        (plan.qdrant, targets.qdrant),
    ):
        if (
            planned.backend != generation.backend
            or planned.generation_id != generation.id
            or planned.alias_name != generation.alias_name
            or planned.physical_name != generation.physical_name
            or planned.previous_generation_id != generation.previous_generation_id
        ):
            raise RetrievalProjectionGenerationError("generation pair cutover plan is stale")


def _locked_plan_previous_pair(
    db: Session,
    *,
    plan: RetrievalProjectionGenerationPairCutoverPlan,
    targets: RetrievalProjectionGenerationPair,
) -> RetrievalProjectionGenerationPair | None:
    previous_ids = {
        plan.opensearch.previous_generation_id,
        plan.qdrant.previous_generation_id,
    }
    if previous_ids == {None}:
        if (
            plan.opensearch.previous_physical_name is not None
            or plan.qdrant.previous_physical_name is not None
        ):
            raise RetrievalProjectionGenerationError("generation pair cutover plan is stale")
        if _locked_active_pair(db) is not None:
            raise RetrievalProjectionGenerationError(
                "generation pair cutover plan does not match the current active pair"
            )
        return None
    if None in previous_ids or len(previous_ids) != 2:
        raise RetrievalProjectionGenerationError(
            "generation pair cutover plan contains a partial previous pair"
        )
    previous = _locked_pair(
        db,
        opensearch_generation_id=str(plan.opensearch.previous_generation_id),
        qdrant_generation_id=str(plan.qdrant.previous_generation_id),
    )
    _validate_optional_previous_pair(previous, targets=targets)
    if (
        plan.opensearch.previous_physical_name != previous.opensearch.physical_name
        or plan.qdrant.previous_physical_name != previous.qdrant.physical_name
    ):
        raise RetrievalProjectionGenerationError("generation pair cutover plan is stale")
    active = _locked_active_pair(db)
    if active is None or {
        active.opensearch.id,
        active.qdrant.id,
    } != {
        previous.opensearch.id,
        previous.qdrant.id,
    }:
        raise RetrievalProjectionGenerationError(
            "generation pair cutover plan does not match the current active pair"
        )
    return previous


def _lock_pair_control_plane(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, CAST(0 AS bigint)))"),
            {"identity": "retrieval-projection-generation-pair"},
        )
    for backend in sorted(_PAIR_SCHEMA_VERSIONS):
        _lock_backend_control_plane(db, backend)


def _require_no_conflicting_pair_control_plane_rows(
    db: Session,
    *,
    allowed_activating_ids: set[str] | None = None,
    allowed_compensation_ids: set[str] | None = None,
) -> None:
    allowed_activating = allowed_activating_ids or set()
    allowed_compensation = allowed_compensation_ids or set()
    rows = tuple(
        db.scalars(
            select(RetrievalProjectionGeneration)
            .where(
                RetrievalProjectionGeneration.backend.in_(tuple(_PAIR_SCHEMA_VERSIONS)),
                RetrievalProjectionGeneration.state.in_(
                    (
                        RetrievalProjectionGenerationState.ACTIVATING.value,
                        RetrievalProjectionGenerationState.COMPENSATION_REQUIRED.value,
                    )
                ),
            )
            .with_for_update()
        ).all()
    )
    activating_ids = {
        generation.id
        for generation in rows
        if generation.state == RetrievalProjectionGenerationState.ACTIVATING.value
    }
    compensation_ids = {
        generation.id
        for generation in rows
        if generation.state == RetrievalProjectionGenerationState.COMPENSATION_REQUIRED.value
    }
    if activating_ids != allowed_activating or compensation_ids != allowed_compensation:
        raise RetrievalProjectionGenerationError(
            "another generation cutover is already in progress or requires compensation"
        )


def _locked_generation(db: Session, generation_id: str) -> RetrievalProjectionGeneration:
    generation = db.scalar(
        select(RetrievalProjectionGeneration)
        .where(RetrievalProjectionGeneration.id == generation_id)
        .with_for_update()
    )
    if generation is None:
        raise RetrievalProjectionGenerationError(
            f"retrieval projection generation is missing: {generation_id}"
        )
    return generation


def _require_state(
    generation: RetrievalProjectionGeneration,
    *states: RetrievalProjectionGenerationState,
) -> None:
    allowed = {state.value for state in states}
    if generation.state not in allowed:
        raise RetrievalProjectionGenerationError(
            f"generation state {generation.state!r} is not one of {sorted(allowed)}"
        )


def _current_event_watermark(db: Session) -> int:
    return int(db.scalar(select(func.max(RetrievalProjectionEvent.event_sequence))) or 0)


def _validated_required_event_sequence(
    db: Session,
    *,
    required_event_sequence: int | None,
) -> int:
    current_watermark = _current_event_watermark(db)
    if required_event_sequence is None:
        return current_watermark
    if required_event_sequence < 0:
        raise RetrievalProjectionGenerationError("required event watermark must not be negative")
    if required_event_sequence > current_watermark:
        raise RetrievalProjectionGenerationError(
            "required event watermark cannot exceed the persisted event watermark"
        )
    return required_event_sequence


def _lock_backend_control_plane(db: Session, backend: str) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, CAST(0 AS bigint)))"),
        {"identity": f"retrieval-projection-generation:{backend}"},
    )


def _backend_value(value: RetrievalProjectionBackend | str) -> str:
    try:
        return RetrievalProjectionBackend(str(value)).value
    except ValueError as error:
        raise ValueError("backend must be 'opensearch' or 'qdrant'") from error


def _generation_key(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if not _GENERATION_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "generation_key must contain only lowercase letters, digits, underscores, or hyphens"
        )
    return normalized


def _required_name(value: object, *, field: str, max_length: int = 255) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{field} exceeds {max_length} characters")
    return normalized


def _optional_checksum(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > 128:
        raise ValueError("checksum exceeds 128 characters")
    return normalized


def _touch(generation: RetrievalProjectionGeneration) -> None:
    generation.updated_at = utcnow_naive()


__all__ = [
    "RetrievalProjectionGenerationCutoverTarget",
    "RetrievalProjectionGenerationError",
    "RetrievalProjectionGenerationPair",
    "RetrievalProjectionGenerationPairCutoverPlan",
    "advance_generation_replay_checkpoint",
    "begin_generation_cutover",
    "compensate_generation_pair_cutover",
    "complete_generation_cutover",
    "complete_generation_pair_cutover",
    "create_projection_generation",
    "mark_generation_baselining",
    "mark_generation_cutover_failed",
    "mark_generation_replaying",
    "mark_generation_validating",
    "prepare_generation_pair_cutover",
    "record_generation_validation",
]
