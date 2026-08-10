from __future__ import annotations

from io import BytesIO
from hashlib import sha256
from types import SimpleNamespace
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import (
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.files import external_lifecycle, service as files_service
from ai_do_api.domains.files.external_access import authorize_explicit_file_ids
from ai_do_api.domains.files.external_lifecycle import ExternalFileGrant
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from ai_do_api.domains.files.source_access import (
    authorize_many_files,
    can_read_file,
    has_accessible_file,
)
from ai_do_api.domains.rag.contracts import RagSyncOperation
from ai_do_api.domains.retrieval.models import RetrievalPartition


WORKSPACE_ID = "workspace-source"
OTHER_WORKSPACE_ID = "workspace-other"
CORPUS_ID = "corpus-source"
PARTITION_ID = "11111111111111111111111111111111"
PLATFORM_ADMIN_ID = "platform-admin"
WORKSPACE_ADMIN_ID = "workspace-admin"
MEMBER_ID = "member"
OTHER_ID = "other-user"
ORG_MEMBER_ID = "org-member"
TEAM_MEMBER_ID = "team-member"
ORG_ID = "org-engineering"
TEAM_ID = "team-search"
OTHER_TEAM_ID = "team-other"


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
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            UserSystemRole.__table__,
            WorkspaceUserBinding.__table__,
            Team.__table__,
            TeamMember.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerFileSourceMetadata.__table__,
            FileManagerFileAccessGrant.__table__,
            FileManagerStorageCleanupJob.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(id=WORKSPACE_ID, key="source", name="Source"),
                Workspace(id=OTHER_WORKSPACE_ID, key="other", name="Other"),
                OrgUnit(
                    id=ORG_ID,
                    name="Engineering",
                    slug="engineering",
                    unit_type="division",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                _user(PLATFORM_ADMIN_ID),
                _user(WORKSPACE_ADMIN_ID),
                _user(MEMBER_ID),
                _user(OTHER_ID),
                _user(ORG_MEMBER_ID, primary_org_unit_id=ORG_ID),
                _user(TEAM_MEMBER_ID),
            ]
        )
        session.flush()
        session.add_all(
            [
                UserSystemRole(
                    id="platform-admin-role",
                    user_id=PLATFORM_ADMIN_ID,
                    role="platform_admin",
                ),
                _binding("workspace-admin-binding", WORKSPACE_ADMIN_ID, role="admin"),
                _binding("member-binding", MEMBER_ID),
                _binding("org-member-binding", ORG_MEMBER_ID),
                _binding("team-member-binding", TEAM_MEMBER_ID),
                Team(
                    id=TEAM_ID,
                    workspace_id=WORKSPACE_ID,
                    key="search",
                    name="Search",
                ),
                Team(
                    id=OTHER_TEAM_ID,
                    workspace_id=OTHER_WORKSPACE_ID,
                    key="other-search",
                    name="Other Search",
                ),
            ]
        )
        session.flush()
        session.add(
            TeamMember(
                id="team-member-link",
                team_id=TEAM_ID,
                user_id=TEAM_MEMBER_ID,
                role="member",
            )
        )
        session.add(
            TeamMember(
                id="other-team-member-link",
                team_id=OTHER_TEAM_ID,
                user_id=TEAM_MEMBER_ID,
                role="member",
            )
        )
        session.add(
            RetrievalPartition(
                id=PARTITION_ID,
                source_namespace="files",
                managed_workspace_id=WORKSPACE_ID,
                candidate_scope_kind="workspace",
                candidate_workspace_id=WORKSPACE_ID,
                candidate_user_id=None,
                state="active",
                metadata_version=1,
                is_default_ingest=False,
            )
        )
        session.flush()
        session.add(
            FileManagerCorpus(
                id=CORPUS_ID,
                name="External documents",
                managed_workspace_id=WORKSPACE_ID,
                access_scope_kind="workspace",
                retrieval_partition_id=PARTITION_ID,
                created_by_id=PLATFORM_ADMIN_ID,
                source_managed=True,
                authorization_mode="explicit_grants",
            )
        )
        session.commit()
        yield session


