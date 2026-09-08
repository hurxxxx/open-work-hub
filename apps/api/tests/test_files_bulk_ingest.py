from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from company_admission_fixture import company_authority_tables, seed_company_app_access

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User, UserSystemRole
from open_work_hub_api.domains.files import bulk_ingest, service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerBulkIngestEntry,
    FileManagerBulkIngestRun,
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.search.models import SearchIndexJob


ADMIN_ID = "admin-a"
MEMBER_ID = "member-a"
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manage_files_bulk_ingest.py"


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            *company_authority_tables(),
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerStorageCleanupJob.__table__,
            FileManagerBulkIngestRun.__table__,
            FileManagerBulkIngestEntry.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            SearchIndexJob.__table__,
            RagSyncJob.__table__,
        ],
    )
    with Session(engine) as session:
        seed_company_app_access(session)
        session.add_all(
            [
                User(
                    id=ADMIN_ID,
                    login_id="operator",
                    email="operator@example.com",
                    full_name="Operator",
                    password_hash="!",
                    status="active",
                    login_blocked=False,
                ),
                User(
                    id=MEMBER_ID,
                    login_id="owner",
                    email="owner@example.com",
                    full_name="Owner",
                    password_hash="!",
                    status="active",
                    login_blocked=False,
                ),
            ]
        )
        session.add(UserSystemRole(id="operator-role", user_id=ADMIN_ID, role="platform_admin"))
        session.commit()
        yield session


def test_create_run_is_idempotent_and_reserves_stable_target_ids(db: Session) -> None:
    entries = [
        _manifest_entry("nested/report.txt", b"report"),
        _manifest_entry("root.txt", b"root"),
    ]
    run = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        corpus_name="기술연구소 안전 적재",
        root_folder_name="프로젝트 RAG",
        idempotency_key="operation-20260729",
        manifest_sha256="a" * 64,
        source_root_sha256="b" * 64,
        entries=entries,
    )
    db.commit()
    target_ids = tuple(
        db.scalars(
            select(FileManagerBulkIngestEntry.target_file_id)
            .where(FileManagerBulkIngestEntry.run_id == run.id)
            .order_by(FileManagerBulkIngestEntry.source_path.asc())
        )
    )

    same = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        corpus_name="ignored-on-retry",
        root_folder_name="ignored-on-retry",
        idempotency_key="operation-20260729",
        manifest_sha256="a" * 64,
        source_root_sha256="b" * 64,
        entries=entries,
    )

    assert same.id == run.id
    assert same.corpus.operator_managed is True
    assert len(target_ids) == len(set(target_ids)) == 2
    assert db.scalar(select(func.count(FileManagerBulkIngestRun.id))) == 1
    assert db.scalar(select(func.count(FileManagerCorpus.id))) == 1
    assert db.scalar(select(func.count(FileManagerBulkIngestEntry.id))) == 2


def test_control_plane_admin_can_assign_only_an_authorized_ingest_owner(db: Session) -> None:
    owner = db.get(User, MEMBER_ID)
    assert owner is not None
    with pytest.raises(bulk_ingest.FilesBulkIngestError, match="run_owner_access_required"):
        bulk_ingest.create_run(
            db,
            actor=_actor(db),
            owner=owner,
            corpus_name="Denied",
            root_folder_name="Denied",
            idempotency_key="denied-owner",
            manifest_sha256="c" * 64,
            source_root_sha256="d" * 64,
            entries=[_manifest_entry("root.txt", b"root")],
        )
    db.add(UserSystemRole(id="delegated-operator-role", user_id=owner.id, role="platform_admin"))
    db.flush()
    run = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        owner=owner,
        corpus_name="기술연구소 안전 적재",
        root_folder_name="프로젝트 RAG",
        idempotency_key="member-owned-operation",
        manifest_sha256="c" * 64,
        source_root_sha256="d" * 64,
        entries=[_manifest_entry("root.txt", b"root")],
    )

    root = db.get(FileManagerFolder, run.root_folder_id)
    assert root is not None
    assert root.owner_id == MEMBER_ID
    assert run.created_by_id == ADMIN_ID
    assert run.corpus.created_by_id == ADMIN_ID


