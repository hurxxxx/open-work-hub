from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from time import perf_counter
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, insert, select, text
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import (
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.files import service as files_service
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerCorpusTransitionAudit,
    FileManagerFile,
)
from ai_do_api.domains.files.source_access import (
    FileManagerSourceAccessAdapter,
    can_read_file,
)
from ai_do_api.domains.rag.models import RagSyncJob
from ai_do_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from ai_do_api.domains.search.models import SearchIndexJob
from ai_do_api.domains.source_access.policy import SourceAclPolicy
from ai_do_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


pytestmark = pytest.mark.migration

_FILE_COUNT = 10_000
_FILE_SIZE_BYTES = 1024 * 1024
_WORKSPACE_A_ID = "scale-corpus-workspace-a"
_WORKSPACE_B_ID = "scale-corpus-workspace-b"
_ACTOR_ID = "scale-corpus-platform-admin"
_OBSERVER_ID = "scale-corpus-observer"
_FIRST_FILE_ID = "scale-corpus-file-00000"
_SEEDED_AT = datetime(2026, 1, 1)


def test_native_postgres_ten_thousand_file_corpus_transition_is_metadata_only(
    application_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(application_postgres_dsn)
    unexpected_side_effects: list[str] = []

    def unexpected_side_effect(name: str):
        def fail(*_args: Any, **_kwargs: Any) -> None:
            unexpected_side_effects.append(name)
            raise AssertionError(f"corpus transition invoked backend hook: {name}")

        return fail

    monkeypatch.setattr(
        files_service,
        "enqueue_file_retrieval_sync",
        unexpected_side_effect("enqueue_file_retrieval_sync"),
    )
    for hook_name in (
        "put_file_object",
        "open_file_object",
        "remove_file_object",
        "remove_file_objects",
    ):
        monkeypatch.setattr(
            files_service.file_storage,
            hook_name,
            unexpected_side_effect(hook_name),
        )

    setup_started = perf_counter()
    try:
        with Session(engine) as db:
            corpus_id, partition_id = _seed_scale_corpus(db)
            setup_seconds = perf_counter() - setup_started
            logical_bytes = int(
                db.scalar(
                    select(func.sum(FileManagerFile.size_bytes)).where(
                        FileManagerFile.corpus_id == corpus_id
                    )
                )
                or 0
            )
            assert logical_bytes == _FILE_COUNT * _FILE_SIZE_BYTES
            assert _corpus_index_state(db) == (
                "ix_file_manager_files_corpus_id",
                True,
                True,
            )

            baseline_heads = _projection_head_snapshot(db, corpus_id=corpus_id)
            baseline_side_effect_counts = _side_effect_counts(db)
            assert len(baseline_heads) == _FILE_COUNT
            assert baseline_side_effect_counts == (_FILE_COUNT, 0, 0)

            statements: dict[str, list[str]] = defaultdict(list)
            active_phase: str | None = None

            def capture_statement(
                _connection,
                _cursor,
                statement: str,
                _parameters,
                _context,
                _executemany,
            ) -> None:
                if active_phase is not None:
                    statements[active_phase].append(statement)

            event.listen(engine, "before_cursor_execute", capture_statement)
            timings: dict[str, float] = {}

            def transition(
                phase: str,
                *,
                expected_metadata_version: int,
                access_scope_kind: str,
                target_workspace_id: str | None = None,
            ) -> None:
                nonlocal active_phase
                active_phase = phase
                started = perf_counter()
                try:
                    actor = db.get(User, _ACTOR_ID)
                    assert actor is not None
                    files_service.transition_file_corpus(
                        db,
                        corpus_id=corpus_id,
                        actor=actor,
                        expected_metadata_version=expected_metadata_version,
                        access_scope_kind=access_scope_kind,
                        target_workspace_id=target_workspace_id,
                        reason=f"Native PostgreSQL scale transition: {phase}",
                        request_id=f"scale-{phase}",
                    )
                    db.commit()
                finally:
                    timings[phase] = perf_counter() - started
                    active_phase = None

            try:
                transition(
                    "a_to_company",
                    expected_metadata_version=1,
                    access_scope_kind="company",
                )
                _assert_corpus_envelope(
                    db,
                    corpus_id=corpus_id,
                    partition_id=partition_id,
                    metadata_version=2,
                    access_scope_kind="company",
                    managed_workspace_id=_WORKSPACE_A_ID,
                )
                observer = _required_observer(db)
                assert can_read_file(
                    SourceAclPolicy.for_company(db, user=observer),
                    _FIRST_FILE_ID,
                )
                assert can_read_file(
                    _workspace_policy(
                        db,
                        workspace_id=_WORKSPACE_B_ID,
                        user=observer,
                    ),
                    _FIRST_FILE_ID,
                )
                assert _unchanged_child_count(db, corpus_id=corpus_id) == _FILE_COUNT
                db.rollback()

                transition(
                    "company_to_a",
                    expected_metadata_version=2,
                    access_scope_kind="workspace",
                    target_workspace_id=_WORKSPACE_A_ID,
                )
                _assert_corpus_envelope(
                    db,
                    corpus_id=corpus_id,
                    partition_id=partition_id,
                    metadata_version=3,
                    access_scope_kind="workspace",
                    managed_workspace_id=_WORKSPACE_A_ID,
                )
                observer = _required_observer(db)
                assert can_read_file(
                    _workspace_policy(
                        db,
                        workspace_id=_WORKSPACE_A_ID,
                        user=observer,
                    ),
                    _FIRST_FILE_ID,
                )
                assert not can_read_file(
                    _workspace_policy(
                        db,
                        workspace_id=_WORKSPACE_B_ID,
                        user=observer,
                    ),
                    _FIRST_FILE_ID,
                )
                assert _unchanged_child_count(db, corpus_id=corpus_id) == _FILE_COUNT
                db.rollback()

                transition(
                    "a_to_b",
                    expected_metadata_version=3,
                    access_scope_kind="workspace",
                    target_workspace_id=_WORKSPACE_B_ID,
                )
            finally:
                event.remove(engine, "before_cursor_execute", capture_statement)

            _assert_corpus_envelope(
                db,
                corpus_id=corpus_id,
                partition_id=partition_id,
                metadata_version=4,
                access_scope_kind="workspace",
                managed_workspace_id=_WORKSPACE_B_ID,
            )
            observer = _required_observer(db)
            assert not can_read_file(
                _workspace_policy(
                    db,
                    workspace_id=_WORKSPACE_A_ID,
                    user=observer,
                ),
                _FIRST_FILE_ID,
            )
            assert can_read_file(
                _workspace_policy(
                    db,
                    workspace_id=_WORKSPACE_B_ID,
                    user=observer,
                ),
                _FIRST_FILE_ID,
            )
            assert not can_read_file(
                SourceAclPolicy.for_company(db, user=observer),
                _FIRST_FILE_ID,
            )

            child_binding_distribution = {
                (str(workspace_id), str(child_partition_id)): int(count)
                for workspace_id, child_partition_id, count in db.execute(
                    select(
                        FileManagerFile.workspace_id,
                        FileManagerFile.retrieval_partition_id,
                        func.count(FileManagerFile.id),
                    )
                    .where(FileManagerFile.corpus_id == corpus_id)
                    .group_by(
                        FileManagerFile.workspace_id,
                        FileManagerFile.retrieval_partition_id,
                    )
                )
            }
            assert child_binding_distribution == {(_WORKSPACE_B_ID, partition_id): _FILE_COUNT}
            moved_count = child_binding_distribution[(_WORKSPACE_B_ID, partition_id)]
            assert moved_count == _FILE_COUNT
            sample_file = db.get(FileManagerFile, _FIRST_FILE_ID)
            assert sample_file is not None
            assert (
                sample_file.corpus_id,
                sample_file.retrieval_partition_id,
                sample_file.workspace_id,
                sample_file.size_bytes,
                sample_file.visibility,
            ) == (
                corpus_id,
                partition_id,
                _WORKSPACE_B_ID,
                _FILE_SIZE_BYTES,
                "workspace",
            )
            binding = FileManagerSourceAccessAdapter().bind_resource_partition(
                db,
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id=_FIRST_FILE_ID,
            )
            assert binding.partition_id == partition_id

            assert _projection_head_snapshot(db, corpus_id=corpus_id) == baseline_heads
            assert _side_effect_counts(db) == baseline_side_effect_counts
            assert unexpected_side_effects == []
            assert _audit_snapshot(db, corpus_id=corpus_id) == (
                ("workspace", "company", _WORKSPACE_A_ID, _WORKSPACE_A_ID, 1, 2),
                ("company", "workspace", _WORKSPACE_A_ID, _WORKSPACE_A_ID, 2, 3),
                ("workspace", "workspace", _WORKSPACE_A_ID, _WORKSPACE_B_ID, 3, 4),
            )

            scope_statements = statements["a_to_company"] + statements["company_to_a"]
            assert not _table_updates(scope_statements, "file_manager_files")
            transfer_file_updates = _table_updates(
                statements["a_to_b"],
                "file_manager_files",
            )
            assert len(transfer_file_updates) == 1
            assert len(statements["a_to_b"]) < 50

            scope_seconds = timings["a_to_company"] + timings["company_to_a"]
            print(
                "file_corpus_scale "
                f"rows={moved_count} "
                f"logical_gib={logical_bytes / (1024**3):.3f} "
                f"setup_seconds={setup_seconds:.3f} "
                f"scope_seconds={scope_seconds:.3f} "
                f"transfer_seconds={timings['a_to_b']:.3f} "
                f"scope_sql={len(scope_statements)} "
                f"transfer_sql={len(statements['a_to_b'])} "
                f"file_updates={len(transfer_file_updates)}"
            )
    finally:
        engine.dispose()


def _seed_scale_corpus(db: Session) -> tuple[str, str]:
    db.add_all(
        [
            Workspace(
                id=_WORKSPACE_A_ID,
                key=_WORKSPACE_A_ID,
                name="Scale Corpus Workspace A",
            ),
            Workspace(
                id=_WORKSPACE_B_ID,
                key=_WORKSPACE_B_ID,
                name="Scale Corpus Workspace B",
            ),
            User(
                id=_ACTOR_ID,
                login_id=_ACTOR_ID,
                email=f"{_ACTOR_ID}@example.com",
                full_name="Scale Corpus Platform Admin",
                password_hash="hash",
            ),
            User(
                id=_OBSERVER_ID,
                login_id=_OBSERVER_ID,
                email=f"{_OBSERVER_ID}@example.com",
                full_name="Scale Corpus Observer",
                password_hash="hash",
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            WorkspaceUserBinding(
                id="scale-corpus-admin-a",
                workspace_id=_WORKSPACE_A_ID,
                user_id=_ACTOR_ID,
                role="admin",
            ),
            WorkspaceUserBinding(
                id="scale-corpus-admin-b",
                workspace_id=_WORKSPACE_B_ID,
                user_id=_ACTOR_ID,
                role="admin",
            ),
            WorkspaceUserBinding(
                id="scale-corpus-observer-a",
                workspace_id=_WORKSPACE_A_ID,
                user_id=_OBSERVER_ID,
                role="member",
            ),
            WorkspaceUserBinding(
                id="scale-corpus-observer-b",
                workspace_id=_WORKSPACE_B_ID,
                user_id=_OBSERVER_ID,
                role="member",
            ),
            UserSystemRole(
                id="scale-corpus-platform-role",
                user_id=_ACTOR_ID,
                role="platform_admin",
            ),
        ]
    )
    db.flush()
    workspace = db.get(Workspace, _WORKSPACE_A_ID)
    actor = db.get(User, _ACTOR_ID)
    assert workspace is not None and actor is not None
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace,
        user=actor,
        name="Ten-thousand-file native PostgreSQL corpus",
    )
    db.flush()
    partition_id = str(corpus.retrieval_partition_id)
    corpus_id = str(corpus.id)
    checksum = "a" * 64
    visibility_checksum = "b" * 64

    file_rows = []
    head_rows = []
    event_rows = []
    for index in range(_FILE_COUNT):
        file_id = f"scale-corpus-file-{index:05d}"
        file_rows.append(
            {
                "id": file_id,
                "workspace_id": _WORKSPACE_A_ID,
                "retrieval_partition_id": partition_id,
                "corpus_id": corpus_id,
                "owner_id": _ACTOR_ID,
                "filename": f"logical-1mib-{index:05d}.bin",
                "content_type": "application/octet-stream",
                "size_bytes": _FILE_SIZE_BYTES,
                "storage_key": f"files/scale-corpus/{index:05d}",
                "visibility": "workspace",
                "extraction_status": "ready",
                "extraction_content_checksum": checksum,
                "extraction_text": "synthetic scale metadata",
                "extraction_blocks": [],
                "extraction_metadata": {"fixture": "logical-1mib"},
                "created_at": _SEEDED_AT,
                "updated_at": _SEEDED_AT,
            }
        )
        projection_values = {
            "resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE,
            "resource_id": file_id,
            "projection_version": 1,
            "retrieval_partition_id": partition_id,
            "desired_state": "active",
            "content_checksum": checksum,
            "visibility_checksum": visibility_checksum,
            "diagnostic_workspace_id": _WORKSPACE_A_ID,
        }
        head_rows.append({**projection_values, "updated_at": _SEEDED_AT})
        event_rows.append(
            {
                **projection_values,
                "change_kind": "content",
                "created_at": _SEEDED_AT,
            }
        )

    db.execute(insert(FileManagerFile), file_rows)
    db.execute(insert(RetrievalProjectionHead), head_rows)
    db.execute(insert(RetrievalProjectionEvent), event_rows)
    db.commit()
    return corpus_id, partition_id


def _projection_head_snapshot(
    db: Session,
    *,
    corpus_id: str,
) -> tuple[tuple[Any, ...], ...]:
    rows = db.execute(
        select(
            RetrievalProjectionHead.resource_type,
            RetrievalProjectionHead.resource_id,
            RetrievalProjectionHead.retrieval_partition_id,
            RetrievalProjectionHead.projection_version,
            RetrievalProjectionHead.desired_state,
            RetrievalProjectionHead.content_checksum,
            RetrievalProjectionHead.visibility_checksum,
            RetrievalProjectionHead.diagnostic_workspace_id,
        )
        .join(
            FileManagerFile,
            FileManagerFile.id == RetrievalProjectionHead.resource_id,
        )
        .where(
            RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            FileManagerFile.corpus_id == corpus_id,
        )
        .order_by(RetrievalProjectionHead.resource_id.asc())
    ).all()
    return tuple(tuple(row) for row in rows)


def _side_effect_counts(db: Session) -> tuple[int, int, int]:
    resource_prefix = "scale-corpus-file-%"
    return (
        int(
            db.scalar(
                select(func.count())
                .select_from(RetrievalProjectionEvent)
                .where(
                    RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
                    RetrievalProjectionEvent.resource_id.like(resource_prefix),
                )
            )
            or 0
        ),
        int(
            db.scalar(
                select(func.count())
                .select_from(SearchIndexJob)
                .where(SearchIndexJob.entity_id.like(resource_prefix))
            )
            or 0
        ),
        int(
            db.scalar(
                select(func.count())
                .select_from(RagSyncJob)
                .where(RagSyncJob.resource_id.like(resource_prefix))
            )
            or 0
        ),
    )


def _assert_corpus_envelope(
    db: Session,
    *,
    corpus_id: str,
    partition_id: str,
    metadata_version: int,
    access_scope_kind: str,
    managed_workspace_id: str,
) -> None:
    db.expire_all()
    corpus = db.get(FileManagerCorpus, corpus_id)
    partition = db.get(RetrievalPartition, partition_id)
    assert corpus is not None and partition is not None
    assert corpus.retrieval_partition_id == partition_id
    assert (
        corpus.metadata_version,
        corpus.access_scope_kind,
        corpus.managed_workspace_id,
    ) == (metadata_version, access_scope_kind, managed_workspace_id)
    assert (
        partition.metadata_version,
        partition.source_namespace,
        partition.managed_workspace_id,
        partition.candidate_scope_kind,
        partition.candidate_workspace_id,
        partition.candidate_user_id,
        partition.is_default_ingest,
    ) == (
        metadata_version,
        "files",
        managed_workspace_id,
        access_scope_kind,
        managed_workspace_id if access_scope_kind == "workspace" else None,
        None,
        False,
    )


def _required_observer(db: Session) -> User:
    observer = db.get(User, _OBSERVER_ID)
    assert observer is not None
    return observer


def _workspace_policy(
    db: Session,
    *,
    workspace_id: str,
    user: User,
) -> SourceAclPolicy:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    return SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)