@pytest.fixture
def lifecycle_spies(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    stored: dict[str, bytes] = {}
    removed_storage_keys: list[str] = []
    sync_operations: list[RagSyncOperation] = []

    def put_file_object(*, storage_key, content, size_bytes, content_type) -> None:
        del content_type
        stored[storage_key] = content.read(size_bytes)

    def enqueue_sync(db, *, file, operation) -> None:
        del db, file
        sync_operations.append(operation)

    def remove_storage_object(storage_key: str) -> None:
        removed_storage_keys.append(storage_key)
        stored.pop(storage_key, None)

    monkeypatch.setattr(external_lifecycle.file_storage, "put_file_object", put_file_object)
    monkeypatch.setattr(external_lifecycle, "enqueue_file_retrieval_sync", enqueue_sync)
    monkeypatch.setattr(
        files_service,
        "remove_storage_object_immediately",
        remove_storage_object,
    )
    return SimpleNamespace(
        stored=stored,
        removed_storage_keys=removed_storage_keys,
        sync_operations=sync_operations,
    )


def test_existing_corpus_defaults_remain_cohort() -> None:
    corpus = FileManagerCorpus(
        id="legacy-corpus",
        name="Legacy",
        managed_workspace_id=WORKSPACE_ID,
        retrieval_partition_id=PARTITION_ID,
        created_by_id=PLATFORM_ADMIN_ID,
    )

    assert corpus.source_managed is None
    assert corpus.authorization_mode is None
    assert FileManagerCorpus.source_managed.default.arg is False
    assert FileManagerCorpus.authorization_mode.default.arg == "cohort"


def test_source_managed_corpus_scope_cannot_drift_from_source_binding(db: Session) -> None:
    with pytest.raises(files_service.FileCorpusConflict, match="scope is immutable"):
        files_service.transition_file_corpus(
            db,
            corpus_id=CORPUS_ID,
            actor=db.get(User, PLATFORM_ADMIN_ID),
            expected_metadata_version=1,
            access_scope_kind="company",
            reason="Source binding must remain stable",
        )


def test_explicit_acl_denies_workspace_admin_and_allows_platform_admin(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    result = _upsert(
        db,
        external_id="document-1",
        payload=b"first",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        raw_metadata={"department": "R&D", "upstream_acl": ["private-source-value"]},
    )
    db.commit()

    assert result.created and result.changed and result.acl_resolved
    assert lifecycle_spies.sync_operations == [RagSyncOperation.UPSERT]
    source_metadata = db.get(FileManagerFileSourceMetadata, result.file.id)
    assert source_metadata is not None
    assert source_metadata.source_kind == "external_document"
    assert source_metadata.source_id == "document-1"
    assert source_metadata.external_id_sha256 == sha256(b"document-1").hexdigest()
    assert source_metadata.source_id_sha256 == sha256(b"document-1").hexdigest()
    assert source_metadata.title == "Title document-1"
    assert source_metadata.author == "External Author"
    assert source_metadata.department == "Engineering"
    assert source_metadata.document_type == "technical"
    assert source_metadata.raw_metadata["department"] == "R&D"
    assert can_read_file(_policy(db, MEMBER_ID, "member"), result.file.id)
    assert not can_read_file(_policy(db, WORKSPACE_ADMIN_ID, "admin"), result.file.id)
    assert can_read_file(_policy(db, PLATFORM_ADMIN_ID, None), result.file.id)
    assert authorize_many_files(_policy(db, WORKSPACE_ADMIN_ID, "admin"), [result.file.id]) == set()
    assert has_accessible_file(_policy(db, MEMBER_ID, "member"))
    assert [
        file.id
        for file in files_service.list_accessible_files(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, MEMBER_ID),
            accessible_folder_ids=set(),
        )
    ] == [result.file.id]
    assert (
        files_service.list_accessible_files(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, WORKSPACE_ADMIN_ID),
            accessible_folder_ids=set(),
        )
        == []
    )
    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.upload_file(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, WORKSPACE_ADMIN_ID),
            filename="manual.txt",
            content_type="text/plain",
            content=BytesIO(b"manual"),
            size_bytes=6,
            folder_id=None,
            visibility="workspace",
            corpus_id=CORPUS_ID,
        )
    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.delete_file(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, WORKSPACE_ADMIN_ID),
            file_id=result.file.id,
        )

    corpus = db.get(FileManagerCorpus, CORPUS_ID)
    corpus.access_scope_kind = "company"
    db.flush()
    assert [
        file.id
        for file in files_service.list_accessible_files(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, MEMBER_ID),
            accessible_folder_ids=set(),
        )
    ] == [result.file.id]
    assert (
        files_service.list_accessible_files(
            db,
            workspace=db.get(Workspace, OTHER_WORKSPACE_ID),
            user=db.get(User, MEMBER_ID),
            accessible_folder_ids=set(),
        )
        == []
    )

    with pytest.raises(HTTPException) as denied:
        files_service.require_file_access(
            db,
            workspace=db.get(Workspace, WORKSPACE_ID),
            user=db.get(User, WORKSPACE_ADMIN_ID),
            file_id=result.file.id,
        )
    assert denied.value.status_code == 403


