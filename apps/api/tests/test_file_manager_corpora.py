from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, event, func, insert, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import (
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files import rag_projection as files_rag_projection
from open_work_hub_api.domains.files import search_projection as files_search_projection
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerCorpusTransitionAudit,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
    FileManagerFolder,
)
from open_work_hub_api.domains.files.source_access import (
    FileManagerSourceAccessAdapter,
    can_read_file,
    has_accessible_file,
)
from open_work_hub_api.domains.retrieval.models import RetrievalPartition
from open_work_hub_api.domains.retrieval.partitioning import ensure_default_partition
from open_work_hub_api.domains.rag.contracts import (
    RagProjection,
    RagScopeKind,
    RagVectorSearchHit,
)
from open_work_hub_api.domains.rag.query_projection import to_query_hit
from open_work_hub_api.domains.source_access.policy import SourceAclPolicy


WORKSPACE_A_ID = "workspace-a"
WORKSPACE_B_ID = "workspace-b"
DUAL_ADMIN_ID = "dual-admin"
SOURCE_ADMIN_ID = "source-admin"
PLATFORM_ADMIN_ID = "platform-admin"
WORKSPACE_B_MEMBER_ID = "workspace-b-member"


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
            Workspace.__table__,
            User.__table__,
            UserSystemRole.__table__,
            WorkspaceUserBinding.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerCorpusTransitionAudit.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            FileManagerFileAccessGrant.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(id=WORKSPACE_A_ID, key="workspace-a", name="Workspace A"),
                Workspace(id=WORKSPACE_B_ID, key="workspace-b", name="Workspace B"),
                _user(DUAL_ADMIN_ID),
                _user(SOURCE_ADMIN_ID),
                _user(PLATFORM_ADMIN_ID),
                _user(WORKSPACE_B_MEMBER_ID),
            ]
        )
        session.flush()
        session.add_all(
            [
                _workspace_binding("dual-admin-a", DUAL_ADMIN_ID, WORKSPACE_A_ID, "admin"),
                _workspace_binding("dual-admin-b", DUAL_ADMIN_ID, WORKSPACE_B_ID, "admin"),
                _workspace_binding("source-admin-a", SOURCE_ADMIN_ID, WORKSPACE_A_ID, "admin"),
                _workspace_binding(
                    "workspace-b-member",
                    WORKSPACE_B_MEMBER_ID,
                    WORKSPACE_B_ID,
                    "member",
                ),
                UserSystemRole(
                    id="platform-admin-role",
                    user_id=PLATFORM_ADMIN_ID,
                    role="platform_admin",
                ),
            ]
        )
        session.commit()
        yield session


def test_corpus_creation_uses_unique_non_default_managed_partitions(db: Session) -> None:
    workspace = _workspace(db, WORKSPACE_A_ID)
    admin = _user_row(db, DUAL_ADMIN_ID)

    first = files_service.create_file_corpus(
        db,
        workspace=workspace,
        user=admin,
        name="General Workspace archive",
    )
    second = files_service.create_file_corpus(
        db,
        workspace=workspace,
        user=admin,
        name="Engineering archive",
    )

    assert first.id != second.id
    assert first.retrieval_partition_id != second.retrieval_partition_id
    for corpus in (first, second):
        partition = db.get(RetrievalPartition, corpus.retrieval_partition_id)
        assert partition is not None
        assert partition.source_namespace == "files"
        assert partition.managed_workspace_id == workspace.id
        assert partition.candidate_scope_kind == "workspace"
        assert partition.candidate_workspace_id == workspace.id
        assert partition.is_default_ingest is False
        assert corpus.metadata_version == partition.metadata_version == 1

    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.create_file_corpus(
            db,
            workspace=_workspace(db, WORKSPACE_B_ID),
            user=_user_row(db, WORKSPACE_B_MEMBER_ID),
            name="Forbidden corpus",
        )

    assert FileManagerSourceAccessAdapter.allowed_transitions == (
        "corpus_scope_change",
        "corpus_workspace_transfer",
    )


