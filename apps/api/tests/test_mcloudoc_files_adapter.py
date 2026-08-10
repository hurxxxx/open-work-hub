from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import User, UserSystemRole, Workspace
from ai_do_api.domains.files import external_lifecycle
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
    FileManagerStorageCleanupJob,
)
from ai_do_api.domains.mcloudoc.contracts import ResolvedGrant
from ai_do_api.domains.mcloudoc import files_adapter
from ai_do_api.domains.mcloudoc.files_adapter import (
    McloudocFilesAdapterError,
    SqlAlchemyMcloudocFilesIngress,
)
from ai_do_api.domains.mcloudoc.models import (
    McloudocDocument,
    McloudocIngestRun,
    McloudocSource,
)
from ai_do_api.domains.mcloudoc.ports import FilesUpsertCommand
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.retrieval.models import RetrievalPartition


class _FakeSession:
    def __init__(self, *, source, corpus, actor, document) -> None:
        self.rows = {
            (McloudocSource, source.id): source,
            (FileManagerCorpus, corpus.id): corpus,
            (User, actor.id): actor,
            (McloudocDocument, document.id): document,
        }

    def get(self, model, identity):
        return self.rows.get((model, identity))


def test_adapter_maps_transport_neutral_change_to_private_files_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    captured: dict[str, object] = {}

    def _upsert(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            file=SimpleNamespace(id="file-1"),
            changed=True,
            acl_resolved=True,
        )

    monkeypatch.setattr(files_adapter, "upsert_external_file", _upsert)
    adapter = SqlAlchemyMcloudocFilesIngress(db, source_id="source-1")

    result = adapter.upsert(_command())

    assert result.file_id == "file-1"
    assert result.changed is True
    assert result.acl_resolved is True
    assert captured["corpus_id"] == "corpus-1"
    assert captured["source_kind"] == "mcloudoc"
    assert captured["source_id"] == "document-1"
    assert captured["external_id"] == "upstream/document/1"
    assert captured["expected_file_id"] is None
    assert captured["source_version"] == "opaque-revision"
    assert captured["raw_metadata"] == {"unmapped": {"value": 1}}
    assert captured["source_uri"] == "opaque-internal-locator"
    grants = captured["grants"]
    assert isinstance(grants, tuple)
    assert [(grant.grant_type, grant.target_id) for grant in grants] == [
        ("workspace", "workspace-1")
    ]


def test_adapter_propagates_files_current_principal_resolution_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    monkeypatch.setattr(
        files_adapter,
        "upsert_external_file",
        lambda *_args, **_kwargs: SimpleNamespace(
            file=SimpleNamespace(id="file-1"),
            changed=True,
            acl_resolved=False,
        ),
    )

    result = SqlAlchemyMcloudocFilesIngress(db, source_id="source-1").upsert(_command())

    assert result.acl_resolved is False


def test_adapter_rejects_scope_or_document_binding_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    monkeypatch.setattr(
        files_adapter,
        "upsert_external_file",
        lambda *_args, **_kwargs: pytest.fail("invalid binding must fail before Files mutation"),
    )
    adapter = SqlAlchemyMcloudocFilesIngress(db, source_id="source-1")

    with pytest.raises(McloudocFilesAdapterError, match="source_command_binding_mismatch"):
        adapter.upsert(_command(scope_id="workspace-other"))

    document = db.rows[(McloudocDocument, "document-1")]
    document.external_id = "different-upstream-id"
    with pytest.raises(McloudocFilesAdapterError, match="source_document_binding_mismatch"):
        adapter.upsert(_command())


def test_adapter_joins_real_files_lifecycle_for_upsert_quarantine_and_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            UserSystemRole.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            FileManagerFileAccessGrant.__table__,
            FileManagerStorageCleanupJob.__table__,
            McloudocSource.__table__,
            McloudocIngestRun.__table__,
            McloudocDocument.__table__,
        ],
    )
    stored: dict[str, bytes] = {}
    sync_operations: list[RagSyncOperation] = []

    def put_file_object(*, storage_key, content, size_bytes, content_type) -> None:
        del content_type
        stored[storage_key] = content.read(size_bytes)

    monkeypatch.setattr(external_lifecycle.file_storage, "put_file_object", put_file_object)
    monkeypatch.setattr(
        external_lifecycle,
        "enqueue_file_retrieval_sync",
        lambda _db, *, file, operation: sync_operations.append(operation),
    )

    with Session(engine) as db:
        _seed_integrated_adapter(db)
        adapter = SqlAlchemyMcloudocFilesIngress(db, source_id="source-1")

        result = adapter.upsert(_command())
        document = db.get(McloudocDocument, "document-1")
        assert document is not None
        document.file_id = result.file_id
        db.commit()

        file = db.get(FileManagerFile, result.file_id)
        metadata = db.get(FileManagerFileSourceMetadata, result.file_id)
        assert file is not None
        assert metadata is not None
        assert stored[file.storage_key] == b"searchable"
        assert metadata.source_kind == "mcloudoc"
        assert metadata.source_id == "document-1"
        assert metadata.external_id == "upstream/document/1"
        assert metadata.title == "Source title"
        assert (
            db.scalar(
                select(func.count())
                .select_from(FileManagerFileAccessGrant)
                .where(FileManagerFileAccessGrant.file_id == file.id)
            )
            == 1
        )

        assert adapter.quarantine(file_id=file.id, reason="upstream_acl_unresolved")
        db.commit()
        assert db.get(FileManagerFileSourceMetadata, file.id).acl_resolved is False  # type: ignore[union-attr]
        assert (
            db.scalar(
                select(func.count())
                .select_from(FileManagerFileAccessGrant)
                .where(FileManagerFileAccessGrant.file_id == file.id)
            )
            == 0
        )
        assert not adapter.quarantine(file_id=file.id, reason="same_state")

        assert adapter.delete(file_id=file.id, reason="upstream_delete")
        db.commit()
        assert db.get(FileManagerFile, file.id).deleted_at is not None  # type: ignore[union-attr]
        assert not adapter.delete(file_id=file.id, reason="duplicate_delete")

    assert sync_operations == [
        RagSyncOperation.UPSERT,
        RagSyncOperation.VISIBILITY_UPDATE,
        RagSyncOperation.DELETE,
    ]