@pytest.mark.parametrize(
    ("grant", "user_id", "workspace_id"),
    [
        (ExternalFileGrant("company"), OTHER_ID, WORKSPACE_ID),
        (ExternalFileGrant("workspace", WORKSPACE_ID), MEMBER_ID, WORKSPACE_ID),
        (ExternalFileGrant("user", MEMBER_ID), MEMBER_ID, WORKSPACE_ID),
        (ExternalFileGrant("org_unit", ORG_ID), ORG_MEMBER_ID, WORKSPACE_ID),
        (ExternalFileGrant("team", TEAM_ID), TEAM_MEMBER_ID, WORKSPACE_ID),
    ],
)
def test_each_explicit_grant_type_uses_current_identity_state(
    db: Session,
    lifecycle_spies: SimpleNamespace,
    grant: ExternalFileGrant,
    user_id: str,
    workspace_id: str,
) -> None:
    del lifecycle_spies
    result = _upsert(
        db,
        external_id=f"grant-{grant.grant_type}",
        payload=str(grant.grant_type).encode(),
        grants=[grant],
    )
    db.commit()

    assert authorize_explicit_file_ids(
        db,
        file_ids=[result.file.id],
        user_id=user_id,
        workspace_id=workspace_id,
    ) == {result.file.id}
    assert authorize_explicit_file_ids(
        db,
        file_ids=[result.file.id],
        user_id=WORKSPACE_ADMIN_ID,
        workspace_id=workspace_id,
    ) == ({result.file.id} if grant.grant_type in {"company", "workspace"} else set())