def test_corpus_folder_and_file_inherit_partition_and_security_cohort(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upload_side_effects(monkeypatch)
    workspace = _workspace(db, WORKSPACE_A_ID)
    admin = _user_row(db, DUAL_ADMIN_ID)
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace,
        user=admin,
        name="One security cohort",
    )

    root = files_service.create_folder(
        db,
        workspace=workspace,
        user=admin,
        name="Root",
        parent_id=None,
        visibility="private",
        corpus_id=corpus.id,
    )
    child = files_service.create_folder(
        db,
        workspace=workspace,
        user=admin,
        name="Child",
        parent_id=root.id,
        visibility="private",
    )
    file = files_service.upload_file(
        db,
        workspace=workspace,
        user=admin,
        filename="source.txt",
        content_type="text/plain",
        content=BytesIO(b"source"),
        size_bytes=6,
        folder_id=child.id,
        visibility="private",
    )
    legacy_root = files_service.create_folder(
        db,
        workspace=workspace,
        user=admin,
        name="Legacy root",
        parent_id=None,
        visibility="private",
    )

    assert {root.corpus_id, child.corpus_id, file.corpus_id} == {corpus.id}
    assert {
        root.retrieval_partition_id,
        child.retrieval_partition_id,
        file.retrieval_partition_id,
    } == {corpus.retrieval_partition_id}
    # Child visibility is retained only for legacy rows. Corpus rows are one
    # source-owned security cohort and therefore use workspace visibility.
    assert root.visibility == child.visibility == file.visibility == "workspace"
    assert legacy_root.corpus_id is None
    assert legacy_root.retrieval_partition_id != corpus.retrieval_partition_id
    assert db.get(RetrievalPartition, legacy_root.retrieval_partition_id).is_default_ingest


