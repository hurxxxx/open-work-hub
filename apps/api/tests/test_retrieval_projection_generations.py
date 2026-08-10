from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionGeneration,
)
from open_work_hub_api.domains.retrieval.projection_generations import (
    RetrievalProjectionGenerationError,
    begin_generation_cutover,
    compensate_generation_pair_cutover,
    complete_generation_cutover,
    complete_generation_pair_cutover,
    create_projection_generation,
    mark_generation_baselining,
    mark_generation_replaying,
    mark_generation_validating,
    prepare_generation_pair_cutover,
    record_generation_validation,
)


_PARTITION_ID = "d1f35cd5-4fd1-442c-93ed-6a79afe0fa85"


@pytest.fixture
def generation_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        RetrievalPartition.__table__,
        RetrievalProjectionEvent.__table__,
        RetrievalProjectionGeneration.__table__,
    ):
        table.create(engine)
    db = Session(engine, expire_on_commit=False)
    db.add(
        RetrievalPartition(
            id=_PARTITION_ID,
            source_namespace="generation-test",
            candidate_scope_kind="company",
            is_default_ingest=False,
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _ready_generation(db: Session, *, key: str) -> RetrievalProjectionGeneration:
    return _ready_backend_generation(db, backend="opensearch", key=key)


def _ready_backend_generation(
    db: Session,
    *,
    backend: str,
    key: str,
) -> RetrievalProjectionGeneration:
    schema_version = 3 if backend == "opensearch" else 1
    physical_prefix = "keyword" if backend == "opensearch" else "rag"
    generation = create_projection_generation(
        db,
        backend=backend,
        generation_key=key,
        physical_name=f"{physical_prefix}-v{schema_version}-{key}",
        alias_name=f"{physical_prefix}-live",
        schema_version=schema_version,
    )
    mark_generation_baselining(db, generation_id=generation.id)
    mark_generation_replaying(
        db,
        generation_id=generation.id,
        expected_projection_count=0,
    )
    mark_generation_validating(db, generation_id=generation.id)
    record_generation_validation(
        db,
        generation_id=generation.id,
        passed=True,
        details={"key_set": "passed", "acl_matrix": "passed"},
        content_checksum="a" * 64,
        config_checksum="b" * 64,
    )
    return generation


def _ready_pair(
    db: Session,
    *,
    key: str,
) -> tuple[RetrievalProjectionGeneration, RetrievalProjectionGeneration]:
    return (
        _ready_backend_generation(db, backend="opensearch", key=key),
        _ready_backend_generation(db, backend="qdrant", key=key),
    )


def test_pair_cutover_promotes_both_backends_and_rolls_back_the_previous_pair(
    generation_db: Session,
) -> None:
    first_opensearch, first_qdrant = _ready_pair(generation_db, key="first-pair")
    first_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=first_opensearch.id,
        qdrant_generation_id=first_qdrant.id,
        writes_quiesced=True,
    )
    complete_generation_pair_cutover(
        generation_db,
        plan=first_plan,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )

    second_opensearch, second_qdrant = _ready_pair(generation_db, key="second-pair")
    second_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=second_opensearch.id,
        qdrant_generation_id=second_qdrant.id,
        writes_quiesced=True,
    )
    rollback_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    activated = complete_generation_pair_cutover(
        generation_db,
        plan=second_plan,
        rollback_expires_at=rollback_expires_at,
    )

    assert first_opensearch.state == "rollback"
    assert first_qdrant.state == "rollback"
    assert first_opensearch.rollback_expires_at == rollback_expires_at
    assert first_qdrant.rollback_expires_at == rollback_expires_at
    assert activated.opensearch.state == "active"
    assert activated.qdrant.state == "active"
    assert second_plan.opensearch.previous_generation_id == first_opensearch.id
    assert second_plan.qdrant.previous_generation_id == first_qdrant.id
    assert second_plan.opensearch.alias_name == "keyword-live"
    assert second_plan.opensearch.physical_name == "keyword-v3-second-pair"
    assert second_plan.opensearch.previous_physical_name == "keyword-v3-first-pair"
    assert second_plan.qdrant.alias_name == "rag-live"
    assert second_plan.qdrant.physical_name == "rag-v1-second-pair"
    assert second_plan.qdrant.previous_physical_name == "rag-v1-first-pair"


