from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from company_admission_fixture import company_authority_tables, seed_company_app_access
from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import AuditLog, CompanyAppControl, User, UserSystemRole
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from open_work_hub_api.domains.files.source_access import can_read_file
from open_work_hub_api.domains.retrieval.models import RetrievalPartition
from open_work_hub_api.domains.source_access.policy import SourceAclPolicy


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            *company_authority_tables(),
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            FileManagerFileAccessGrant.__table__,
            FileManagerFileSourceMetadata.__table__,
            FileManagerStorageCleanupJob.__table__,
        ],
    )
    monkeypatch.setattr(files_service, "enqueue_file_retrieval_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(files_service.file_storage, "put_file_object", lambda **kwargs: None)
    with Session(engine) as session:
        seed_company_app_access(session, ("files",))
        session.add_all(
            [
                User(
                    id=user_id,
                    login_id=user_id,
                    email=f"{user_id}@example.test",
                    full_name=user_id,
                    password_hash="unused",
                )
                for user_id in ("admin", "owner", "reader")
            ]
        )
        session.add(UserSystemRole(id="platform-role", user_id="admin", role="platform_admin"))
        session.commit()
        yield session
    engine.dispose()


def _folder(db, *, owner="admin", corpus_id=None, parent_id=None, acknowledge=True):
    return files_service.create_folder(
        db,
        user=db.get(User, owner),
        name="Folder",
        parent_id=parent_id,
        visibility="private",
        corpus_id=corpus_id,
        company_admin_read_acknowledged=acknowledge,
    )


def _file(
    db, *, owner="admin", corpus_id=None, folder_id=None, visibility="private", acknowledge=True
):
    return files_service.upload_file(
        db,
        user=db.get(User, owner),
        filename="report.txt",
        content_type="text/plain",
        content=BytesIO(b"test"),
        size_bytes=4,
        folder_id=folder_id,
        visibility=visibility,
        corpus_id=corpus_id,
        company_admin_read_acknowledged=acknowledge,
    )


def _policy(db, user_id):
    return SourceAclPolicy.for_user(db, user=db.get(User, user_id))


def test_corpora_have_distinct_stable_company_partitions(db):
    admin = db.get(User, "admin")
    first = files_service.create_file_corpus(db, user=admin, name="Finance")
    second = files_service.create_file_corpus(db, user=admin, name="Engineering")
    assert first.id != second.id
    assert first.retrieval_partition_id != second.retrieval_partition_id
    assert {item.id for item in files_service.list_managed_file_corpora(db, user=admin)} == {
        first.id,
        second.id,
    }
    for corpus in (first, second):
        partition = db.get(RetrievalPartition, corpus.retrieval_partition_id)
        assert corpus.access_scope_kind == partition.candidate_scope_kind == "company"
        assert corpus.metadata_version == partition.metadata_version == 1
        assert not partition.is_default_ingest
        assert partition.candidate_user_id is None
        assert not hasattr(corpus, "managed_workspace_id")
        assert not hasattr(partition, "candidate_workspace_id")


@pytest.mark.parametrize("revocation", ["role", "blocked", "inactive", "master"])
def test_corpus_management_rechecks_current_admin_authority(db, revocation):
    admin = db.get(User, "admin")
    files_service.create_file_corpus(db, user=admin, name="Before revocation")
    mutation = {
        "role": delete(UserSystemRole),
        "blocked": update(User).where(User.id == "admin").values(login_blocked=True),
        "inactive": update(User).where(User.id == "admin").values(status="inactive"),
        "master": update(CompanyAppControl).values(enabled=False),
    }[revocation]
    db.execute(mutation)
    db.commit()
    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.create_file_corpus(db, user=admin, name="Denied")
    with pytest.raises(files_service.FileCorpusAccessDenied):
        files_service.list_managed_file_corpora(db, user=admin)


def test_corpus_children_inherit_company_ownership_and_partition_with_acknowledgment(db):
    corpus = files_service.create_file_corpus(db, user=db.get(User, "admin"), name="Records")
    with pytest.raises(HTTPException) as denied:
        _folder(db, corpus_id=corpus.id, acknowledge=False)
    assert denied.value.status_code == 409
    parent = _folder(db, corpus_id=corpus.id)
    child = _folder(db, parent_id=parent.id)
    file = _file(db, folder_id=child.id)
    assert {parent.corpus_id, child.corpus_id, file.corpus_id} == {corpus.id}
    assert {
        parent.retrieval_partition_id,
        child.retrieval_partition_id,
        file.retrieval_partition_id,
    } == {corpus.retrieval_partition_id}
    assert parent.visibility == child.visibility == file.visibility == "company"
    assert db.scalars(select(AuditLog).where(AuditLog.action == "content.publish_to_company")).all()
    assert can_read_file(_policy(db, "reader"), file.id)


def test_corpus_parent_cannot_accept_a_different_corpus(db):
    admin = db.get(User, "admin")
    first = files_service.create_file_corpus(db, user=admin, name="First")
    second = files_service.create_file_corpus(db, user=admin, name="Second")
    parent = _folder(db, corpus_id=first.id)
    with pytest.raises(files_service.FileCorpusConflict, match="match the parent"):
        _folder(db, parent_id=parent.id, corpus_id=second.id)
    with pytest.raises(files_service.FileCorpusConflict, match="match the parent"):
        _file(db, folder_id=parent.id, corpus_id=second.id)


def test_non_admin_cannot_ingest_company_corpus_even_with_app_admission(db):
    corpus = files_service.create_file_corpus(db, user=db.get(User, "admin"), name="Records")
    with pytest.raises(files_service.FileCorpusAccessDenied):
        _folder(db, owner="owner", corpus_id=corpus.id)
    with pytest.raises(files_service.FileCorpusAccessDenied):
        _file(db, owner="owner", corpus_id=corpus.id)


def test_company_partition_never_grants_private_file_access_even_to_admin(db):
    file = _file(db, owner="owner")
    partition = db.get(RetrievalPartition, file.retrieval_partition_id)
    assert partition.candidate_scope_kind == "company"
    assert can_read_file(_policy(db, "owner"), file.id)
    for user_id in ("admin", "reader"):
        assert not can_read_file(_policy(db, user_id), file.id)
        with pytest.raises(HTTPException):
            files_service.require_file_access(db, user=db.get(User, user_id), file_id=file.id)
        with pytest.raises(HTTPException):
            files_service.delete_file(db, user=db.get(User, user_id), file_id=file.id)


def test_company_file_read_audience_does_not_inherit_owner_mutations(db):
    file = _file(db, owner="owner", visibility="company")
    for user_id in ("reader", "admin"):
        assert can_read_file(_policy(db, user_id), file.id)
        with pytest.raises(HTTPException):
            files_service.delete_file(db, user=db.get(User, user_id), file_id=file.id)


def test_corpus_rejects_corrupted_partition_binding_before_ingress(db):
    corpus = files_service.create_file_corpus(db, user=db.get(User, "admin"), name="Records")
    partition = db.get(RetrievalPartition, corpus.retrieval_partition_id)
    partition.metadata_version = 2
    db.flush()
    with pytest.raises(files_service.FileCorpusConflict, match="metadata does not match"):
        _folder(db, corpus_id=corpus.id)