def test_genuine_null_legacy_rows_remain_fully_mutation_compatible(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upload_side_effects(monkeypatch)
    workspace = _workspace(db, WORKSPACE_A_ID)
    admin = _user_row(db, DUAL_ADMIN_ID)
    parent = FileManagerFolder(
        id="genuine-null-legacy-parent",
        workspace_id=workspace.id,
        owner_id=admin.id,
        name="Unbound legacy parent",
        visibility="workspace",
    )
    legacy_file = FileManagerFile(
        id="genuine-null-legacy-file",
        workspace_id=workspace.id,
        folder_id=parent.id,
        owner_id=admin.id,
        filename="legacy-null.txt",
        content_type="text/plain",
        size_bytes=11,
        storage_key="files/genuine-null-legacy-file/legacy-null.txt",
        visibility="workspace",
    )
    db.add_all([parent, legacy_file])
    db.flush()
    assert parent.corpus_id is parent.retrieval_partition_id is None
    assert legacy_file.corpus_id is legacy_file.retrieval_partition_id is None

    child = files_service.create_folder(
        db,
        workspace=workspace,
        user=admin,
        name="Bound new child",
        parent_id=parent.id,
        visibility="workspace",
    )
    uploaded = files_service.upload_file(
        db,
        workspace=workspace,
        user=admin,
        filename="new-child.txt",
        content_type="text/plain",
        content=BytesIO(b"new child"),
        size_bytes=9,
        folder_id=parent.id,
        visibility="workspace",
    )
    default_partition = db.get(RetrievalPartition, child.retrieval_partition_id)
    assert default_partition is not None
    assert default_partition.is_default_ingest is True
    assert default_partition.source_namespace == "files"
    assert default_partition.managed_workspace_id == workspace.id
    assert default_partition.candidate_scope_kind == "workspace"
    assert default_partition.candidate_workspace_id == workspace.id
    assert uploaded.retrieval_partition_id == default_partition.id
    assert child.corpus_id is uploaded.corpus_id is None
    # Shared ingress locks must not opportunistically backfill the parent.
    assert parent.retrieval_partition_id is None

    files_service.update_folder(
        db,
        workspace=workspace,
        user=admin,
        folder_id=parent.id,
        name="Updated unbound legacy parent",
    )
    assert parent.name == "Updated unbound legacy parent"
    assert parent.retrieval_partition_id is None

    assert (
        files_service.delete_file(
            db,
            workspace=workspace,
            user=admin,
            file_id=legacy_file.id,
        )
        == legacy_file.storage_key
    )
    assert legacy_file.deleted_at is not None
    assert legacy_file.retrieval_partition_id is None

    deleted_storage_keys = files_service.delete_folder(
        db,
        workspace=workspace,
        user=admin,
        folder_id=parent.id,
    )
    assert deleted_storage_keys == [uploaded.storage_key]
    assert parent.deleted_at is not None
    assert child.deleted_at is not None
    assert uploaded.deleted_at is not None
    assert parent.retrieval_partition_id is None


def test_foreign_workspace_null_parent_does_not_create_a_partition_gate(db: Session) -> None:
    foreign_parent = FileManagerFolder(
        id="foreign-workspace-null-parent",
        workspace_id=WORKSPACE_B_ID,
        owner_id=DUAL_ADMIN_ID,
        name="Foreign NULL parent",
        visibility="workspace",
    )
    db.add(foreign_parent)
    db.flush()
    assert db.scalar(select(func.count()).select_from(RetrievalPartition)) == 0

    with pytest.raises(HTTPException) as error:
        files_service.create_folder(
            db,
            workspace=_workspace(db, WORKSPACE_A_ID),
            user=_user_row(db, DUAL_ADMIN_ID),
            name="Must not inspect the foreign parent",
            parent_id=foreign_parent.id,
            visibility="workspace",
        )
    assert error.value.status_code == 404
    assert db.scalar(select(func.count()).select_from(RetrievalPartition)) == 0
    assert foreign_parent.retrieval_partition_id is None


def test_legacy_bound_partition_must_be_workspace_default_files_gate(db: Session) -> None:
    workspace_a = _workspace(db, WORKSPACE_A_ID)
    admin = _user_row(db, DUAL_ADMIN_ID)
    managed_corpus = files_service.create_file_corpus(
        db,
        workspace=workspace_a,
        user=admin,
        name="Not a legacy default gate",
    )
    workspace_b_default = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id=WORKSPACE_B_ID,
    )
    malformed_parents = [
        FileManagerFolder(
            id="legacy-managed-partition-parent",
            workspace_id=workspace_a.id,
            retrieval_partition_id=managed_corpus.retrieval_partition_id,
            owner_id=admin.id,
            name="Managed partition mismatch",
            visibility="workspace",
        ),
        FileManagerFolder(
            id="legacy-foreign-default-parent",
            workspace_id=workspace_a.id,
            retrieval_partition_id=workspace_b_default.id,
            owner_id=admin.id,
            name="Workspace partition mismatch",
            visibility="workspace",
        ),
    ]
    db.add_all(malformed_parents)
    db.flush()

    for parent in malformed_parents:
        with pytest.raises(files_service.FileCorpusConflict, match="does not match"):
            files_service.update_folder(
                db,
                workspace=workspace_a,
                user=admin,
                folder_id=parent.id,
                name="Must remain unchanged",
            )
        assert parent.name != "Must remain unchanged"