def _unchanged_child_count(db: Session, *, corpus_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(FileManagerFile.id)).where(
                FileManagerFile.corpus_id == corpus_id,
                FileManagerFile.workspace_id == _WORKSPACE_A_ID,
                FileManagerFile.updated_at == _SEEDED_AT,
            )
        )
        or 0
    )


def _audit_snapshot(
    db: Session,
    *,
    corpus_id: str,
) -> tuple[tuple[Any, ...], ...]:
    rows = db.execute(
        select(
            FileManagerCorpusTransitionAudit.from_access_scope_kind,
            FileManagerCorpusTransitionAudit.to_access_scope_kind,
            FileManagerCorpusTransitionAudit.from_managed_workspace_id,
            FileManagerCorpusTransitionAudit.to_managed_workspace_id,
            FileManagerCorpusTransitionAudit.from_metadata_version,
            FileManagerCorpusTransitionAudit.to_metadata_version,
        )
        .where(FileManagerCorpusTransitionAudit.corpus_id == corpus_id)
        .order_by(FileManagerCorpusTransitionAudit.from_metadata_version.asc())
    ).all()
    return tuple(tuple(row) for row in rows)


def _table_updates(statements: list[str], table_name: str) -> list[str]:
    prefix = f"update {table_name} "
    return [
        statement
        for statement in statements
        if " ".join(statement.lower().split()).startswith(prefix)
    ]


def _corpus_index_state(db: Session) -> tuple[str, bool, bool]:
    row = db.execute(
        text(
            """
            SELECT idx.relname, catalog.indisvalid, catalog.indisready
            FROM pg_catalog.pg_index AS catalog
            JOIN pg_catalog.pg_class AS idx ON idx.oid = catalog.indexrelid
            WHERE catalog.indrelid = pg_catalog.to_regclass('file_manager_files')
              AND idx.relname = 'ix_file_manager_files_corpus_id'
            """
        )
    ).one()
    return str(row[0]), bool(row[1]), bool(row[2])
