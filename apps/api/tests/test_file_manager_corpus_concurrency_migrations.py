from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from threading import Barrier, Event, local

import pytest
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import sessionmaker

from company_admission_fixture import seed_company_app_access
from open_work_hub_api.domains.auth.access import load_user_graph
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
from open_work_hub_api.domains.auth.models import CompanyAppControl, User, UserSystemRole
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
)
from open_work_hub_api.domains.retrieval.models import RetrievalPartition

pytestmark = pytest.mark.migration
_ACTOR_ID = "corpus-race-owner"


@dataclass(frozen=True)
class CorpusRaceContext:
    factory: sessionmaker
    first_corpus_id: str
    first_folder_id: str
    second_corpus_id: str
    second_folder_id: str


@pytest.fixture
def corpus_race_context(application_postgres_dsn, monkeypatch):
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(files_service.file_storage, "put_file_object", lambda **kwargs: None)
    monkeypatch.setattr(files_service, "enqueue_file_retrieval_sync", lambda *args, **kwargs: None)
    with factory.begin() as db:
        seed_company_app_access(db, ("files",))
        actor = User(
            id=_ACTOR_ID,
            login_id=_ACTOR_ID,
            email="race-owner@example.test",
            full_name="Race owner",
            password_hash="unused",
        )
        db.add(actor)
        db.flush()
        db.add(
            UserSystemRole(id="corpus-race-platform-role", user_id=actor.id, role="platform_admin")
        )
        db.flush()
        corpus_ids = []
        folder_ids = []
        for name in ("First", "Second"):
            corpus = files_service.create_file_corpus(db, user=actor, name=name)
            folder = files_service.create_folder(
                db,
                user=actor,
                name=f"{name} root",
                parent_id=None,
                visibility="company",
                company_admin_read_acknowledged=True,
                corpus_id=corpus.id,
            )
            corpus_ids.append(corpus.id)
            folder_ids.append(folder.id)
        context = CorpusRaceContext(
            factory, *[value for pair in zip(corpus_ids, folder_ids) for value in pair]
        )
    try:
        yield context
    finally:
        engine.dispose()


def _create_child(db, *, parent_id, name="Child"):
    return files_service.create_folder(
        db,
        user=db.get(User, _ACTOR_ID),
        name=name,
        parent_id=parent_id,
        visibility="company",
        company_admin_read_acknowledged=True,
    )


def test_same_corpus_shared_ingress_overlaps_and_tree_delete_waits_for_both_children(
    corpus_race_context,
):
    context = corpus_race_context
    folder_ready, file_ready, release, delete_attempted = Event(), Event(), Event(), Event()
    role = local()
    engine = context.factory.kw["bind"]

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        if (
            getattr(role, "name", None) == "delete"
            and "file_manager_corpora" in statement
            and "FOR UPDATE" in statement.upper()
        ):
            delete_attempted.set()

    event.listen(engine, "before_cursor_execute", observe)

    def folder_ingress():
        with context.factory.begin() as db:
            row = _create_child(db, parent_id=context.first_folder_id)
            folder_ready.set()
            assert release.wait(10)
            return row.id

    def file_ingress():
        with context.factory.begin() as db:
            row = files_service.upload_file(
                db,
                user=db.get(User, _ACTOR_ID),
                filename="race.txt",
                content_type="text/plain",
                content=BytesIO(b"race"),
                size_bytes=4,
                folder_id=context.first_folder_id,
                visibility="company",
                company_admin_read_acknowledged=True,
            )
            file_ready.set()
            assert release.wait(10)
            return row.id

    def delete_tree():
        role.name = "delete"
        with context.factory.begin() as db:
            return files_service.delete_folder(
                db, user=db.get(User, _ACTOR_ID), folder_id=context.first_folder_id
            )

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            first = executor.submit(folder_ingress)
            assert folder_ready.wait(10)
            second = executor.submit(file_ingress)
            assert file_ready.wait(10)
            deletion = executor.submit(delete_tree)
            assert delete_attempted.wait(10)
            assert not deletion.done()
            release.set()
            folder_id, file_id = first.result(10), second.result(10)
            keys = deletion.result(10)
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", observe)
    with context.factory() as db:
        assert db.get(FileManagerFolder, folder_id).deleted_at is not None
        file = db.get(FileManagerFile, file_id)
        assert file.deleted_at is not None and file.storage_key in keys
        assert db.get(FileManagerFolder, context.second_folder_id).deleted_at is None