def test_parent_and_explicit_corpus_must_match(db: Session) -> None:
    workspace = _workspace(db, WORKSPACE_A_ID)
    admin = _user_row(db, DUAL_ADMIN_ID)
    first = files_service.create_file_corpus(db, workspace=workspace, user=admin, name="First")
    second = files_service.create_file_corpus(db, workspace=workspace, user=admin, name="Second")
    parent = files_service.create_folder(
        db,
        workspace=workspace,
        user=admin,
        name="First root",
        parent_id=None,
        visibility="workspace",
        corpus_id=first.id,
    )

    with pytest.raises(files_service.FileCorpusConflict, match="parent folder corpus"):
        files_service.create_folder(
            db,
            workspace=workspace,
            user=admin,
            name="Mixed child",
            parent_id=parent.id,
            visibility="workspace",
            corpus_id=second.id,
        )


def test_company_publication_is_platform_admin_only_and_keeps_partition_identity(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upload_side_effects(monkeypatch)
    workspace_a = _workspace(db, WORKSPACE_A_ID)
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace_a,
        user=_user_row(db, DUAL_ADMIN_ID),
        name="Company handbook",
    )
    file = files_service.upload_file(
        db,
        workspace=workspace_a,
        user=_user_row(db, DUAL_ADMIN_ID),
        filename="handbook.txt",
        content_type="text/plain",
        content=BytesIO(b"handbook"),
        size_bytes=8,
        folder_id=None,
        visibility="private",
        corpus_id=corpus.id,
    )
    # Simulate a pre-corpus private child. Corpus ACL remains authoritative.
    file.visibility = "private"
    db.flush()
    original_partition_id = corpus.retrieval_partition_id

    with pytest.raises(files_service.FileCorpusAccessDenied, match="platform admin"):
        files_service.transition_file_corpus(
            db,
            corpus_id=corpus.id,
            actor=_user_row(db, SOURCE_ADMIN_ID),
            expected_metadata_version=1,
            access_scope_kind="company",
            reason="Publish handbook company-wide",
        )

    _install_transition_side_effect_canaries(monkeypatch)
    transitioned = files_service.transition_file_corpus(
        db,
        corpus_id=corpus.id,
        actor=_user_row(db, PLATFORM_ADMIN_ID),
        expected_metadata_version=1,
        access_scope_kind="company",
        reason="Approved company publication",
        request_id="request-company-publication",
    )

    partition = db.get(RetrievalPartition, original_partition_id)
    assert partition is not None
    assert transitioned.retrieval_partition_id == original_partition_id
    assert transitioned.access_scope_kind == "company"
    assert partition.candidate_scope_kind == "company"
    assert partition.candidate_workspace_id is None
    assert transitioned.metadata_version == partition.metadata_version == 2
    audit = db.scalar(
        select(FileManagerCorpusTransitionAudit).where(
            FileManagerCorpusTransitionAudit.corpus_id == corpus.id
        )
    )
    assert audit is not None
    assert audit.actor_id == PLATFORM_ADMIN_ID
    assert audit.reason == "Approved company publication"
    assert audit.request_id == "request-company-publication"
    assert audit.from_access_scope_kind == "workspace"
    assert audit.to_access_scope_kind == "company"
    assert (audit.from_metadata_version, audit.to_metadata_version) == (1, 2)

    policy = SourceAclPolicy.for_workspace(
        db,
        workspace=_workspace(db, WORKSPACE_B_ID),
        user=_user_row(db, WORKSPACE_B_MEMBER_ID),
    )
    assert can_read_file(policy, file.id) is True
    assert has_accessible_file(policy) is True
    assert (
        files_service.require_file_access(
            db,
            workspace=_workspace(db, WORKSPACE_B_ID),
            user=_user_row(db, WORKSPACE_B_MEMBER_ID),
            file_id=file.id,
        ).id
        == file.id
    )
    company_policy = SourceAclPolicy.for_company(
        db,
        user=_user_row(db, WORKSPACE_B_MEMBER_ID),
    )
    assert company_policy.authorize_many_rag_resources([("file_manager_file", file.id)]) == {
        ("file_manager_file", file.id)
    }
    assert has_accessible_file(company_policy) is True

    with pytest.raises(files_service.FileCorpusConflict, match="metadata version"):
        files_service.transition_file_corpus(
            db,
            corpus_id=corpus.id,
            actor=_user_row(db, PLATFORM_ADMIN_ID),
            expected_metadata_version=1,
            access_scope_kind="workspace",
            target_workspace_id=WORKSPACE_A_ID,
            reason="Stale request",
        )
    assert db.scalar(select(func.count()).select_from(FileManagerCorpusTransitionAudit)) == 1