def test_unresolved_or_empty_explicit_acl_fails_closed_without_partial_grants(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    del lifecycle_spies
    unresolved = _upsert(
        db,
        external_id="unresolved",
        payload=b"unresolved",
        grants=[
            ExternalFileGrant("user", MEMBER_ID),
            ExternalFileGrant("team", "missing-team"),
        ],
    )
    empty = _upsert(
        db,
        external_id="empty",
        payload=b"empty",
        grants=[],
    )
    db.commit()

    unresolved_metadata = db.get(FileManagerFileSourceMetadata, unresolved.file.id)
    assert unresolved_metadata is not None and not unresolved_metadata.acl_resolved
    assert (
        db.scalar(
            select(func.count(FileManagerFileAccessGrant.id)).where(
                FileManagerFileAccessGrant.file_id == unresolved.file.id
            )
        )
        == 0
    )
    assert not can_read_file(_policy(db, MEMBER_ID, "member"), unresolved.file.id)
    assert not can_read_file(_policy(db, MEMBER_ID, "member"), empty.file.id)
    assert can_read_file(_policy(db, PLATFORM_ADMIN_ID, None), unresolved.file.id)
    assert can_read_file(_policy(db, PLATFORM_ADMIN_ID, None), empty.file.id)

    wrong_workspace_team = _upsert(
        db,
        external_id="wrong-workspace-team",
        payload=b"wrong-team",
        grants=[ExternalFileGrant("team", OTHER_TEAM_ID)],
    )
    assert not wrong_workspace_team.acl_resolved
    assert not can_read_file(_policy(db, TEAM_MEMBER_ID, "member"), wrong_workspace_team.file.id)


def test_external_upsert_delete_and_revive_are_idempotent(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    created = _upsert(
        db,
        external_id="lifecycle",
        payload=b"version-one",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        source_version="1",
    )
    db.commit()
    first_key = created.file.storage_key
    assert lifecycle_spies.stored[first_key] == b"version-one"
    assert lifecycle_spies.removed_storage_keys == []

    unchanged = _upsert(
        db,
        external_id="lifecycle",
        payload=b"version-one",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        source_version="1",
    )
    assert not unchanged.created and not unchanged.changed
    assert lifecycle_spies.sync_operations == [RagSyncOperation.UPSERT]

    replaced = _upsert(
        db,
        external_id="lifecycle",
        payload=b"version-two",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        source_version="2",
    )
    db.commit()
    assert replaced.file.id == created.file.id
    assert replaced.obsolete_storage_keys == (first_key,)
    assert replaced.file.storage_key != first_key
    assert lifecycle_spies.stored[replaced.file.storage_key] == b"version-two"
    assert replaced.file.storage_key not in lifecycle_spies.removed_storage_keys

    deleted_storage_key = replaced.file.storage_key
    deleted = external_lifecycle.delete_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        file_id=replaced.file.id,
    )
    db.commit()
    assert deleted.changed
    assert deleted.obsolete_storage_keys == (deleted_storage_key,)
    cleanup_jobs = list(
        db.scalars(
            select(FileManagerStorageCleanupJob).order_by(
                FileManagerStorageCleanupJob.created_at.asc()
            )
        )
    )
    assert [job.storage_key for job in cleanup_jobs] == [
        first_key,
        deleted_storage_key,
    ]
    assert not can_read_file(_policy(db, MEMBER_ID, "member"), replaced.file.id)
    assert not external_lifecycle.delete_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        external_id="lifecycle",
    ).changed

    revived = _upsert(
        db,
        external_id="lifecycle",
        payload=b"version-two",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        source_version="2",
    )
    db.commit()
    assert revived.file.id == created.file.id
    assert revived.changed and not revived.created
    assert revived.file.deleted_at is None
    assert revived.file.storage_key != deleted_storage_key
    assert all(
        job.storage_key != revived.file.storage_key
        for job in db.scalars(select(FileManagerStorageCleanupJob))
    )
    assert can_read_file(_policy(db, MEMBER_ID, "member"), revived.file.id)
    assert lifecycle_spies.sync_operations == [
        RagSyncOperation.UPSERT,
        RagSyncOperation.UPSERT,
        RagSyncOperation.DELETE,
        RagSyncOperation.UPSERT,
    ]


def test_acl_only_change_uses_visibility_event_and_quarantine_is_idempotent(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    created = _upsert(
        db,
        external_id="acl-change",
        payload=b"same-content",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
    )
    db.commit()

    acl_changed = _upsert(
        db,
        external_id="acl-change",
        payload=b"same-content",
        grants=[ExternalFileGrant("user", OTHER_ID)],
    )
    db.commit()
    assert acl_changed.changed
    assert lifecycle_spies.sync_operations[-1] == RagSyncOperation.VISIBILITY_UPDATE
    assert not can_read_file(_policy(db, MEMBER_ID, "member"), created.file.id)

    assert external_lifecycle.quarantine_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        file_id=created.file.id,
    )
    db.commit()
    assert lifecycle_spies.sync_operations[-1] == RagSyncOperation.VISIBILITY_UPDATE
    assert not external_lifecycle.quarantine_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        external_id="acl-change",
    )
    assert can_read_file(_policy(db, PLATFORM_ADMIN_ID, None), created.file.id)


