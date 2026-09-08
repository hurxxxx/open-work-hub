from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, insert, select, text, delete
from sqlalchemy.orm import Session

from company_admission_fixture import seed_company_app_access
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
from open_work_hub_api.domains.auth.models import User, UserSystemRole
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
)
from open_work_hub_api.domains.files.source_access import (
    FileManagerSourceAccessAdapter,
)
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.policy import SourceAclPolicy
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


pytestmark = pytest.mark.migration

_FILE_COUNT = 10_000
_FILE_SIZE_BYTES = 1024 * 1024
_ACTOR_ID = "scale-corpus-platform-admin"
_OBSERVER_ID = "scale-corpus-observer"
_FIRST_FILE_ID = "scale-corpus-file-00000"
_SEEDED_AT = datetime(2026, 1, 1)


def test_native_postgres_ten_thousand_file_company_corpus_revocation_is_metadata_only(
    application_postgres_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(application_postgres_dsn)

    def unexpected_io(*args, **kwargs):
        raise AssertionError("Admission revocation must not rewrite content or invoke providers")

    monkeypatch.setattr(files_service, "enqueue_file_retrieval_sync", unexpected_io)
    for hook_name in (
        "put_file_object",
        "open_file_object",
        "remove_file_object",
        "remove_file_objects",
    ):
        monkeypatch.setattr(files_service.file_storage, hook_name, unexpected_io)
    try:
        with Session(engine) as db:
            corpus_id, partition_id = _seed_scale_corpus(db)
            assert (
                db.scalar(
                    select(func.sum(FileManagerFile.size_bytes)).where(
                        FileManagerFile.corpus_id == corpus_id
                    )
                )
                == _FILE_COUNT * _FILE_SIZE_BYTES
            )
            assert _corpus_index_state(db) == ("ix_file_manager_files_corpus_id", True, True)
            heads = _projection_head_snapshot(db, corpus_id=corpus_id)
            side_effect_counts = _side_effect_counts(db)
            assert len(heads) == _FILE_COUNT
            assert side_effect_counts == (_FILE_COUNT, 0, 0)
            observer = _required_observer(db)
            policy = SourceAclPolicy.for_user(db, user=observer)
            assert policy.can_read_resource(FILE_MANAGER_FILE_RESOURCE_TYPE, _FIRST_FILE_ID)
            statements = []

            def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
                statements.append(statement)

            event.listen(engine, "before_cursor_execute", capture)
            try:
                db.get(AppAccessPolicy, "files").audience = "selected"
                db.commit()
                assert not policy.can_read_resource(FILE_MANAGER_FILE_RESOURCE_TYPE, _FIRST_FILE_ID)
                db.add(AppUserGrant(app_id="files", user_id=observer.id))
                db.commit()
                assert policy.can_read_resource(FILE_MANAGER_FILE_RESOURCE_TYPE, _FIRST_FILE_ID)
                db.execute(delete(AppUserGrant).where(AppUserGrant.user_id == observer.id))
                db.commit()
                assert not policy.can_read_resource(FILE_MANAGER_FILE_RESOURCE_TYPE, _FIRST_FILE_ID)
            finally:
                event.remove(engine, "before_cursor_execute", capture)
            assert not _table_updates(statements, "file_manager_files")
            assert not _table_updates(statements, "file_manager_corpora")
            assert not _table_updates(statements, "retrieval_partitions")
            assert _projection_head_snapshot(db, corpus_id=corpus_id) == heads
            assert _side_effect_counts(db) == side_effect_counts
            assert _unchanged_child_count(db, corpus_id=corpus_id) == _FILE_COUNT
            corpus = db.get(FileManagerCorpus, corpus_id)
            partition = db.get(RetrievalPartition, partition_id)
            assert corpus.access_scope_kind == partition.candidate_scope_kind == "company"
            assert corpus.metadata_version == partition.metadata_version == 1
            assert corpus.retrieval_partition_id == partition_id
            assert partition.candidate_user_id is None
            binding = FileManagerSourceAccessAdapter().bind_resource_partition(
                db, resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE, resource_id=_FIRST_FILE_ID
            )
            assert binding.partition_id == partition_id
    finally:
        engine.dispose()


def _seed_scale_corpus(db: Session) -> tuple[str, str]:
    db.add_all(
        [
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
            UserSystemRole(
                id="scale-corpus-platform-role",
                user_id=_ACTOR_ID,
                role="platform_admin",
            ),
        ]
    )
    db.flush()
    actor = db.get(User, _ACTOR_ID)
    assert actor is not None
    seed_company_app_access(db, ("files",))
    corpus = files_service.create_file_corpus(
        db,
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
                "retrieval_partition_id": partition_id,
                "corpus_id": corpus_id,
                "owner_id": _ACTOR_ID,
                "filename": f"logical-1mib-{index:05d}.bin",
                "content_type": "application/octet-stream",
                "size_bytes": _FILE_SIZE_BYTES,
                "storage_key": f"files/scale-corpus/{index:05d}",
                "visibility": "company",
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


def _required_observer(db: Session) -> User:
    observer = db.get(User, _OBSERVER_ID)
    assert observer is not None
    return observer


def _unchanged_child_count(db: Session, *, corpus_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(FileManagerFile.id)).where(
                FileManagerFile.corpus_id == corpus_id,
                FileManagerFile.updated_at == _SEEDED_AT,
            )
        )
        or 0
    )


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
