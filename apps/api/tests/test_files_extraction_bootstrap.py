from __future__ import annotations

from contextlib import nullcontext
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.files import rag_projection, rag_sync
from open_work_hub_api.domains.files.extraction_bootstrap import (
    bootstrap_file_extraction_artifacts,
)
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileSourceMetadata,
    FileManagerFolder,
)
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


_PARTITION_ID = "3b348bd8-7c75-48a1-a5c7-3c9e9a77fd11"
_RUNNER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "manage_files_retrieval_generation.py"
)


def _load_runner_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "test_files_extraction_bootstrap_runner_script",
        _RUNNER_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ExtractionRuntime:
    ocr_provider_name = "test-ocr"

    def extract_text(self, **_kwargs) -> str:
        raise AssertionError("plain text bootstrap must not invoke OCR")


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            SearchIndexJob.__table__,
            RagSyncJob.__table__,
        ],
    )
    session = Session(engine)
    session.add_all(
        [
            Workspace(
                id="workspace-1",
                key="workspace-1",
                name="Workspace 1",
                description="",
                active=True,
            ),
            User(
                id="user-1",
                login_id="user-1",
                email="user-1@example.com",
                full_name="User 1",
                password_hash="hash",
            ),
            RetrievalPartition(
                id=_PARTITION_ID,
                source_namespace="files",
                managed_workspace_id="workspace-1",
                candidate_scope_kind="workspace",
                candidate_workspace_id="workspace-1",
                is_default_ingest=False,
            ),
        ]
    )
    session.flush()
    return session


def _pending_file(file_id: str) -> FileManagerFile:
    return FileManagerFile(
        id=file_id,
        workspace_id="workspace-1",
        retrieval_partition_id=_PARTITION_ID,
        owner_id="user-1",
        filename=f"{file_id}.txt",
        content_type="text/plain",
        size_bytes=64,
        storage_key=f"files/workspace-1/{file_id}.txt",
        visibility="workspace",
        extraction_status="pending",
        extraction_blocks=[],
        extraction_metadata={},
    )


def test_gate_closed_bootstrap_extracts_and_refences_source_without_backend_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        file = _pending_file("file-1")
        db.add(file)
        db.flush()
        monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", False)
        rag_sync.enqueue_file_retrieval_sync(
            db,
            file=file,
            operation=RagSyncOperation.UPSERT,
        )
        first_head = db.get(
            RetrievalProjectionHead,
            (FILE_MANAGER_FILE_RESOURCE_TYPE, file.id),
        )
        assert first_head is not None and first_head.content_checksum is None
        monkeypatch.setattr(
            rag_projection,
            "read_file_content",
            lambda _file: "브레이크 제어기 시험 기준".encode(),
        )

        result = bootstrap_file_extraction_artifacts(
            db,
            after_file_id=None,
            limit=10,
            extraction_runtime=_ExtractionRuntime(),
        )

        stored = db.get(FileManagerFile, file.id, populate_existing=True)
        head = db.get(
            RetrievalProjectionHead,
            (FILE_MANAGER_FILE_RESOURCE_TYPE, file.id),
            populate_existing=True,
        )
        assert result.complete is True
        assert result.scanned_files == result.ready_files == 1
        assert result.unsupported_files == result.failed_files == 0
        assert result.recorded_events == 1
        assert stored is not None and stored.extraction_status == "ready"
        assert stored.extraction_content_checksum
        assert head is not None
        assert head.projection_version == 2
        assert head.content_checksum == stored.extraction_content_checksum
        assert db.scalar(select(SearchIndexJob)) is None
        assert db.scalar(select(RagSyncJob)) is None
    finally:
        db.close()


def test_bootstrap_is_resumable_and_does_not_duplicate_current_ready_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        db.add_all([_pending_file("file-1"), _pending_file("file-2")])
        db.flush()
        monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", False)
        monkeypatch.setattr(
            rag_projection,
            "read_file_content",
            lambda file: f"{file.id} 접근 권한 기준".encode(),
        )

        first = bootstrap_file_extraction_artifacts(
            db,
            after_file_id=None,
            limit=1,
            extraction_runtime=_ExtractionRuntime(),
        )
        second = bootstrap_file_extraction_artifacts(
            db,
            after_file_id=first.next_file_id,
            limit=1,
            extraction_runtime=_ExtractionRuntime(),
        )
        event_count = int(
            db.scalar(
                select(func.count())
                .select_from(RetrievalProjectionEvent)
                .where(RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE)
            )
            or 0
        )
        repeated = bootstrap_file_extraction_artifacts(
            db,
            after_file_id=None,
            limit=10,
            extraction_runtime=_ExtractionRuntime(),
        )

        assert first.complete is False and first.next_file_id == "file-1"
        assert second.complete is True and second.next_file_id == "file-2"
        assert repeated.ready_files == 2
        assert repeated.recorded_events == 0
        assert event_count == 2
        assert (
            int(
                db.scalar(
                    select(func.count())
                    .select_from(RetrievalProjectionEvent)
                    .where(
                        RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
                    )
                )
                or 0
            )
            == event_count
        )
    finally:
        db.close()