def test_company_caller_without_company_corpus_is_fail_closed(db: Session) -> None:
    policy = SourceAclPolicy.for_company(
        db,
        user=_user_row(db, WORKSPACE_B_MEMBER_ID),
    )

    assert has_accessible_file(policy) is False
    assert policy.authorize_many_rag_resources([("file_manager_file", "missing-file")]) == set()


def test_corpus_scope_transition_hydrates_stale_search_and_rag_response_metadata(
    db: Session,
) -> None:
    workspace_a = _workspace(db, WORKSPACE_A_ID)
    workspace_b = _workspace(db, WORKSPACE_B_ID)
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace_a,
        user=_user_row(db, DUAL_ADMIN_ID),
        name="Hydrated company corpus",
    )
    file = FileManagerFile(
        id="hydrated-file",
        workspace_id=WORKSPACE_A_ID,
        corpus_id=corpus.id,
        retrieval_partition_id=corpus.retrieval_partition_id,
        owner_id=DUAL_ADMIN_ID,
        filename="hydrated.txt",
        content_type="text/plain",
        size_bytes=8,
        storage_key="files/hydrated-file/hydrated.txt",
        visibility="workspace",
    )
    db.add(file)
    db.flush()

    stale_search_row = {
        "workspace_id": WORKSPACE_A_ID,
        "retrieval_partition_id": corpus.retrieval_partition_id,
        "entity_type": "file",
        "entity_id": file.id,
        "visibility": "workspace",
        "deep_link": f"/w/workspace-a/files?file={file.id}",
        "metadata": {
            "resource_type": "file_manager_file",
            "resource_id": file.id,
            "source_kind": "files",
            "corpus_id": corpus.id,
            "managed_workspace_id": WORKSPACE_A_ID,
            "author": "stale author",
            "author_filter": "stale author",
            "department": "stale department",
            "document_type": "stale type",
            "authored_at": "2025-01-01T00:00:00",
        },
    }
    stale_rag_hit = RagVectorSearchHit(
        chunk_id=f"{file.id}:0",
        text="company evidence",
        score=1.0,
        projection=RagProjection(
            retrieval_partition_id=corpus.retrieval_partition_id,
            projection_version=1,
            scope_kind=RagScopeKind.WORKSPACE,
            workspace_id=WORKSPACE_A_ID,
            resource_type="file_manager_file",
            resource_id=file.id,
            source_kind="files",
            visibility_refs=[f"workspace:{WORKSPACE_A_ID}"],
            metadata={
                "origin_ref": f"/w/workspace-a/files?file={file.id}",
                "corpus_id": corpus.id,
                "managed_workspace_id": WORKSPACE_A_ID,
                "author": "stale author",
                "author_filter": "stale author",
                "department": "stale department",
                "document_type": "stale type",
                "authored_at": "2025-01-01T00:00:00",
            },
        ),
    )

    files_service.transition_file_corpus(
        db,
        corpus_id=corpus.id,
        actor=_user_row(db, PLATFORM_ADMIN_ID),
        expected_metadata_version=1,
        access_scope_kind="company",
        reason="Publish hydration fixture company-wide",
    )

    hydrated_rows = files_search_projection.hydrate_file_search_rows_from_source(
        db,
        rows=[stale_search_row],
        execution_workspace=workspace_b,
    )
    assert hydrated_rows[0]["workspace_id"] == WORKSPACE_B_ID
    assert hydrated_rows[0]["visibility"] == "company"
    assert hydrated_rows[0]["deep_link"] == (f"/w/workspace-b/files?file={file.id}")
    assert hydrated_rows[0]["metadata"]["access_scope_kind"] == "company"
    assert hydrated_rows[0]["metadata"]["managed_workspace_id"] == WORKSPACE_A_ID
    assert "author" not in hydrated_rows[0]["metadata"]
    assert "author_filter" not in hydrated_rows[0]["metadata"]
    assert "department" not in hydrated_rows[0]["metadata"]
    assert "document_type" not in hydrated_rows[0]["metadata"]
    assert "authored_at" not in hydrated_rows[0]["metadata"]

    hydrated_hits = files_rag_projection.hydrate_file_rag_hits_from_source(
        db,
        hits=[stale_rag_hit],
    )
    hydrated_projection = hydrated_hits[0].projection
    assert hydrated_projection.scope_kind == RagScopeKind.COMPANY
    assert hydrated_projection.workspace_id is None
    assert hydrated_projection.visibility_refs == ["company_public"]
    assert hydrated_projection.metadata["origin_ref"] == f"/files?file={file.id}"
    assert hydrated_projection.metadata["access_scope_kind"] == "company"
    assert "author" not in hydrated_projection.metadata
    assert "author_filter" not in hydrated_projection.metadata
    assert "department" not in hydrated_projection.metadata
    assert "document_type" not in hydrated_projection.metadata
    assert "authored_at" not in hydrated_projection.metadata
    assert to_query_hit(hydrated_hits[0]).acl_summary == ["company public"]

    files_service.transition_file_corpus(
        db,
        corpus_id=corpus.id,
        actor=_user_row(db, PLATFORM_ADMIN_ID),
        expected_metadata_version=2,
        access_scope_kind="workspace",
        target_workspace_id=WORKSPACE_A_ID,
        reason="Return hydration fixture to its managed workspace",
    )

    assert (
        files_search_projection.hydrate_file_search_rows_from_source(
            db,
            rows=hydrated_rows,
            execution_workspace=workspace_b,
        )
        == []
    )
    workspace_rows = files_search_projection.hydrate_file_search_rows_from_source(
        db,
        rows=hydrated_rows,
        execution_workspace=workspace_a,
    )
    assert workspace_rows[0]["workspace_id"] == WORKSPACE_A_ID
    assert workspace_rows[0]["visibility"] == "workspace"
    assert workspace_rows[0]["deep_link"] == f"/w/workspace-a/files?file={file.id}"
    workspace_hits = files_rag_projection.hydrate_file_rag_hits_from_source(
        db,
        hits=hydrated_hits,
    )
    assert workspace_hits[0].projection.scope_kind == RagScopeKind.WORKSPACE
    assert workspace_hits[0].projection.workspace_id == WORKSPACE_A_ID
    assert workspace_hits[0].projection.visibility_refs == [f"workspace:{WORKSPACE_A_ID}"]


