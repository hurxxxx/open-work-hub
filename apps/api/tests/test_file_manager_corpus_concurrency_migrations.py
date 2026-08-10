from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from threading import Barrier, Event, local

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_do_api.domains.auth.access import load_user_graph
from ai_do_api.domains.auth.models import (
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.files import service as files_service
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition
from ai_do_api.domains.retrieval.partitioning import ensure_default_partition


pytestmark = pytest.mark.migration

WORKSPACE_A_ID = "corpus-race-workspace-a"
WORKSPACE_B_ID = "corpus-race-workspace-b"
DUAL_ADMIN_ID = "corpus-race-dual-admin"
SOURCE_ADMIN_ID = "corpus-race-source-admin"
PLATFORM_ACTOR_ID = "corpus-race-platform-actor"


@dataclass(frozen=True)
class CorpusRaceContext:
    engine: Engine
    corpus_id: str
    folder_id: str
    second_corpus_id: str
    second_folder_id: str
    legacy_folder_id: str
    first_use_legacy_folder_id: str


@pytest.fixture
def corpus_race_context(application_postgres_dsn: str):
    engine = create_engine(application_postgres_dsn)
    with Session(engine) as db, db.begin():
        db.add_all(
            [
                Workspace(id=WORKSPACE_A_ID, key=WORKSPACE_A_ID, name="Corpus Race A"),
                Workspace(id=WORKSPACE_B_ID, key=WORKSPACE_B_ID, name="Corpus Race B"),
                _user(DUAL_ADMIN_ID),
                _user(SOURCE_ADMIN_ID),
                _user(PLATFORM_ACTOR_ID),
            ]
        )
        db.flush()
        db.add_all(
            [
                _binding("corpus-race-dual-a", DUAL_ADMIN_ID, WORKSPACE_A_ID),
                _binding("corpus-race-dual-b", DUAL_ADMIN_ID, WORKSPACE_B_ID),
                _binding("corpus-race-source-a", SOURCE_ADMIN_ID, WORKSPACE_A_ID),
                UserSystemRole(
                    id="corpus-race-platform-role",
                    user_id=PLATFORM_ACTOR_ID,
                    role="platform_admin",
                ),
            ]
        )
        db.flush()
        workspace = db.get(Workspace, WORKSPACE_A_ID)
        source_admin = db.get(User, SOURCE_ADMIN_ID)
        assert workspace is not None and source_admin is not None
        corpus = files_service.create_file_corpus(
            db,
            workspace=workspace,
            user=source_admin,
            name="Corpus transition race",
        )
        folder = files_service.create_folder(
            db,
            workspace=workspace,
            user=source_admin,
            name="Original child",
            parent_id=None,
            visibility="workspace",
            corpus_id=corpus.id,
        )
        second_corpus = files_service.create_file_corpus(
            db,
            workspace=workspace,
            user=source_admin,
            name="Second corpus transition race",
        )
        second_folder = files_service.create_folder(
            db,
            workspace=workspace,
            user=source_admin,
            name="Second corpus child",
            parent_id=None,
            visibility="workspace",
            corpus_id=second_corpus.id,
        )
        ensure_default_partition(
            db,
            source_namespace="files",
            candidate_scope_kind="workspace",
            workspace_id=workspace.id,
        )
        legacy_folder = FileManagerFolder(
            id="corpus-race-null-root-a",
            workspace_id=workspace.id,
            owner_id=source_admin.id,
            name="Genuine NULL legacy root",
            visibility="workspace",
        )
        first_use_legacy_folder = FileManagerFolder(
            id="corpus-race-first-null-root-b",
            workspace_id=WORKSPACE_B_ID,
            owner_id=DUAL_ADMIN_ID,
            name="First-use NULL legacy root",
            visibility="workspace",
        )
        db.add_all([legacy_folder, first_use_legacy_folder])
        db.flush()
        assert legacy_folder.corpus_id is None
        assert legacy_folder.retrieval_partition_id is None
        assert first_use_legacy_folder.corpus_id is None
        assert first_use_legacy_folder.retrieval_partition_id is None
        context = CorpusRaceContext(
            engine=engine,
            corpus_id=corpus.id,
            folder_id=folder.id,
            second_corpus_id=second_corpus.id,
            second_folder_id=second_folder.id,
            legacy_folder_id=legacy_folder.id,
            first_use_legacy_folder_id=first_use_legacy_folder.id,
        )
    try:
        yield context
    finally:
        engine.dispose()


def test_stale_source_admin_mutation_waits_for_transfer_then_fails_closed(
    corpus_race_context: CorpusRaceContext,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    transition_holds_lock = Event()
    allow_transition_commit = Event()
    mutation_corpus_lock_attempted = Event()
    mutation_finished = Event()
    thread_role = local()

    def observe_corpus_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            getattr(thread_role, "value", None) == "mutation"
            and "file_manager_corpora" in statement
            and "FOR SHARE" in statement.upper()
        ):
            mutation_corpus_lock_attempted.set()

    event.listen(corpus_race_context.engine, "before_cursor_execute", observe_corpus_lock)

    def transfer() -> None:
        with factory.begin() as db:
            actor = db.get(User, DUAL_ADMIN_ID)
            assert actor is not None
            files_service.transition_file_corpus(
                db,
                corpus_id=corpus_race_context.corpus_id,
                actor=actor,
                expected_metadata_version=1,
                access_scope_kind="workspace",
                target_workspace_id=WORKSPACE_B_ID,
                reason="Exercise child mutation serialization",
            )
            transition_holds_lock.set()
            assert allow_transition_commit.wait(timeout=10)

    def stale_update() -> int:
        thread_role.value = "mutation"
        try:
            with factory.begin() as db:
                workspace = db.get(Workspace, WORKSPACE_A_ID)
                actor = db.get(User, SOURCE_ADMIN_ID)
                assert workspace is not None and actor is not None
                files_service.update_folder(
                    db,
                    workspace=workspace,
                    user=actor,
                    folder_id=corpus_race_context.folder_id,
                    name="Unauthorized stale update",
                )
        except HTTPException as error:
            return error.status_code
        finally:
            mutation_finished.set()
        return 200

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            transfer_future = executor.submit(transfer)
            assert transition_holds_lock.wait(timeout=10)
            mutation_future = executor.submit(stale_update)
            assert mutation_corpus_lock_attempted.wait(timeout=10)
            assert not mutation_finished.wait(timeout=0.25)
            allow_transition_commit.set()
            transfer_future.result(timeout=10)
            assert mutation_future.result(timeout=10) == 404
    finally:
        allow_transition_commit.set()
        event.remove(
            corpus_race_context.engine,
            "before_cursor_execute",
            observe_corpus_lock,
        )

    with factory() as db:
        corpus = db.get(FileManagerCorpus, corpus_race_context.corpus_id)
        folder = db.get(FileManagerFolder, corpus_race_context.folder_id)
        assert corpus is not None and folder is not None
        assert corpus.managed_workspace_id == WORKSPACE_B_ID
        assert folder.workspace_id == WORKSPACE_B_ID
        assert folder.name == "Original child"


def test_same_corpus_upload_and_folder_ingress_overlap_while_transfer_waits(
    corpus_race_context: CorpusRaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    folder_ingress_returned = Event()
    upload_ingress_returned = Event()
    allow_ingress_commits = Event()
    transition_lock_attempted = Event()
    transition_finished = Event()
    thread_role = local()
    monkeypatch.setattr(
        files_service.file_storage,
        "put_file_object",
        lambda **_kwargs: None,
    )

    def observe_corpus_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            getattr(thread_role, "value", None) == "transition"
            and "file_manager_corpora" in statement
            and "FOR UPDATE" in statement.upper()
        ):
            transition_lock_attempted.set()

    event.listen(corpus_race_context.engine, "before_cursor_execute", observe_corpus_lock)

    def create_child_folder() -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            child = files_service.create_folder(
                db,
                workspace=workspace,
                user=actor,
                name="Concurrent ingress child folder",
                parent_id=corpus_race_context.folder_id,
                visibility="workspace",
            )
            folder_ingress_returned.set()
            assert allow_ingress_commits.wait(timeout=10)
            return child.id

    def upload_child_file() -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            child = files_service.upload_file(
                db,
                workspace=workspace,
                user=actor,
                filename="concurrent-ingress.txt",
                content_type="text/plain",
                content=BytesIO(b"concurrent ingress"),
                size_bytes=18,
                folder_id=corpus_race_context.folder_id,
                visibility="workspace",
            )
            upload_ingress_returned.set()
            assert allow_ingress_commits.wait(timeout=10)
            return child.id

    def transfer() -> None:
        thread_role.value = "transition"
        try:
            with factory.begin() as db:
                actor = db.get(User, DUAL_ADMIN_ID)
                assert actor is not None
                files_service.transition_file_corpus(
                    db,
                    corpus_id=corpus_race_context.corpus_id,
                    actor=actor,
                    expected_metadata_version=1,
                    access_scope_kind="workspace",
                    target_workspace_id=WORKSPACE_B_ID,
                    reason="Exercise child ingress serialization",
                )
        finally:
            transition_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            folder_ingress_future = executor.submit(create_child_folder)
            assert folder_ingress_returned.wait(timeout=10)
            upload_ingress_future = executor.submit(upload_child_file)
            # Both service calls return before either transaction commits. This proves
            # same-corpus upload/folder and parent locks are compatible shared locks.
            assert upload_ingress_returned.wait(timeout=10)
            transfer_future = executor.submit(transfer)
            assert transition_lock_attempted.wait(timeout=10)
            assert not transition_finished.wait(timeout=0.25)
            allow_ingress_commits.set()
            child_folder_id = folder_ingress_future.result(timeout=10)
            child_file_id = upload_ingress_future.result(timeout=10)
            transfer_future.result(timeout=10)
    finally:
        allow_ingress_commits.set()
        event.remove(
            corpus_race_context.engine,
            "before_cursor_execute",
            observe_corpus_lock,
        )

    with factory() as db:
        corpus = db.get(FileManagerCorpus, corpus_race_context.corpus_id)
        child_folder = db.get(FileManagerFolder, child_folder_id)
        child_file = db.get(FileManagerFile, child_file_id)
        assert corpus is not None and child_folder is not None and child_file is not None
        assert corpus.managed_workspace_id == WORKSPACE_B_ID
        for child in (child_folder, child_file):
            assert child.workspace_id == WORKSPACE_B_ID
            assert child.corpus_id == corpus.id
            assert child.retrieval_partition_id == corpus.retrieval_partition_id


def test_same_null_legacy_parent_upload_and_folder_ingress_overlap(
    corpus_race_context: CorpusRaceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    folder_ingress_returned = Event()
    upload_ingress_returned = Event()
    allow_commits = Event()
    monkeypatch.setattr(
        files_service.file_storage,
        "put_file_object",
        lambda **_kwargs: None,
    )

    def create_child_folder() -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            child = files_service.create_folder(
                db,
                workspace=workspace,
                user=actor,
                name="Concurrent NULL-parent child",
                parent_id=corpus_race_context.legacy_folder_id,
                visibility="workspace",
            )
            folder_ingress_returned.set()
            assert allow_commits.wait(timeout=10)
            return child.id

    def upload_child_file() -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            child = files_service.upload_file(
                db,
                workspace=workspace,
                user=actor,
                filename="null-parent-concurrent.txt",
                content_type="text/plain",
                content=BytesIO(b"null parent"),
                size_bytes=11,
                folder_id=corpus_race_context.legacy_folder_id,
                visibility="workspace",
            )
            upload_ingress_returned.set()
            assert allow_commits.wait(timeout=10)
            return child.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        folder_future = executor.submit(create_child_folder)
        assert folder_ingress_returned.wait(timeout=10)
        upload_future = executor.submit(upload_child_file)
        try:
            # Both calls finish before either transaction commits. The logical
            # default-partition gate and NULL parent row are both shared locks.
            assert upload_ingress_returned.wait(timeout=10)
        finally:
            allow_commits.set()
        folder_id = folder_future.result(timeout=10)
        file_id = upload_future.result(timeout=10)

    with factory() as db:
        parent = db.get(FileManagerFolder, corpus_race_context.legacy_folder_id)
        folder = db.get(FileManagerFolder, folder_id)
        file = db.get(FileManagerFile, file_id)
        assert parent is not None and folder is not None and file is not None
        assert parent.corpus_id is parent.retrieval_partition_id is None
        assert folder.corpus_id is file.corpus_id is None
        assert folder.retrieval_partition_id == file.retrieval_partition_id
        assert folder.retrieval_partition_id is not None


def test_concurrent_first_use_of_null_parent_creates_one_default_gate_without_deadlock(
    corpus_race_context: CorpusRaceContext,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    start_together = Barrier(2)

    with factory() as db:
        assert (
            db.scalar(
                select(RetrievalPartition.id).where(
                    RetrievalPartition.source_namespace == "files",
                    RetrievalPartition.managed_workspace_id == WORKSPACE_B_ID,
                    RetrievalPartition.is_default_ingest.is_(True),
                )
            )
            is None
        )

    def create_child(name: str) -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_B_ID)
            actor = db.get(User, DUAL_ADMIN_ID)
            assert workspace is not None and actor is not None
            start_together.wait(timeout=10)
            child = files_service.create_folder(
                db,
                workspace=workspace,
                user=actor,
                name=name,
                parent_id=corpus_race_context.first_use_legacy_folder_id,
                visibility="workspace",
            )
            return child.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(create_child, "First concurrent first-use child")
        second_future = executor.submit(create_child, "Second concurrent first-use child")
        child_ids = [
            first_future.result(timeout=15),
            second_future.result(timeout=15),
        ]

    with factory() as db:
        parent = db.get(
            FileManagerFolder,
            corpus_race_context.first_use_legacy_folder_id,
        )
        children = [db.get(FileManagerFolder, child_id) for child_id in child_ids]
        assert parent is not None
        assert parent.corpus_id is parent.retrieval_partition_id is None
        assert all(child is not None for child in children)
        partition_ids = {child.retrieval_partition_id for child in children if child is not None}
        assert len(partition_ids) == 1
        partition_id = partition_ids.pop()
        assert partition_id is not None
        partition = db.get(RetrievalPartition, partition_id)
        assert partition is not None
        assert partition.source_namespace == "files"
        assert partition.is_default_ingest is True
        assert partition.managed_workspace_id == WORKSPACE_B_ID
        assert partition.candidate_workspace_id == WORKSPACE_B_ID


def test_cross_corpus_tree_deletes_lock_only_their_trees_and_do_not_deadlock(
    corpus_race_context: CorpusRaceContext,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    start_together = Barrier(2)
    first_delete_returned = Event()
    second_delete_returned = Event()
    allow_commits = Event()

    def delete_tree(folder_id: str, returned: Event) -> None:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            start_together.wait(timeout=10)
            assert (
                files_service.delete_folder(
                    db,
                    workspace=workspace,
                    user=actor,
                    folder_id=folder_id,
                )
                == []
            )
            returned.set()
            assert allow_commits.wait(timeout=10)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            delete_tree,
            corpus_race_context.folder_id,
            first_delete_returned,
        )
        second_future = executor.submit(
            delete_tree,
            corpus_race_context.second_folder_id,
            second_delete_returned,
        )
        try:
            # Both disjoint tree deletes must finish their service work while the
            # other transaction is still open; a workspace-wide row lock cannot.
            assert first_delete_returned.wait(timeout=10)
            assert second_delete_returned.wait(timeout=10)
        finally:
            allow_commits.set()
        first_future.result(timeout=10)
        second_future.result(timeout=10)

    with factory() as db:
        first_folder = db.get(FileManagerFolder, corpus_race_context.folder_id)
        second_folder = db.get(FileManagerFolder, corpus_race_context.second_folder_id)
        assert first_folder is not None and first_folder.deleted_at is not None
        assert second_folder is not None and second_folder.deleted_at is not None


def test_legacy_tree_delete_waits_on_partition_gate_and_includes_new_child(
    corpus_race_context: CorpusRaceContext,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    ingress_returned = Event()
    allow_ingress_commit = Event()
    delete_partition_lock_attempted = Event()
    delete_finished = Event()
    thread_role = local()

    def observe_partition_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            getattr(thread_role, "value", None) == "delete"
            and "retrieval_partitions" in statement
            and "FOR UPDATE" in statement.upper()
        ):
            delete_partition_lock_attempted.set()

    event.listen(corpus_race_context.engine, "before_cursor_execute", observe_partition_lock)

    def create_legacy_child() -> str:
        with factory.begin() as db:
            workspace = db.get(Workspace, WORKSPACE_A_ID)
            actor = db.get(User, SOURCE_ADMIN_ID)
            assert workspace is not None and actor is not None
            child = files_service.create_folder(
                db,
                workspace=workspace,
                user=actor,
                name="Legacy child committed before delete",
                parent_id=corpus_race_context.legacy_folder_id,
                visibility="workspace",
            )
            ingress_returned.set()
            assert allow_ingress_commit.wait(timeout=10)
            return child.id

    def delete_legacy_tree() -> None:
        thread_role.value = "delete"
        try:
            with factory.begin() as db:
                workspace = db.get(Workspace, WORKSPACE_A_ID)
                actor = db.get(User, SOURCE_ADMIN_ID)
                assert workspace is not None and actor is not None
                assert (
                    files_service.delete_folder(
                        db,
                        workspace=workspace,
                        user=actor,
                        folder_id=corpus_race_context.legacy_folder_id,
                    )
                    == []
                )
        finally:
            delete_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            ingress_future = executor.submit(create_legacy_child)
            assert ingress_returned.wait(timeout=10)
            delete_future = executor.submit(delete_legacy_tree)
            assert delete_partition_lock_attempted.wait(timeout=10)
            assert not delete_finished.wait(timeout=0.25)
            allow_ingress_commit.set()
            child_id = ingress_future.result(timeout=10)
            delete_future.result(timeout=10)
    finally:
        allow_ingress_commit.set()
        event.remove(
            corpus_race_context.engine,
            "before_cursor_execute",
            observe_partition_lock,
        )

    with factory() as db:
        root = db.get(FileManagerFolder, corpus_race_context.legacy_folder_id)
        child = db.get(FileManagerFolder, child_id)
        assert root is not None and root.deleted_at is not None
        assert child is not None and child.deleted_at is not None
        assert root.corpus_id is root.retrieval_partition_id is None
        assert child.corpus_id is None
        assert child.retrieval_partition_id is not None


@pytest.mark.parametrize(
    "revocation",
    ("workspace_binding", "user_blocked", "user_inactive", "workspace_inactive"),
)
def test_waiting_mutation_reauthorizes_eager_loaded_actor_from_current_db_state(
    corpus_race_context: CorpusRaceContext,
    revocation: str,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    corpus_lock_held = Event()
    allow_lock_release = Event()
    actor_preloaded = Event()
    mutation_lock_attempted = Event()
    thread_role = local()

    def observe_corpus_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            getattr(thread_role, "value", None) == "mutation"
            and "file_manager_corpora" in statement
            and "FOR SHARE" in statement.upper()
        ):
            mutation_lock_attempted.set()

    event.listen(corpus_race_context.engine, "before_cursor_execute", observe_corpus_lock)

    def hold_exclusive_corpus_lock() -> None:
        with factory.begin() as db:
            corpus = db.scalar(
                select(FileManagerCorpus)
                .where(FileManagerCorpus.id == corpus_race_context.corpus_id)
                .with_for_update()
            )
            assert corpus is not None
            corpus_lock_held.set()
            assert allow_lock_release.wait(timeout=10)

    def mutate_with_preloaded_actor() -> str:
        thread_role.value = "mutation"
        try:
            with factory.begin() as db:
                workspace = db.get(Workspace, WORKSPACE_A_ID)
                actor = load_user_graph(db, DUAL_ADMIN_ID)
                assert workspace is not None and actor is not None
                assert actor.status == "active"
                assert actor.login_blocked is False
                assert any(
                    binding.workspace_id == WORKSPACE_A_ID and binding.role == "admin"
                    for binding in actor.workspace_bindings
                )
                actor_preloaded.set()
                files_service.update_folder(
                    db,
                    workspace=workspace,
                    user=actor,
                    folder_id=corpus_race_context.folder_id,
                    name="Must not apply after authorization revocation",
                )
        except files_service.FileCorpusAccessDenied:
            return "denied"
        return "updated"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            holder_future = executor.submit(hold_exclusive_corpus_lock)
            assert corpus_lock_held.wait(timeout=10)
            mutation_future = executor.submit(mutate_with_preloaded_actor)
            assert actor_preloaded.wait(timeout=10)
            assert mutation_lock_attempted.wait(timeout=10)

            with factory.begin() as db:
                if revocation == "workspace_binding":
                    binding = db.scalar(
                        select(WorkspaceUserBinding).where(
                            WorkspaceUserBinding.user_id == DUAL_ADMIN_ID,
                            WorkspaceUserBinding.workspace_id == WORKSPACE_A_ID,
                        )
                    )
                    assert binding is not None
                    db.delete(binding)
                elif revocation == "user_blocked":
                    actor = db.get(User, DUAL_ADMIN_ID)
                    assert actor is not None
                    actor.login_blocked = True
                elif revocation == "user_inactive":
                    actor = db.get(User, DUAL_ADMIN_ID)
                    assert actor is not None
                    actor.status = "inactive"
                else:
                    workspace = db.get(Workspace, WORKSPACE_A_ID)
                    assert workspace is not None
                    workspace.active = False

            allow_lock_release.set()
            holder_future.result(timeout=10)
            assert mutation_future.result(timeout=10) == "denied"
    finally:
        allow_lock_release.set()
        event.remove(
            corpus_race_context.engine,
            "before_cursor_execute",
            observe_corpus_lock,
        )

    with factory() as db:
        folder = db.get(FileManagerFolder, corpus_race_context.folder_id)
        assert folder is not None
        assert folder.name == "Original child"


def test_waiting_company_transition_reauthorizes_eager_loaded_platform_role(
    corpus_race_context: CorpusRaceContext,
) -> None:
    factory = _session_factory(corpus_race_context.engine)
    corpus_lock_held = Event()
    allow_lock_release = Event()
    actor_preloaded = Event()
    transition_lock_attempted = Event()
    thread_role = local()

    def observe_corpus_lock(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if (
            getattr(thread_role, "value", None) == "transition"
            and "file_manager_corpora" in statement
            and "FOR UPDATE" in statement.upper()
        ):
            transition_lock_attempted.set()

    event.listen(corpus_race_context.engine, "before_cursor_execute", observe_corpus_lock)

    def hold_exclusive_corpus_lock() -> None:
        with factory.begin() as db:
            corpus = db.scalar(
                select(FileManagerCorpus)
                .where(FileManagerCorpus.id == corpus_race_context.corpus_id)
                .with_for_update()
            )
            assert corpus is not None
            corpus_lock_held.set()
            assert allow_lock_release.wait(timeout=10)

    def transition_with_preloaded_actor() -> str:
        thread_role.value = "transition"
        try:
            with factory.begin() as db:
                actor = load_user_graph(db, PLATFORM_ACTOR_ID)
                assert actor is not None
                assert any(role.role == "platform_admin" for role in actor.system_role_links)
                actor_preloaded.set()
                files_service.transition_file_corpus(
                    db,
                    corpus_id=corpus_race_context.corpus_id,
                    actor=actor,
                    expected_metadata_version=1,
                    access_scope_kind="company",
                    reason="Must not apply after platform role revocation",
                )
        except files_service.FileCorpusAccessDenied:
            return "denied"
        return "transitioned"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            holder_future = executor.submit(hold_exclusive_corpus_lock)
            assert corpus_lock_held.wait(timeout=10)
            transition_future = executor.submit(transition_with_preloaded_actor)
            assert actor_preloaded.wait(timeout=10)
            assert transition_lock_attempted.wait(timeout=10)

            with factory.begin() as db:
                role = db.scalar(
                    select(UserSystemRole).where(
                        UserSystemRole.user_id == PLATFORM_ACTOR_ID,
                        UserSystemRole.role == "platform_admin",
                    )
                )
                assert role is not None
                db.delete(role)

            allow_lock_release.set()
            holder_future.result(timeout=10)
            assert transition_future.result(timeout=10) == "denied"
    finally:
        allow_lock_release.set()
        event.remove(
            corpus_race_context.engine,
            "before_cursor_execute",
            observe_corpus_lock,
        )

    with factory() as db:
        corpus = db.get(FileManagerCorpus, corpus_race_context.corpus_id)
        assert corpus is not None
        assert corpus.access_scope_kind == "workspace"
        assert corpus.managed_workspace_id == WORKSPACE_A_ID
        assert corpus.metadata_version == 1


def _session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.com",
        full_name=user_id.replace("-", " ").title(),
        password_hash="hash",
    )


def _binding(binding_id: str, user_id: str, workspace_id: str) -> WorkspaceUserBinding:
    return WorkspaceUserBinding(
        id=binding_id,
        user_id=user_id,
        workspace_id=workspace_id,
        role="admin",
    )