def test_operator_corpus_rejects_ordinary_upload_and_accepts_bound_run(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"searchable"
    source = tmp_path / "nested" / "report.txt"
    source.parent.mkdir()
    source.write_bytes(content)
    root_sha256 = bulk_ingest.source_root_identity(tmp_path)
    run = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        corpus_name="Managed",
        root_folder_name="Root",
        idempotency_key="operator-guard",
        manifest_sha256="a" * 64,
        source_root_sha256=root_sha256,
        entries=[_manifest_entry("nested/report.txt", content)],
    )
    db.commit()
    monkeypatch.setattr(files_service.file_storage, "put_file_object", lambda **_kwargs: None)
    monkeypatch.setattr(
        files_service, "enqueue_file_retrieval_sync", lambda *_args, **_kwargs: None
    )

    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.upload_file(
            db,
            user=_actor(db),
            filename="ordinary.txt",
            content_type="text/plain",
            content=BytesIO(b"ordinary"),
            size_bytes=8,
            folder_id=run.root_folder_id,
            visibility="company",
            corpus_id=run.corpus_id,
        )
    db.rollback()

    bulk_ingest.start_or_resume_run(
        db,
        run_id=run.id,
        manifest_sha256="a" * 64,
        source_root_sha256=root_sha256,
    )
    entry = bulk_ingest.list_ingest_candidates(db, run_id=run.id)[0]
    db.commit()
    assert bulk_ingest.ingest_entry(
        db,
        run_id=run.id,
        entry_id=entry.id,
        source_root=tmp_path,
        actor=_actor(db),
    )
    db.commit()

    uploaded = db.get(FileManagerFile, entry.target_file_id)
    assert uploaded is not None
    assert uploaded.corpus_id == run.corpus_id
    assert uploaded.visibility == "company"
    folder = db.get(FileManagerFolder, uploaded.folder_id)
    assert folder is not None and folder.name == "nested"

    assert (
        bulk_ingest.ingest_entry(
            db,
            run_id=run.id,
            entry_id=entry.id,
            source_root=tmp_path,
            actor=_actor(db),
        )
        is False
    )
    assert db.scalar(select(func.count(FileManagerFile.id))) == 1


def test_purge_is_cursor_batched_and_idempotent(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.autoflush = False
    entries = [
        _manifest_entry(f"batch/file-{index:03}.txt", f"value-{index}".encode())
        for index in range(101)
    ]
    run = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        corpus_name="Managed",
        root_folder_name="Root",
        idempotency_key="purge-batches",
        manifest_sha256="c" * 64,
        source_root_sha256="d" * 64,
        entries=entries,
    )
    rows = list(
        db.scalars(
            select(FileManagerBulkIngestEntry).where(FileManagerBulkIngestEntry.run_id == run.id)
        )
    )
    for entry in rows:
        entry.status = "uploaded"
        db.add(
            FileManagerFile(
                id=entry.target_file_id,
                retrieval_partition_id=run.corpus.retrieval_partition_id,
                corpus_id=run.corpus_id,
                folder_id=run.root_folder_id,
                owner_id=ADMIN_ID,
                filename=Path(entry.source_path).name,
                content_type=entry.content_type,
                size_bytes=entry.size_bytes,
                storage_key=f"files/{entry.target_file_id}/source.txt",
                visibility="company",
                extraction_status="ready",
                extraction_content_checksum=entry.content_sha256,
                extraction_text="derived",
            )
        )
    run.status = "completed"
    db.commit()
    monkeypatch.setattr(
        files_service, "enqueue_file_retrieval_sync", lambda *_args, **_kwargs: None
    )

    bulk_ingest.begin_purge(db, run_id=run.id)
    first = bulk_ingest.purge_batch(
        db,
        run_id=run.id,
        actor=_actor(db),
        limit=100,
    )
    db.commit()
    assert first.processed == 100
    assert first.state == "purging"
    assert len(first.storage_keys) == 100

    second = bulk_ingest.purge_batch(
        db,
        run_id=run.id,
        actor=_actor(db),
        limit=100,
    )
    db.commit()
    assert second.processed == 1
    assert second.state == "purged"
    assert len(second.storage_keys) == 1
    assert (
        db.scalar(
            select(func.count(FileManagerFile.id)).where(FileManagerFile.deleted_at.is_(None))
        )
        == 0
    )
    assert all(
        file.extraction_text is None and file.extraction_content_checksum is None
        for file in db.scalars(select(FileManagerFile))
    )
    assert db.get(FileManagerFolder, run.root_folder_id).deleted_at is not None
    cleanup_jobs = tuple(db.scalars(select(FileManagerStorageCleanupJob)).all())
    assert len(cleanup_jobs) == 101
    assert {job.status for job in cleanup_jobs} == {"pending"}

    again = bulk_ingest.purge_batch(
        db,
        run_id=run.id,
        actor=_actor(db),
        limit=100,
    )
    assert again.processed == 0
    assert db.scalar(select(func.count(FileManagerStorageCleanupJob.id))) == 101
    for job in cleanup_jobs:
        job.status = "succeeded"
        job.next_retry_at = None
        db.add(job)
    db.flush()
    assert (
        bulk_ingest.verify_clean(
            db,
            run_id=run.id,
            storage_objects=0,
            opensearch_documents=0,
            qdrant_points=0,
        ).clean
        is True
    )
    assert (
        bulk_ingest.verify_clean(
            db,
            run_id=run.id,
            storage_objects=0,
            opensearch_documents=1,
            qdrant_points=0,
        ).clean
        is False
    )