def test_company_corpus_ingestion_requires_platform_admin(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upload_side_effects(monkeypatch)
    workspace = _workspace(db, WORKSPACE_A_ID)
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace,
        user=_user_row(db, DUAL_ADMIN_ID),
        name="Approved company corpus",
    )
    files_service.transition_file_corpus(
        db,
        corpus_id=corpus.id,
        actor=_user_row(db, PLATFORM_ADMIN_ID),
        expected_metadata_version=1,
        access_scope_kind="company",
        reason="Approve company publication boundary",
    )

    with pytest.raises(files_service.FileCorpusAccessDenied, match="platform admin"):
        files_service.upload_file(
            db,
            workspace=workspace,
            user=_user_row(db, SOURCE_ADMIN_ID),
            filename="unapproved.txt",
            content_type="text/plain",
            content=BytesIO(b"unapproved"),
            size_bytes=10,
            folder_id=None,
            visibility="workspace",
            corpus_id=corpus.id,
        )

    approved = files_service.upload_file(
        db,
        workspace=workspace,
        user=_user_row(db, PLATFORM_ADMIN_ID),
        filename="approved.txt",
        content_type="text/plain",
        content=BytesIO(b"approved"),
        size_bytes=8,
        folder_id=None,
        visibility="workspace",
        corpus_id=corpus.id,
    )
    assert approved.corpus_id == corpus.id