def _seed_integrated_adapter(db: Session) -> None:
    db.add(Workspace(id="workspace-1", key="workspace-1", name="Workspace 1"))
    db.add(
        User(
            id="owner-1",
            login_id="owner-1",
            email="owner-1@example.test",
            full_name="Owner 1",
            password_hash="unused",
            status="active",
            login_blocked=False,
        )
    )
    db.flush()
    db.add(UserSystemRole(id="owner-platform-role", user_id="owner-1", role="platform_admin"))
    db.add(
        RetrievalPartition(
            id="11111111111111111111111111111111",
            source_namespace="files",
            managed_workspace_id="workspace-1",
            candidate_scope_kind="workspace",
            candidate_workspace_id="workspace-1",
            state="active",
            metadata_version=1,
            is_default_ingest=False,
        )
    )
    db.flush()
    db.add(
        FileManagerCorpus(
            id="corpus-1",
            name="mcloudoc corpus",
            managed_workspace_id="workspace-1",
            access_scope_kind="workspace",
            retrieval_partition_id="11111111111111111111111111111111",
            created_by_id="owner-1",
            source_managed=True,
            authorization_mode="explicit_grants",
        )
    )
    db.flush()
    db.add(
        McloudocSource(
            id="source-1",
            name="mcloudoc source",
            scope_type="workspace",
            scope_id="workspace-1",
            corpus_id="corpus-1",
            ingest_owner_id="owner-1",
            enabled=True,
        )
    )
    db.flush()
    db.add(
        McloudocDocument(
            id="document-1",
            source_id="source-1",
            external_id="upstream/document/1",
            external_id_sha256="0" * 64,
            status="quarantined",
            raw_metadata={},
            raw_acl=None,
            resolved_grants=[],
        )
    )
    db.commit()


def _session() -> _FakeSession:
    source = SimpleNamespace(
        id="source-1",
        enabled=True,
        corpus_id="corpus-1",
        ingest_owner_id="owner-1",
        scope_type="workspace",
        scope_id="workspace-1",
    )
    corpus = SimpleNamespace(
        id="corpus-1",
        source_managed=True,
        authorization_mode="explicit_grants",
        access_scope_kind="workspace",
        managed_workspace_id="workspace-1",
    )
    actor = SimpleNamespace(id="owner-1")
    document = SimpleNamespace(
        id="document-1",
        source_id="source-1",
        external_id="upstream/document/1",
        file_id=None,
    )
    return _FakeSession(
        source=source,
        corpus=corpus,
        actor=actor,
        document=document,
    )


def _command(**updates) -> FilesUpsertCommand:
    values = {
        "source_id": "source-1",
        "document_id": "document-1",
        "existing_file_id": None,
        "scope_type": "workspace",
        "scope_id": "workspace-1",
        "corpus_id": "corpus-1",
        "ingest_owner_id": "owner-1",
        "external_id": "upstream/document/1",
        "opaque_revision": "opaque-revision",
        "checksum": "opaque-checksum",
        "filename": "document.txt",
        "content_type": "text/plain",
        "content": b"searchable",
        "title": "Source title",
        "author": "Author",
        "authored_at": datetime(2026, 8, 1),
        "department": "Engineering",
        "document_type": "Technical note",
        "source_updated_at": datetime(2026, 8, 2),
        "source_uri": "opaque-internal-locator",
        "raw_metadata": {"unmapped": {"value": 1}},
        "resolved_grants": (ResolvedGrant(principal_type="workspace", principal_id="workspace-1"),),
    }
    values.update(updates)
    return FilesUpsertCommand(**values)