def test_bootstrap_tombstones_unsupported_source_and_keeps_failure_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        unsupported = _pending_file("file-unsupported")
        failed = _pending_file("file-failed")
        db.add_all([failed, unsupported])
        db.flush()
        monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", False)

        def content(file: FileManagerFile) -> bytes:
            if file.id == unsupported.id:
                return b""
            raise RuntimeError("storage temporarily unavailable")

        monkeypatch.setattr(rag_projection, "read_file_content", content)

        result = bootstrap_file_extraction_artifacts(
            db,
            after_file_id=None,
            limit=10,
            extraction_runtime=_ExtractionRuntime(),
        )

        failed = db.get(FileManagerFile, "file-failed", populate_existing=True)
        unsupported = db.get(FileManagerFile, "file-unsupported", populate_existing=True)
        unsupported_head = db.get(
            RetrievalProjectionHead,
            (FILE_MANAGER_FILE_RESOURCE_TYPE, "file-unsupported"),
        )
        assert result.failed_files == 1
        assert result.unsupported_files == 1
        assert failed is not None and failed.extraction_status == "failed"
        assert unsupported is not None and unsupported.extraction_status == "unsupported"
        assert unsupported_head is not None
        assert unsupported_head.desired_state == "deleted"
        assert unsupported_head.content_checksum is None
        assert db.scalar(select(SearchIndexJob)) is None
        assert db.scalar(select(RagSyncJob)) is None

        monkeypatch.setattr(
            rag_projection,
            "read_file_content",
            lambda _file: pytest.fail("unsupported source must not be re-opened"),
        )
        repeated = bootstrap_file_extraction_artifacts(
            db,
            after_file_id="file-failed",
            limit=10,
            extraction_runtime=_ExtractionRuntime(),
        )
        assert repeated.unsupported_files == 1
        assert repeated.recorded_events == 0
    finally:
        db.close()


def test_bootstrap_refuses_to_run_when_files_retrieval_gate_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    try:
        monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)

        with pytest.raises(ValueError, match="disabled gate"):
            bootstrap_file_extraction_artifacts(
                db,
                after_file_id=None,
                limit=10,
                extraction_runtime=_ExtractionRuntime(),
            )
    finally:
        db.close()


def test_cli_requires_distinct_production_confirmation_before_extraction_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    settings = SimpleNamespace(environment="production", files_retrieval_enabled=False)
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    monkeypatch.setattr(
        script,
        "RagProviderFactory",
        lambda _settings: pytest.fail("confirmation must precede OCR provider construction"),
        raising=False,
    )

    exit_code = script.main(
        [
            "bootstrap-extraction",
            "--confirm-writes-quiesced",
            "--confirm-workers-stopped",
            "--confirm-operator-gate-disabled",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == "status=failed reason=production_confirmation_required"


def test_cli_exact_production_confirmation_allows_provider_free_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    settings = SimpleNamespace(environment="production", files_retrieval_enabled=False)
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    monkeypatch.setattr(
        script,
        "RagProviderFactory",
        lambda _settings: pytest.fail("dry-run must not construct an OCR provider"),
    )
    monkeypatch.setattr(
        script,
        "FilesPhysicalGenerationBackends",
        lambda _settings: pytest.fail("dry-run must not construct retrieval backends"),
    )

    exit_code = script.main(
        [
            "bootstrap-extraction",
            "--confirm-writes-quiesced",
            "--confirm-workers-stopped",
            "--confirm-operator-gate-disabled",
            "--confirm-production-extraction",
            "bootstrap-files-extraction",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.strip() == "status=ok state=extraction-planned dry_run=1"


def test_cli_commits_failed_artifact_state_but_returns_nonzero_batch_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_runner_script()
    settings = SimpleNamespace(environment="development", files_retrieval_enabled=False)
    monkeypatch.setattr(script, "get_settings", lambda: settings)
    monkeypatch.setattr(
        script,
        "RagProviderFactory",
        lambda _settings: SimpleNamespace(build_ocr=lambda: None),
    )
    monkeypatch.setattr(
        script,
        "get_session_factory",
        lambda: SimpleNamespace(begin=lambda: nullcontext(SimpleNamespace())),
    )
    monkeypatch.setattr(
        script,
        "bootstrap_file_extraction_artifacts",
        lambda *_args, **_kwargs: SimpleNamespace(
            next_file_id="file-25",
            scanned_files=25,
            ready_files=24,
            unsupported_files=0,
            failed_files=1,
            recorded_events=24,
            complete=False,
        ),
    )

    exit_code = script.main(
        [
            "bootstrap-extraction",
            "--confirm-writes-quiesced",
            "--confirm-workers-stopped",
            "--confirm-operator-gate-disabled",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "status=failed reason=extraction_batch_incomplete"
        " scanned_files=25 ready_files=24 unsupported_files=0 failed_files=1"
        " recorded_events=24 complete=0 next_file_id=file-25"
    )