def test_workspace_transfer_requires_both_admin_roles_and_bulk_updates_children(
    db: Session,
) -> None:
    workspace_a = _workspace(db, WORKSPACE_A_ID)
    corpus = files_service.create_file_corpus(
        db,
        workspace=workspace_a,
        user=_user_row(db, DUAL_ADMIN_ID),
        name="Transferred corpus",
    )
    folder = FileManagerFolder(
        id="transfer-folder",
        workspace_id=WORKSPACE_A_ID,
        corpus_id=corpus.id,
        retrieval_partition_id=corpus.retrieval_partition_id,
        owner_id=DUAL_ADMIN_ID,
        name="Transferred folder",
        visibility="private",
    )
    file = FileManagerFile(
        id="transfer-file",
        workspace_id=WORKSPACE_A_ID,
        corpus_id=corpus.id,
        retrieval_partition_id=corpus.retrieval_partition_id,
        folder_id=folder.id,
        owner_id=DUAL_ADMIN_ID,
        filename="transfer.txt",
        content_type="text/plain",
        size_bytes=8,
        storage_key="files/transfer-file/transfer.txt",
        visibility="private",
    )
    db.add_all([folder, file])
    db.flush()

    with pytest.raises(files_service.FileCorpusAccessDenied, match="target workspace admin"):
        files_service.transition_file_corpus(
            db,
            corpus_id=corpus.id,
            actor=_user_row(db, SOURCE_ADMIN_ID),
            expected_metadata_version=1,
            access_scope_kind="workspace",
            target_workspace_id=WORKSPACE_B_ID,
            reason="Move ownership",
        )

    original_partition_id = corpus.retrieval_partition_id
    transitioned = files_service.transition_file_corpus(
        db,
        corpus_id=corpus.id,
        actor=_user_row(db, DUAL_ADMIN_ID),
        expected_metadata_version=1,
        access_scope_kind="workspace",
        target_workspace_id=WORKSPACE_B_ID,
        reason="Both workspace owners approved",
        request_id="request-workspace-transfer",
    )
    db.refresh(folder)
    db.refresh(file)
    partition = db.get(RetrievalPartition, original_partition_id)

    assert transitioned.retrieval_partition_id == original_partition_id
    assert transitioned.managed_workspace_id == WORKSPACE_B_ID
    assert partition is not None
    assert partition.managed_workspace_id == WORKSPACE_B_ID
    assert partition.candidate_workspace_id == WORKSPACE_B_ID
    assert folder.workspace_id == file.workspace_id == WORKSPACE_B_ID
    assert transitioned.metadata_version == partition.metadata_version == 2

    workspace_a_policy = SourceAclPolicy.for_workspace(
        db,
        workspace=workspace_a,
        user=_user_row(db, SOURCE_ADMIN_ID),
    )
    workspace_b_policy = SourceAclPolicy.for_workspace(
        db,
        workspace=_workspace(db, WORKSPACE_B_ID),
        user=_user_row(db, WORKSPACE_B_MEMBER_ID),
    )
    assert can_read_file(workspace_a_policy, file.id) is False
    assert can_read_file(workspace_b_policy, file.id) is True

    audit = db.scalar(
        select(FileManagerCorpusTransitionAudit).where(
            FileManagerCorpusTransitionAudit.corpus_id == corpus.id
        )
    )
    assert audit is not None
    assert audit.from_managed_workspace_id == WORKSPACE_A_ID
    assert audit.to_managed_workspace_id == WORKSPACE_B_ID

    db.expire_all()
    with pytest.raises(HTTPException) as stale_update:
        files_service.update_folder(
            db,
            workspace=workspace_a,
            user=_user_row(db, SOURCE_ADMIN_ID),
            folder_id=folder.id,
            name="Stale source mutation",
        )
    assert stale_update.value.status_code == 404

    with pytest.raises(HTTPException) as stale_delete:
        files_service.delete_file(
            db,
            workspace=workspace_a,
            user=_user_row(db, SOURCE_ADMIN_ID),
            file_id=file.id,
        )
    assert stale_delete.value.status_code == 404


