from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.files.models import FileManagerCorpus, FileManagerFile  # noqa: F401
from ai_do_api.domains.mcloudoc.contracts import (
    CompleteIngestRun,
    McloudocChange,
    ResolvedGrant,
    StartIngestRun,
)
from ai_do_api.domains.mcloudoc.models import (
    McloudocDocument,
    McloudocIngestRun,
    McloudocSource,
)
from ai_do_api.domains.mcloudoc.ports import FilesUpsertCommand, FilesUpsertResult
from ai_do_api.domains.mcloudoc.service import (
    McloudocCoreError,
    apply_change,
    complete_ingest_run,
    create_source,
    fail_ingest_run,
    start_ingest_run,
)


@dataclass
class FakeFilesPort:
    upserts: list[FilesUpsertCommand] = field(default_factory=list)
    deletes: list[tuple[str, str]] = field(default_factory=list)
    quarantines: list[tuple[str, str]] = field(default_factory=list)
    checksums: dict[str, str] = field(default_factory=dict)
    force_acl_unresolved: bool = False

    def upsert(self, command: FilesUpsertCommand) -> FilesUpsertResult:
        self.upserts.append(command)
        file_id = command.existing_file_id or f"file-{command.document_id}"
        changed = self.checksums.get(file_id) != command.checksum
        self.checksums[file_id] = command.checksum
        return FilesUpsertResult(
            file_id=file_id,
            changed=changed,
            acl_resolved=not self.force_acl_unresolved,
        )

    def delete(self, *, file_id: str, reason: str) -> bool:
        self.deletes.append((file_id, reason))
        return True

    def quarantine(self, *, file_id: str, reason: str) -> bool:
        self.quarantines.append((file_id, reason))
        return True


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            McloudocSource.__table__,
            McloudocIngestRun.__table__,
            McloudocDocument.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def test_source_is_inactive_by_default_and_serializes_runs(db: Session) -> None:
    source = _source(db)
    request = StartIngestRun(
        source_id=source.id,
        mode="incremental",
        delivery_id="delivery-1",
    )

    with pytest.raises(McloudocCoreError, match="source_inactive"):
        start_ingest_run(db, request=request)
    db.rollback()

    source = db.get(McloudocSource, source.id)
    assert source is not None
    source.enabled = True
    db.commit()
    run = start_ingest_run(db, request=request)
    db.commit()

    same = start_ingest_run(db, request=request)
    assert same.id == run.id
    with pytest.raises(McloudocCoreError, match="source_ingest_already_running"):
        start_ingest_run(
            db,
            request=StartIngestRun(
                source_id=source.id,
                mode="incremental",
                delivery_id="delivery-2",
            ),
        )


def test_upsert_keeps_stable_file_identity_and_never_orders_revisions(db: Session) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    first_run = _start(db, source, delivery_id="delivery-z")
    first = apply_change(
        db,
        run_id=first_run.id,
        change=_upsert("doc-1", "delivery-z", revision="z-revision", body=b"first"),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=first_run.id,
        request=CompleteIngestRun(continuation="cursor-1"),
        files=files,
    )
    db.commit()

    second_run = _start(
        db,
        source,
        delivery_id="delivery-a",
        continuation="cursor-1",
    )
    second = apply_change(
        db,
        run_id=second_run.id,
        change=_upsert("doc-1", "delivery-a", revision="a-revision", body=b"second"),
        files=files,
    )

    assert second.document_id == first.document_id
    assert second.file_id == first.file_id
    assert files.upserts[-1].existing_file_id == first.file_id
    document = db.get(McloudocDocument, first.document_id)
    assert document is not None
    assert document.opaque_revision == "a-revision"


def test_resolved_team_grant_is_forwarded_to_files_port(db: Session) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    run = _start(db, source, delivery_id="delivery-team")
    change = _upsert("doc-team", "delivery-team", revision="1", body=b"team")
    change = change.model_copy(
        update={
            "source_uri": "internal-source-locator/doc-team",
            "resolved_grants": (
                ResolvedGrant(principal_type="team", principal_id="engineering-a"),
            ),
        }
    )

    apply_change(db, run_id=run.id, change=change, files=files)

    assert files.upserts[0].resolved_grants == (
        ResolvedGrant(principal_type="team", principal_id="engineering-a"),
    )
    assert files.upserts[0].source_uri == "internal-source-locator/doc-team"
    assert files.upserts[0].raw_metadata == {"category": "test"}
    document = db.get(McloudocDocument, result_document_id := files.upserts[0].document_id)
    assert document is not None
    assert document.id == result_document_id
    assert document.source_uri == "internal-source-locator/doc-team"


def test_files_principal_revalidation_failure_quarantines_current_delivery(
    db: Session,
) -> None:
    files = FakeFilesPort(force_acl_unresolved=True)
    source = _active_source(db)
    run = _start(db, source, delivery_id="delivery-stale-principal")

    result = apply_change(
        db,
        run_id=run.id,
        change=_upsert(
            "doc-stale-principal",
            "delivery-stale-principal",
            revision="1",
            body=b"closed",
        ),
        files=files,
    )

    document = db.get(McloudocDocument, result.document_id)
    assert result.outcome == "quarantined"
    assert document is not None
    assert document.file_id == result.file_id
    assert document.status == "quarantined"
    assert document.quarantine_code == "acl_principal_unresolved"
    assert run.quarantined_count == 1