def test_typed_metadata_change_reuses_extraction_and_raw_metadata_is_bounded(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    created = _upsert(
        db,
        external_id="typed-change",
        payload=b"same-content",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        title="Old title",
    )
    db.commit()
    created.file.extraction_status = "ready"
    created.file.extraction_content_checksum = "derived-checksum"
    created.file.extraction_text = "already extracted"
    db.commit()

    changed = _upsert(
        db,
        external_id="typed-change",
        payload=b"same-content",
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        title="New title",
    )
    db.commit()
    assert changed.changed
    assert lifecycle_spies.sync_operations[-1] == RagSyncOperation.UPSERT
    assert changed.file.extraction_status == "ready"
    assert changed.file.extraction_text == "already extracted"

    timestamp_changed = external_lifecycle.upsert_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        external_id="typed-change",
        source_kind="external_document",
        source_id="typed-change",
        filename="typed-change.txt",
        content_type="text/plain",
        content=BytesIO(b"same-content"),
        size_bytes=len(b"same-content"),
        grants=[ExternalFileGrant("user", MEMBER_ID)],
        source_updated_at=datetime(2026, 8, 4, 12, 30),
        title="New title",
        author="External Author",
        department="Engineering",
        document_type="technical",
    )
    assert timestamp_changed.changed
    assert lifecycle_spies.sync_operations[-1] == RagSyncOperation.UPSERT

    with pytest.raises(external_lifecycle.ExternalFileContractError):
        _upsert(
            db,
            external_id="oversized-metadata",
            payload=b"x",
            grants=[ExternalFileGrant("company")],
            raw_metadata={"payload": "x" * (64 * 1024)},
        )


