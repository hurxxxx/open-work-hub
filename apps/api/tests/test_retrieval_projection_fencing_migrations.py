from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_fencing import record_projection_event


pytestmark = pytest.mark.migration

_PARTITION_ID = "d1f35cd5-4fd1-442c-93ed-6a79afe0fa85"


@pytest.fixture
def projection_engine(application_postgres_dsn: str):
    engine = create_engine(application_postgres_dsn)
    with Session(engine) as db, db.begin():
        db.add(
            RetrievalPartition(
                id=_PARTITION_ID,
                source_namespace="projection-fencing-test",
                candidate_scope_kind="company",
                is_default_ingest=False,
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


def _session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_concurrent_first_event_serializes_one_head_and_monotonic_versions(
    projection_engine,
) -> None:
    factory = _session_factory(projection_engine)
    barrier = Barrier(2)

    def write_event(checksum: str):
        barrier.wait(timeout=10)
        with factory.begin() as db:
            return record_projection_event(
                db,
                resource_type="file_manager_file",
                resource_id="file-concurrent",
                retrieval_partition_id=_PARTITION_ID,
                change_kind="content",
                desired_state="active",
                content_checksum=checksum,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write_event, checksum) for checksum in ("a", "b")]
        refs = [future.result(timeout=15) for future in futures]

    assert sorted(ref.projection_version for ref in refs) == [1, 2]
    assert len({ref.event_sequence for ref in refs}) == 2

    with factory() as db:
        head = db.get(
            RetrievalProjectionHead,
            ("file_manager_file", "file-concurrent"),
        )
        events = db.scalars(
            select(RetrievalProjectionEvent)
            .where(
                RetrievalProjectionEvent.resource_type == "file_manager_file",
                RetrievalProjectionEvent.resource_id == "file-concurrent",
            )
            .order_by(RetrievalProjectionEvent.projection_version)
        ).all()

    assert head is not None
    assert head.projection_version == 2
    assert [event.projection_version for event in events] == [1, 2]


def test_projection_version_is_per_resource_and_event_sequence_is_global_identity(
    projection_engine,
) -> None:
    factory = _session_factory(projection_engine)
    with factory.begin() as db:
        first = record_projection_event(
            db,
            resource_type="docs_native_doc",
            resource_id="doc-a",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
        )
        second = record_projection_event(
            db,
            resource_type="docs_native_doc",
            resource_id="doc-b",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
        )
        third = record_projection_event(
            db,
            resource_type="docs_native_doc",
            resource_id="doc-a",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="visibility",
            desired_state="active",
            visibility_checksum="acl-v2",
        )

    assert [first.projection_version, second.projection_version, third.projection_version] == [
        1,
        1,
        2,
    ]
    assert first.event_sequence < second.event_sequence < third.event_sequence

    with projection_engine.connect() as connection:
        identity = connection.execute(
            text(
                """
                SELECT is_identity, identity_generation
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'retrieval_projection_events'
                  AND column_name = 'event_sequence'
                """
            )
        ).one()

    assert identity == ("YES", "BY DEFAULT")


def test_projection_event_participates_in_outer_transaction_rollback(
    projection_engine,
) -> None:
    factory = _session_factory(projection_engine)

    with pytest.raises(RuntimeError, match="rollback projection mutation"):
        with factory.begin() as db:
            record_projection_event(
                db,
                resource_type="docs_native_doc",
                resource_id="doc-rollback",
                retrieval_partition_id=_PARTITION_ID,
                change_kind="content",
                desired_state="active",
            )
            raise RuntimeError("rollback projection mutation")

    with factory() as db:
        head = db.get(RetrievalProjectionHead, ("docs_native_doc", "doc-rollback"))
        events = db.scalars(
            select(RetrievalProjectionEvent).where(
                RetrievalProjectionEvent.resource_type == "docs_native_doc",
                RetrievalProjectionEvent.resource_id == "doc-rollback",
            )
        ).all()

    assert head is None
    assert events == []


def test_database_rejects_projection_event_update_and_delete(projection_engine) -> None:
    factory = _session_factory(projection_engine)
    with factory.begin() as db:
        event = record_projection_event(
            db,
            resource_type="meeting",
            resource_id="meeting-immutable",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
        )

    with pytest.raises(IntegrityError) as update_error:
        with projection_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE retrieval_projection_events
                    SET content_checksum = 'changed'
                    WHERE event_sequence = :event_sequence
                    """
                ),
                {"event_sequence": event.event_sequence},
            )
    assert getattr(update_error.value.orig, "sqlstate", None) == "23514"

    with pytest.raises(IntegrityError) as delete_error:
        with projection_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM retrieval_projection_events
                    WHERE event_sequence = :event_sequence
                    """
                ),
                {"event_sequence": event.event_sequence},
            )
    assert getattr(delete_error.value.orig, "sqlstate", None) == "23514"


def test_delete_event_keeps_tombstone_head_and_database_rejects_head_delete(
    projection_engine,
) -> None:
    factory = _session_factory(projection_engine)
    with factory.begin() as db:
        active = record_projection_event(
            db,
            resource_type="file_manager_file",
            resource_id="file-deleted",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            content_checksum="content-v1",
        )
        tombstone = record_projection_event(
            db,
            resource_type="file_manager_file",
            resource_id="file-deleted",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="delete",
            desired_state="deleted",
        )

    assert active.projection_version == 1
    assert tombstone.projection_version == 2

    with factory() as db:
        head = db.get(
            RetrievalProjectionHead,
            ("file_manager_file", "file-deleted"),
        )
        persisted_tombstone = db.get(RetrievalProjectionEvent, tombstone.event_sequence)

    assert head is not None
    assert head.projection_version == 2
    assert head.desired_state == "deleted"
    assert head.content_checksum is None
    assert persisted_tombstone is not None
    assert persisted_tombstone.desired_state == "deleted"

    with pytest.raises(IntegrityError) as delete_error:
        with projection_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM retrieval_projection_heads
                    WHERE resource_type = 'file_manager_file'
                      AND resource_id = 'file-deleted'
                    """
                )
            )
    assert getattr(delete_error.value.orig, "sqlstate", None) == "23514"

    with factory() as db:
        assert (
            db.get(
                RetrievalProjectionHead,
                ("file_manager_file", "file-deleted"),
            )
            is not None
        )