@pytest.mark.parametrize(
    ("aliases_restored", "expected_state"),
    [(True, "failed"), (False, "compensation_required")],
)
def test_pair_cutover_compensation_marks_both_targets_together(
    generation_db: Session,
    aliases_restored: bool,
    expected_state: str,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key="compensate-pair")
    plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=opensearch.id,
        qdrant_generation_id=qdrant.id,
        writes_quiesced=True,
    )

    compensated = compensate_generation_pair_cutover(
        generation_db,
        plan=plan,
        reason="external_alias_switch_failed",
        aliases_restored=aliases_restored,
    )

    assert compensated.opensearch.state == expected_state
    assert compensated.qdrant.state == expected_state
    assert compensated.opensearch.failure_reason == "external_alias_switch_failed"
    assert compensated.qdrant.failure_reason == "external_alias_switch_failed"


def test_pair_compensation_can_be_closed_after_both_aliases_are_later_restored(
    generation_db: Session,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key="restore-later")
    plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=opensearch.id,
        qdrant_generation_id=qdrant.id,
        writes_quiesced=True,
    )
    compensate_generation_pair_cutover(
        generation_db,
        plan=plan,
        reason="alias_state_unknown",
        aliases_restored=False,
    )

    resolved = compensate_generation_pair_cutover(
        generation_db,
        plan=plan,
        reason="both_aliases_restored",
        aliases_restored=True,
    )

    assert resolved.opensearch.state == "failed"
    assert resolved.qdrant.state == "failed"
    assert resolved.opensearch.failure_reason == "both_aliases_restored"
    assert resolved.qdrant.failure_reason == "both_aliases_restored"


def test_pair_cutover_rejects_mismatched_release_cohorts_without_mutation(
    generation_db: Session,
) -> None:
    opensearch = _ready_backend_generation(
        generation_db,
        backend="opensearch",
        key="release-one",
    )
    qdrant = _ready_backend_generation(
        generation_db,
        backend="qdrant",
        key="release-two",
    )

    with pytest.raises(RetrievalProjectionGenerationError, match="same generation_key"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("schema", "schema_version must be 1"),
        ("validation_state", "must pass validation"),
        ("validated_at", "validation timestamp"),
        ("validation_cohort", "release cohort"),
    ],
)
def test_pair_cutover_requires_the_validated_backend_schema_contract(
    generation_db: Session,
    mutation: str,
    message: str,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key=f"invalid-{mutation}")
    if mutation == "schema":
        qdrant.schema_version = 2
    elif mutation == "validation_state":
        qdrant.validation_state = "pending"
    elif mutation == "validated_at":
        qdrant.validated_at = None
    else:
        assert qdrant.validation_details is not None
        qdrant.validation_details = {
            **qdrant.validation_details,
            "release_cohort": "another-release",
        }
    generation_db.flush()

    with pytest.raises(RetrievalProjectionGenerationError, match=message):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_pair_cutover_rejects_a_partial_target_pair(generation_db: Session) -> None:
    opensearch = _ready_backend_generation(
        generation_db,
        backend="opensearch",
        key="partial-target",
    )

    with pytest.raises(RetrievalProjectionGenerationError, match="exactly one"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id="00000000-0000-0000-0000-000000000000",
            writes_quiesced=True,
        )

    assert opensearch.state == "ready"


def test_pair_cutover_rejects_multiple_targets_for_the_same_backend(
    generation_db: Session,
) -> None:
    first = _ready_backend_generation(
        generation_db,
        backend="opensearch",
        key="duplicate-one",
    )
    second = _ready_backend_generation(
        generation_db,
        backend="opensearch",
        key="duplicate-two",
    )

    with pytest.raises(RetrievalProjectionGenerationError, match="exactly one"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=first.id,
            qdrant_generation_id=second.id,
            writes_quiesced=True,
        )

    assert first.state == "ready"
    assert second.state == "ready"