def test_external_upsert_rolls_back_joined_uow_and_removes_object_on_outbox_failure(
    db: Session,
    lifecycle_spies: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_enqueue(*_args, **_kwargs) -> None:
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(external_lifecycle, "enqueue_file_retrieval_sync", fail_enqueue)
    with pytest.raises(
        external_lifecycle.ExternalFileLifecycleError,
        match="external file upsert failed",
    ):
        _upsert(
            db,
            external_id="outbox-failure",
            payload=b"must-be-compensated",
            grants=[ExternalFileGrant("company")],
        )

    assert lifecycle_spies.stored == {}
    assert db.scalar(select(func.count()).select_from(FileManagerFile)) == 0
    assert db.scalar(select(func.count()).select_from(FileManagerFileSourceMetadata)) == 0
    assert db.scalar(select(func.count()).select_from(FileManagerFileAccessGrant)) == 0


def test_external_upsert_removes_object_when_storage_writes_then_raises(
    db: Session,
    lifecycle_spies: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def write_then_fail(*, storage_key, content, size_bytes, content_type) -> None:
        del content_type
        lifecycle_spies.stored[storage_key] = content.read(size_bytes)
        raise TimeoutError("storage response lost after write")

    monkeypatch.setattr(external_lifecycle.file_storage, "put_file_object", write_then_fail)

    with pytest.raises(
        external_lifecycle.ExternalFileLifecycleError,
        match="external file upsert failed",
    ):
        _upsert(
            db,
            external_id="storage-ambiguous-failure",
            payload=b"must-be-compensated",
            grants=[ExternalFileGrant("company")],
        )

    assert lifecycle_spies.stored == {}
    assert len(lifecycle_spies.removed_storage_keys) == 1
    assert db.scalar(select(func.count()).select_from(FileManagerFile)) == 0
    assert db.scalar(select(func.count()).select_from(FileManagerFileSourceMetadata)) == 0
    assert db.scalar(select(func.count()).select_from(FileManagerFileAccessGrant)) == 0


def test_external_upsert_removes_object_when_caller_rolls_back(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    result = _upsert(
        db,
        external_id="outer-rollback",
        payload=b"must-not-survive",
        grants=[ExternalFileGrant("company")],
    )
    storage_key = result.file.storage_key
    assert lifecycle_spies.stored[storage_key] == b"must-not-survive"

    db.rollback()

    assert lifecycle_spies.stored == {}
    assert lifecycle_spies.removed_storage_keys == [storage_key]
    assert db.scalar(select(func.count()).select_from(FileManagerFile)) == 0


def test_external_upsert_removes_object_after_outer_commit_failure(
    db: Session,
    lifecycle_spies: SimpleNamespace,
) -> None:
    result = _upsert(
        db,
        external_id="commit-failure",
        payload=b"must-be-compensated",
        grants=[ExternalFileGrant("company")],
    )
    storage_key = result.file.storage_key

    def fail_commit(_connection) -> None:
        raise RuntimeError("database commit failed")

    event.listen(db.get_bind(), "commit", fail_commit, once=True)
    with pytest.raises(RuntimeError, match="database commit failed"):
        try:
            db.commit()
        except Exception:
            # SQLAlchemy requires callers to roll back a failed commit before
            # the Session can be reused. Compensation follows that contract.
            db.rollback()
            raise

    assert lifecycle_spies.stored == {}
    assert lifecycle_spies.removed_storage_keys == [storage_key]
    assert db.scalar(select(func.count()).select_from(FileManagerFile)) == 0


def test_external_lifecycle_requires_explicit_corpus_and_immutable_source_identity(
    db: Session,
    lifecycle_spies: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del lifecycle_spies
    corpus = db.get(FileManagerCorpus, CORPUS_ID)
    corpus.authorization_mode = "cohort"
    db.flush()
    with pytest.raises(external_lifecycle.ExternalFileCorpusConflict):
        _upsert(
            db,
            external_id="wrong-mode",
            payload=b"x",
            grants=[ExternalFileGrant("company")],
        )
    db.rollback()

    monkeypatch.setattr(external_lifecycle, "_identity_sha256", lambda _value: "f" * 64)
    created = _upsert(
        db,
        external_id="identity-one",
        source_id="stable-source-id",
        payload=b"one",
        grants=[ExternalFileGrant("company")],
    )
    db.commit()
    with pytest.raises(external_lifecycle.ExternalFileCorpusConflict):
        _upsert(
            db,
            external_id="identity-one",
            source_id="stable-source-id",
            expected_file_id="different-file-id",
            payload=b"one",
            grants=[ExternalFileGrant("company")],
        )
    with pytest.raises(external_lifecycle.ExternalFileCorpusConflict):
        _upsert(
            db,
            external_id="identity-two",
            source_id="different-source-id",
            payload=b"two",
            grants=[ExternalFileGrant("company")],
        )
    assert created.file.id


def _upsert(
    db: Session,
    *,
    external_id: str,
    payload: bytes,
    grants: list[ExternalFileGrant],
    source_version: str | None = None,
    raw_metadata: dict[str, object] | None = None,
    title: str | None = None,
    source_id: str | None = None,
    expected_file_id: str | None = None,
):
    return external_lifecycle.upsert_external_file(
        db,
        actor=db.get(User, PLATFORM_ADMIN_ID),
        corpus_id=CORPUS_ID,
        external_id=external_id,
        source_kind="external_document",
        source_id=source_id or external_id,
        expected_file_id=expected_file_id,
        filename=f"{external_id}.txt",
        content_type="text/plain",
        content=BytesIO(payload),
        size_bytes=len(payload),
        grants=grants,
        source_version=source_version,
        title=title or f"Title {external_id}",
        author="External Author",
        department="Engineering",
        document_type="technical",
        raw_metadata=raw_metadata,
    )


def _policy(db: Session, user_id: str, workspace_role: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        db=db,
        workspace=db.get(Workspace, WORKSPACE_ID),
        user=db.get(User, user_id),
        workspace_role=workspace_role,
    )


def _binding(binding_id: str, user_id: str, *, role: str = "member"):
    return WorkspaceUserBinding(
        id=binding_id,
        workspace_id=WORKSPACE_ID,
        user_id=user_id,
        role=role,
    )


def _user(user_id: str, *, primary_org_unit_id: str | None = None) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.test",
        full_name=user_id,
        password_hash="unused",
        status="active",
        login_blocked=False,
        primary_org_unit_id=primary_org_unit_id,
    )