def test_independent_corpus_tree_deletes_do_not_deadlock(corpus_race_context):
    context = corpus_race_context
    barrier = Barrier(2)

    def remove(folder_id):
        with context.factory.begin() as db:
            actor = db.get(User, _ACTOR_ID)
            barrier.wait(10)
            files_service.delete_folder(db, user=actor, folder_id=folder_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(remove, folder_id)
            for folder_id in (context.first_folder_id, context.second_folder_id)
        ]
        for future in futures:
            future.result(10)
    with context.factory() as db:
        assert all(
            db.get(FileManagerFolder, folder_id).deleted_at is not None
            for folder_id in (context.first_folder_id, context.second_folder_id)
        )


def test_concurrent_first_standalone_ingress_binds_one_company_candidate_partition(
    corpus_race_context,
):
    context = corpus_race_context
    barrier = Barrier(2)

    def create(name):
        with context.factory.begin() as db:
            actor = db.get(User, _ACTOR_ID)
            barrier.wait(10)
            row = files_service.create_folder(
                db, user=actor, name=name, parent_id=None, visibility="private"
            )
            return row.retrieval_partition_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create, name) for name in ("Private A", "Private B")]
        partitions = [future.result(10) for future in futures]
    assert partitions[0] == partitions[1]
    with context.factory() as db:
        assert (
            db.scalar(
                select(func.count(RetrievalPartition.id)).where(
                    RetrievalPartition.source_namespace == "files",
                    RetrievalPartition.is_default_ingest.is_(True),
                )
            )
            == 1
        )


@pytest.mark.parametrize("revocation", ["app_grant", "blocked", "inactive", "master"])
def test_waiting_owner_mutation_rechecks_live_authority_after_aggregate_lock(
    corpus_race_context, revocation
):
    context = corpus_race_context
    with context.factory.begin() as db:
        # A former administrator retains explicit ownership, but still needs live app admission.
        db.execute(delete(UserSystemRole).where(UserSystemRole.user_id == _ACTOR_ID))
        db.get(AppAccessPolicy, "files").audience = "selected"
        db.add(AppUserGrant(app_id="files", user_id=_ACTOR_ID))
    lock_held, release, actor_loaded, mutation_attempted = Event(), Event(), Event(), Event()
    role = local()
    engine = context.factory.kw["bind"]

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        if (
            getattr(role, "name", None) == "mutation"
            and "file_manager_corpora" in statement
            and "FOR SHARE" in statement.upper()
        ):
            mutation_attempted.set()

    event.listen(engine, "before_cursor_execute", observe)

    def holder():
        with context.factory.begin() as db:
            assert db.scalar(
                select(FileManagerCorpus)
                .where(FileManagerCorpus.id == context.first_corpus_id)
                .with_for_update()
            )
            lock_held.set()
            assert release.wait(10)

    def mutate():
        role.name = "mutation"
        with context.factory.begin() as db:
            actor = load_user_graph(db, _ACTOR_ID)
            assert actor.status == "active" and not actor.login_blocked
            actor_loaded.set()
            with pytest.raises(files_service.FileCorpusAccessDenied):
                files_service.update_folder(
                    db, user=actor, folder_id=context.first_folder_id, name="Denied mutation"
                )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            locked = executor.submit(holder)
            assert lock_held.wait(10)
            changed = executor.submit(mutate)
            assert actor_loaded.wait(10) and mutation_attempted.wait(10)
            with context.factory.begin() as db:
                if revocation == "app_grant":
                    db.execute(delete(AppUserGrant).where(AppUserGrant.user_id == _ACTOR_ID))
                elif revocation == "master":
                    db.get(CompanyAppControl, "files").enabled = False
                else:
                    actor = db.get(User, _ACTOR_ID)
                    if revocation == "blocked":
                        actor.login_blocked = True
                    else:
                        actor.status = "inactive"
            release.set()
            locked.result(10)
            changed.result(10)
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", observe)
    with context.factory() as db:
        assert db.get(FileManagerFolder, context.first_folder_id).name == "First root"