def test_inventory_manifest_is_private_and_stdout_is_aggregate_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_root = tmp_path / "sensitive-root"
    source_root.mkdir()
    sensitive_name = "customer-secret-report.txt"
    (source_root / sensitive_name).write_text("searchable", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    cli = _load_script()

    result = cli.main(
        [
            "inventory",
            "--source-root",
            str(source_root),
            "--manifest",
            str(manifest_path),
            "--include-extension",
            "txt",
        ]
    )

    output = capsys.readouterr()
    assert result == 0
    assert os.stat(manifest_path).st_mode & 0o777 == 0o600
    assert sensitive_name not in output.out + output.err
    payload = json.loads(manifest_path.read_text())
    assert payload["entries"][0]["source_path"] == sensitive_name
    assert "entries=1" in output.out

    os.chmod(manifest_path, 0o644)
    loaded = cli.main(
        [
            "create-run",
            "--manifest",
            str(manifest_path),
            "--actor-login-id",
            "operator",
            "--run-key",
            "dry-run",
            "--corpus-name",
            "Managed",
            "--root-folder-name",
            "Root",
            "--dry-run",
        ]
    )
    assert loaded == 1
    assert capsys.readouterr().err.strip() == ("status=failed reason=manifest_permissions_invalid")


def test_storage_verification_fails_closed_for_missing_bucket(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = bulk_ingest.create_run(
        db,
        actor=_actor(db),
        corpus_name="Managed",
        root_folder_name="Root",
        idempotency_key="missing-bucket",
        manifest_sha256="e" * 64,
        source_root_sha256="f" * 64,
        entries=[_manifest_entry("source.txt", b"source")],
    )
    entry = db.scalar(
        select(FileManagerBulkIngestEntry).where(FileManagerBulkIngestEntry.run_id == run.id)
    )
    assert entry is not None
    db.add(
        FileManagerFile(
            id=entry.target_file_id,
            retrieval_partition_id=run.corpus.retrieval_partition_id,
            corpus_id=run.corpus_id,
            folder_id=run.root_folder_id,
            owner_id=ADMIN_ID,
            filename="source.txt",
            content_type="text/plain",
            size_bytes=6,
            storage_key=f"files/{entry.target_file_id}/source.txt",
            visibility="company",
        )
    )
    db.commit()
    cli = _load_script()

    class MissingBucket(Exception):
        code = "NoSuchBucket"

    class Client:
        def stat_object(self, _bucket, _storage_key):
            raise MissingBucket

    monkeypatch.setattr(cli, "get_minio_client", Client)
    with pytest.raises(
        bulk_ingest.FilesBulkIngestError,
        match="storage_verification_failed",
    ):
        cli._count_storage_objects(db, run_id=run.id, bucket="missing")


def test_production_mutations_require_exact_confirmation_but_dry_run_does_not(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_script()
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    monkeypatch.setattr(cli, "is_production_environment", lambda _environment: True)

    rejected = cli.main(["pause", "--run-id", "run-1"])
    assert rejected == 1
    assert capsys.readouterr().err.strip() == (
        "status=failed reason=production_confirmation_required"
    )

    planned = cli.main(["pause", "--run-id", "run-1", "--dry-run"])
    assert planned == 0
    assert capsys.readouterr().out.strip() == (
        "status=ok run_id=run-1 state=pause-planned dry_run=1"
    )


def _manifest_entry(path: str, content: bytes) -> bulk_ingest.ManifestEntry:
    return bulk_ingest.ManifestEntry(
        source_path=path,
        size_bytes=len(content),
        content_sha256=sha256(content).hexdigest(),
        content_type="text/plain",
    )


def _actor(db: Session) -> User:
    actor = db.get(User, ADMIN_ID)
    assert actor is not None
    return actor


def _load_script() -> ModuleType:
    spec = spec_from_file_location("test_manage_files_bulk_ingest", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