def test_pair_cutover_rejects_another_in_progress_backend_cutover(
    generation_db: Session,
) -> None:
    in_progress = _ready_generation(generation_db, key="already-activating")
    begin_generation_cutover(
        generation_db,
        generation_id=in_progress.id,
        writes_quiesced=True,
    )
    opensearch, qdrant = _ready_pair(generation_db, key="blocked-pair")

    with pytest.raises(RetrievalProjectionGenerationError, match="already in progress"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert in_progress.state == "activating"
    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_pair_cutover_rejects_a_partial_current_active_pair(
    generation_db: Session,
) -> None:
    legacy_opensearch = _ready_generation(generation_db, key="legacy-active")
    begin_generation_cutover(
        generation_db,
        generation_id=legacy_opensearch.id,
        writes_quiesced=True,
    )
    complete_generation_cutover(
        generation_db,
        generation_id=legacy_opensearch.id,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    opensearch, qdrant = _ready_pair(generation_db, key="next-pair")

    with pytest.raises(RetrievalProjectionGenerationError, match="partial or contains multiple"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert legacy_opensearch.state == "active"
    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_pair_cutover_rejects_when_either_replay_checkpoint_is_behind(
    generation_db: Session,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key="behind-pair")
    generation_db.add(
        RetrievalProjectionEvent(
            resource_type="file_manager_file",
            resource_id="file-pair-1",
            projection_version=1,
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            created_at=utcnow_naive(),
        )
    )
    generation_db.flush()

    with pytest.raises(RetrievalProjectionGenerationError, match="checkpoint is behind"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_pair_cutover_fails_closed_without_writer_quiescence(
    generation_db: Session,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key="writers-active")

    with pytest.raises(RetrievalProjectionGenerationError, match="writers to be quiesced"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=False,
        )

    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_pair_completion_rechecks_the_watermark_before_promoting(
    generation_db: Session,
) -> None:
    opensearch, qdrant = _ready_pair(generation_db, key="late-event")
    plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=opensearch.id,
        qdrant_generation_id=qdrant.id,
        writes_quiesced=True,
    )
    generation_db.add(
        RetrievalProjectionEvent(
            resource_type="file_manager_file",
            resource_id="file-pair-late",
            projection_version=1,
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            created_at=utcnow_naive(),
        )
    )
    generation_db.flush()

    with pytest.raises(RetrievalProjectionGenerationError, match="checkpoint is behind"):
        complete_generation_pair_cutover(
            generation_db,
            plan=plan,
            rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        )

    assert opensearch.state == "activating"
    assert qdrant.state == "activating"


def test_pair_prepare_and_complete_are_each_atomic_in_the_callers_transaction(
    generation_db: Session,
) -> None:
    first_opensearch, first_qdrant = _ready_pair(generation_db, key="atomic-first")
    first_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=first_opensearch.id,
        qdrant_generation_id=first_qdrant.id,
        writes_quiesced=True,
    )
    complete_generation_pair_cutover(
        generation_db,
        plan=first_plan,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    generation_db.commit()

    second_opensearch, second_qdrant = _ready_pair(generation_db, key="atomic-second")
    generation_db.commit()
    prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=second_opensearch.id,
        qdrant_generation_id=second_qdrant.id,
        writes_quiesced=True,
    )
    generation_db.rollback()

    assert generation_db.get(RetrievalProjectionGeneration, second_opensearch.id).state == "ready"
    assert generation_db.get(RetrievalProjectionGeneration, second_qdrant.id).state == "ready"

    second_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=second_opensearch.id,
        qdrant_generation_id=second_qdrant.id,
        writes_quiesced=True,
    )
    generation_db.commit()
    complete_generation_pair_cutover(
        generation_db,
        plan=second_plan,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    generation_db.rollback()

    assert generation_db.get(RetrievalProjectionGeneration, first_opensearch.id).state == "active"
    assert generation_db.get(RetrievalProjectionGeneration, first_qdrant.id).state == "active"
    assert (
        generation_db.get(RetrievalProjectionGeneration, second_opensearch.id).state == "activating"
    )
    assert generation_db.get(RetrievalProjectionGeneration, second_qdrant.id).state == "activating"


def test_pair_compensation_leaves_the_previous_pair_active(
    generation_db: Session,
) -> None:
    first_opensearch, first_qdrant = _ready_pair(generation_db, key="active-pair")
    first_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=first_opensearch.id,
        qdrant_generation_id=first_qdrant.id,
        writes_quiesced=True,
    )
    complete_generation_pair_cutover(
        generation_db,
        plan=first_plan,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    second_opensearch, second_qdrant = _ready_pair(generation_db, key="failed-pair")
    second_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=second_opensearch.id,
        qdrant_generation_id=second_qdrant.id,
        writes_quiesced=True,
    )

    compensate_generation_pair_cutover(
        generation_db,
        plan=second_plan,
        reason="both_aliases_restored",
        aliases_restored=True,
    )

    assert first_opensearch.state == "active"
    assert first_qdrant.state == "active"
    assert second_opensearch.state == "failed"
    assert second_qdrant.state == "failed"


def test_pair_completion_rejects_a_stale_previous_alias_plan(
    generation_db: Session,
) -> None:
    first_opensearch, first_qdrant = _ready_pair(generation_db, key="stale-first")
    first_plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=first_opensearch.id,
        qdrant_generation_id=first_qdrant.id,
        writes_quiesced=True,
    )
    complete_generation_pair_cutover(
        generation_db,
        plan=first_plan,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    second_opensearch, second_qdrant = _ready_pair(generation_db, key="stale-second")
    plan = prepare_generation_pair_cutover(
        generation_db,
        opensearch_generation_id=second_opensearch.id,
        qdrant_generation_id=second_qdrant.id,
        writes_quiesced=True,
    )
    stale_plan = replace(
        plan,
        opensearch=replace(
            plan.opensearch,
            previous_physical_name="unexpected-previous-index",
        ),
    )

    with pytest.raises(RetrievalProjectionGenerationError, match="stale"):
        complete_generation_pair_cutover(
            generation_db,
            plan=stale_plan,
            rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        )

    assert first_opensearch.state == "active"
    assert first_qdrant.state == "active"
    assert second_opensearch.state == "activating"
    assert second_qdrant.state == "activating"


def test_pair_cutover_rejects_mismatched_current_active_generations(
    generation_db: Session,
) -> None:
    active_opensearch = _ready_backend_generation(
        generation_db,
        backend="opensearch",
        key="active-one",
    )
    active_qdrant = _ready_backend_generation(
        generation_db,
        backend="qdrant",
        key="active-two",
    )
    for generation in (active_opensearch, active_qdrant):
        begin_generation_cutover(
            generation_db,
            generation_id=generation.id,
            writes_quiesced=True,
        )
        complete_generation_cutover(
            generation_db,
            generation_id=generation.id,
            rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        )
    opensearch, qdrant = _ready_pair(generation_db, key="replacement-pair")

    with pytest.raises(RetrievalProjectionGenerationError, match="same generation_key"):
        prepare_generation_pair_cutover(
            generation_db,
            opensearch_generation_id=opensearch.id,
            qdrant_generation_id=qdrant.id,
            writes_quiesced=True,
        )

    assert active_opensearch.state == "active"
    assert active_qdrant.state == "active"
    assert opensearch.state == "ready"
    assert qdrant.state == "ready"


def test_generation_cutover_records_previous_generation_and_rollback_window(
    generation_db: Session,
) -> None:
    first = _ready_generation(generation_db, key="first")
    begin_generation_cutover(
        generation_db,
        generation_id=first.id,
        writes_quiesced=True,
    )
    complete_generation_cutover(
        generation_db,
        generation_id=first.id,
        rollback_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )

    second = _ready_generation(generation_db, key="second")
    begin_generation_cutover(
        generation_db,
        generation_id=second.id,
        writes_quiesced=True,
    )
    rollback_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    complete_generation_cutover(
        generation_db,
        generation_id=second.id,
        rollback_expires_at=rollback_expires_at,
    )

    assert first.state == "rollback"
    assert first.rollback_expires_at == rollback_expires_at
    assert second.state == "active"
    assert second.previous_generation_id == first.id


def test_cutover_rejects_generation_when_new_event_is_not_replayed(
    generation_db: Session,
) -> None:
    generation = _ready_generation(generation_db, key="behind")
    generation_db.add(
        RetrievalProjectionEvent(
            resource_type="file_manager_file",
            resource_id="file-1",
            projection_version=1,
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            created_at=utcnow_naive(),
        )
    )
    generation_db.flush()

    with pytest.raises(RetrievalProjectionGenerationError, match="checkpoint is behind"):
        begin_generation_cutover(
            generation_db,
            generation_id=generation.id,
            writes_quiesced=True,
        )


def test_cutover_fails_closed_without_writer_quiescence(generation_db: Session) -> None:
    generation = _ready_generation(generation_db, key="not-quiesced")

    with pytest.raises(RetrievalProjectionGenerationError, match="writers to be quiesced"):
        begin_generation_cutover(
            generation_db,
            generation_id=generation.id,
            writes_quiesced=False,
        )


def test_validation_details_are_bound_to_the_generation_release_cohort(
    generation_db: Session,
) -> None:
    generation = _ready_generation(generation_db, key="release-cohort")

    assert generation.validation_details == {
        "key_set": "passed",
        "acl_matrix": "passed",
        "release_cohort": "release-cohort",
    }


def test_validation_rejects_a_conflicting_release_cohort(generation_db: Session) -> None:
    generation = create_projection_generation(
        generation_db,
        backend="qdrant",
        generation_key="release-one",
        physical_name="rag-v1-release-one",
        alias_name="rag-live",
        schema_version=1,
    )
    mark_generation_baselining(generation_db, generation_id=generation.id)
    mark_generation_replaying(
        generation_db,
        generation_id=generation.id,
        expected_projection_count=0,
    )
    mark_generation_validating(generation_db, generation_id=generation.id)

    with pytest.raises(RetrievalProjectionGenerationError, match="release cohort"):
        record_generation_validation(
            generation_db,
            generation_id=generation.id,
            passed=True,
            details={"release_cohort": "release-two"},
        )