def test_change_delivery_is_idempotent_and_conflicting_replay_is_rejected(db: Session) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    run = _start(db, source, delivery_id="delivery-1")
    change = _upsert("doc-1", "delivery-1", revision="rev", body=b"body")

    first = apply_change(db, run_id=run.id, change=change, files=files)
    replay = apply_change(db, run_id=run.id, change=change, files=files)

    assert first.idempotent is False
    assert replay.idempotent is True
    assert len(files.upserts) == 1
    assert run.received_count == 1

    with pytest.raises(McloudocCoreError, match="delivery_payload_conflict"):
        apply_change(
            db,
            run_id=run.id,
            change=_upsert("doc-1", "delivery-1", revision="rev", body=b"changed"),
            files=files,
        )


def test_completion_replay_is_idempotent_and_conflicting_replay_is_rejected(
    db: Session,
) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    seed_run = _start(db, source, delivery_id="completion-seed")
    seeded = apply_change(
        db,
        run_id=seed_run.id,
        change=_upsert(
            "completion-missing",
            "completion-seed",
            revision="1",
            body=b"seeded",
        ),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=seed_run.id,
        request=CompleteIngestRun(continuation="cursor-1"),
        files=files,
    )
    db.commit()

    snapshot = _start(
        db,
        source,
        delivery_id="completion-snapshot",
        mode="snapshot",
        continuation="cursor-1",
    )
    request = CompleteIngestRun(continuation="cursor-2", complete_snapshot=True)
    completed = complete_ingest_run(db, run_id=snapshot.id, request=request, files=files)
    db.commit()
    completed_at = completed.completed_at
    delete_count = len(files.deletes)
    upsert_count = len(files.upserts)

    replay = complete_ingest_run(db, run_id=snapshot.id, request=request, files=files)

    assert replay.id == completed.id
    assert replay.completed_at == completed_at
    assert len(files.deletes) == delete_count
    assert len(files.upserts) == upsert_count
    assert (seeded.file_id, "complete_snapshot_missing") in files.deletes

    with pytest.raises(McloudocCoreError, match="completion_idempotency_conflict"):
        complete_ingest_run(
            db,
            run_id=snapshot.id,
            request=CompleteIngestRun(continuation="different", complete_snapshot=True),
            files=files,
        )
    with pytest.raises(McloudocCoreError, match="completion_idempotency_conflict"):
        complete_ingest_run(
            db,
            run_id=snapshot.id,
            request=CompleteIngestRun(continuation="cursor-2", complete_snapshot=False),
            files=files,
        )


@pytest.mark.parametrize(
    ("raw_acl", "resolution_complete", "expected_code"),
    [
        (None, False, "acl_missing"),
        ({"entries": ["unknown"]}, False, "acl_unresolved"),
    ],
)
def test_missing_or_unresolved_acl_is_quarantined(
    db: Session,
    raw_acl: dict | None,
    resolution_complete: bool,
    expected_code: str,
) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    initial_run = _start(db, source, delivery_id="delivery-1")
    active = apply_change(
        db,
        run_id=initial_run.id,
        change=_upsert("doc-1", "delivery-1", revision="rev-1", body=b"active"),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=initial_run.id,
        request=CompleteIngestRun(continuation="cursor-1"),
        files=files,
    )
    db.commit()

    quarantine_run = _start(
        db,
        source,
        delivery_id="delivery-2",
        continuation="cursor-1",
    )
    result = apply_change(
        db,
        run_id=quarantine_run.id,
        change=_upsert(
            "doc-1",
            "delivery-2",
            revision="rev-2",
            body=b"unsafe",
            raw_acl=raw_acl,
            resolution_complete=resolution_complete,
        ),
        files=files,
    )

    assert result.outcome == "quarantined"
    assert files.quarantines[-1] == (active.file_id, expected_code)
    document = db.get(McloudocDocument, active.document_id)
    assert document is not None
    assert document.status == "quarantined"
    assert document.quarantine_code == expected_code