def test_ten_thousand_file_workspace_transfer_uses_constant_database_work(
    db: Session,
) -> None:
    corpus = files_service.create_file_corpus(
        db,
        workspace=_workspace(db, WORKSPACE_A_ID),
        user=_user_row(db, DUAL_ADMIN_ID),
        name="Ten thousand file transition cohort",
    )
    db.execute(
        insert(FileManagerFile),
        [
            {
                "id": f"scale-file-{index:05d}",
                "workspace_id": WORKSPACE_A_ID,
                "corpus_id": corpus.id,
                "retrieval_partition_id": corpus.retrieval_partition_id,
                "owner_id": DUAL_ADMIN_ID,
                "filename": f"scale-{index:05d}.txt",
                "content_type": "text/plain",
                "size_bytes": 1,
                "storage_key": f"files/scale/{index:05d}",
                "visibility": "workspace",
                "extraction_status": "ready",
                "extraction_blocks": [],
                "extraction_metadata": {},
            }
            for index in range(10_000)
        ],
    )
    db.commit()
    stable_partition_id = corpus.retrieval_partition_id
    statements: list[str] = []

    def _count_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        transitioned = files_service.transition_file_corpus(
            db,
            corpus_id=corpus.id,
            actor=_user_row(db, DUAL_ADMIN_ID),
            expected_metadata_version=1,
            access_scope_kind="workspace",
            target_workspace_id=WORKSPACE_B_ID,
            reason="Prove metadata-only transition scales independently of file count",
        )
        db.commit()
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)

    assert transitioned.retrieval_partition_id == stable_partition_id
    assert transitioned.metadata_version == 2
    assert (
        db.scalar(
            select(func.count(FileManagerFile.id)).where(
                FileManagerFile.corpus_id == corpus.id,
                FileManagerFile.workspace_id == WORKSPACE_B_ID,
                FileManagerFile.retrieval_partition_id == stable_partition_id,
            )
        )
        == 10_000
    )
    # Authorization/locking/audit are fixed-cost and the source rows move with
    # one set-based UPDATE; there must be no per-file statement loop.
    assert len(statements) < 30
    assert sum("UPDATE file_manager_files" in statement for statement in statements) == 1


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.com",
        full_name=user_id.replace("-", " ").title(),
        password_hash="hash",
    )


def _workspace_binding(
    binding_id: str,
    user_id: str,
    workspace_id: str,
    role: str,
) -> WorkspaceUserBinding:
    return WorkspaceUserBinding(
        id=binding_id,
        user_id=user_id,
        workspace_id=workspace_id,
        role=role,
    )


def _workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    return workspace


def _user_row(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    assert user is not None
    return user


def _stub_upload_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(files_service.file_storage, "put_file_object", lambda **_kwargs: None)
    monkeypatch.setattr(
        files_service,
        "enqueue_file_retrieval_sync",
        lambda *_args, **_kwargs: None,
    )


def _install_transition_side_effect_canaries(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_side_effect(*_args, **_kwargs) -> None:
        raise AssertionError("corpus metadata transition invoked a derived/storage backend")

    monkeypatch.setattr(files_service.file_storage, "put_file_object", _unexpected_side_effect)
    monkeypatch.setattr(files_service, "enqueue_file_retrieval_sync", _unexpected_side_effect)