def test_snapshot_tombstones_missing_documents_only_when_complete(db: Session) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    seed_run = _start(db, source, delivery_id="seed")
    a = apply_change(
        db,
        run_id=seed_run.id,
        change=_upsert("a", "seed", revision="1", body=b"a"),
        files=files,
    )
    b = apply_change(
        db,
        run_id=seed_run.id,
        change=_upsert("b", "seed", revision="1", body=b"b"),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=seed_run.id,
        request=CompleteIngestRun(continuation="cursor-1"),
        files=files,
    )
    db.commit()

    partial = _start(
        db,
        source,
        delivery_id="partial",
        mode="snapshot",
        continuation="cursor-1",
    )
    apply_change(
        db,
        run_id=partial.id,
        change=_upsert("a", "partial", revision="2", body=b"a2"),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=partial.id,
        request=CompleteIngestRun(continuation="partial-cursor", complete_snapshot=False),
        files=files,
    )
    db.commit()

    assert db.get(McloudocDocument, b.document_id).status == "active"  # type: ignore[union-attr]
    assert db.get(McloudocSource, source.id).current_continuation == "cursor-1"  # type: ignore[union-attr]

    complete = _start(
        db,
        source,
        delivery_id="complete",
        mode="snapshot",
        continuation="cursor-1",
    )
    apply_change(
        db,
        run_id=complete.id,
        change=_upsert("a", "complete", revision="3", body=b"a3"),
        files=files,
    )
    complete_ingest_run(
        db,
        run_id=complete.id,
        request=CompleteIngestRun(continuation="cursor-2", complete_snapshot=True),
        files=files,
    )

    assert db.get(McloudocDocument, a.document_id).status == "active"  # type: ignore[union-attr]
    assert db.get(McloudocDocument, b.document_id).status == "deleted"  # type: ignore[union-attr]
    assert (b.file_id, "complete_snapshot_missing") in files.deletes


def test_delete_before_upsert_creates_idempotent_tombstone(db: Session) -> None:
    files = FakeFilesPort()
    source = _active_source(db)
    run = _start(db, source, delivery_id="delete-delivery")
    change = McloudocChange(
        operation="delete",
        external_id="not-seen-before",
        delivery_id="delete-delivery",
        opaque_revision="delete-token",
    )

    first = apply_change(db, run_id=run.id, change=change, files=files)
    replay = apply_change(db, run_id=run.id, change=change, files=files)

    document = db.get(McloudocDocument, first.document_id)
    assert document is not None
    assert document.status == "deleted"
    assert document.file_id is None
    assert document.opaque_revision == "delete-token"
    assert replay.idempotent is True
    assert files.deletes == []


def test_failed_run_records_bounded_error_and_does_not_advance_continuation(db: Session) -> None:
    source = _active_source(db)
    run = _start(db, source, delivery_id="delivery-1")

    failed = fail_ingest_run(
        db,
        run_id=run.id,
        code="adapter_failed",
        detail="safe diagnostic",
    )

    assert failed.status == "failed"
    assert failed.errors == [{"code": "adapter_failed", "detail": "safe diagnostic"}]
    assert source.active_run_id is None
    assert source.current_continuation is None


def test_documents_are_isolated_by_source_identity(db: Session) -> None:
    files = FakeFilesPort()
    left = _active_source(db, name="left")
    right = _active_source(db, name="right")
    left_run = _start(db, left, delivery_id="left-delivery")
    right_run = _start(db, right, delivery_id="right-delivery")

    left_result = apply_change(
        db,
        run_id=left_run.id,
        change=_upsert("same-id", "left-delivery", revision="1", body=b"left"),
        files=files,
    )
    right_result = apply_change(
        db,
        run_id=right_run.id,
        change=_upsert("same-id", "right-delivery", revision="1", body=b"right"),
        files=files,
    )

    assert left_result.document_id != right_result.document_id
    assert len(tuple(db.scalars(select(McloudocDocument)))) == 2


def _source(db: Session, *, name: str = "mcloudoc") -> McloudocSource:
    source = create_source(
        db,
        name=name,
        scope_type="workspace",
        scope_id=f"workspace-{name}",
        corpus_id=f"corpus-{name}",
        ingest_owner_id=f"owner-{name}",
    )
    db.commit()
    return source


def _active_source(db: Session, *, name: str = "mcloudoc") -> McloudocSource:
    source = _source(db, name=name)
    source.enabled = True
    db.commit()
    return source


def _start(
    db: Session,
    source: McloudocSource,
    *,
    delivery_id: str,
    mode: str = "incremental",
    continuation: str | None = None,
) -> McloudocIngestRun:
    run = start_ingest_run(
        db,
        request=StartIngestRun(
            source_id=source.id,
            mode=mode,
            delivery_id=delivery_id,
            continuation=continuation,
        ),
    )
    db.commit()
    return run


def _upsert(
    external_id: str,
    delivery_id: str,
    *,
    revision: str,
    body: bytes,
    raw_acl: dict | None = None,
    resolution_complete: bool = True,
) -> McloudocChange:
    effective_acl = {"entries": ["workspace"]} if raw_acl is None else raw_acl
    if raw_acl is None and not resolution_complete:
        effective_acl = None
    return McloudocChange(
        operation="upsert",
        external_id=external_id,
        delivery_id=delivery_id,
        opaque_revision=revision,
        checksum=f"opaque:{revision}:{len(body)}",
        filename=f"{external_id}.txt",
        content_type="text/plain",
        size_bytes=len(body),
        searchable_content=body,
        title=f"Document {external_id}",
        raw_metadata={"category": "test"},
        raw_acl=effective_acl,
        resolved_grants=(
            ResolvedGrant(principal_type="workspace", principal_id="workspace-mcloudoc"),
        )
        if resolution_complete
        else (),
        acl_resolution_complete=resolution_complete,
    )
