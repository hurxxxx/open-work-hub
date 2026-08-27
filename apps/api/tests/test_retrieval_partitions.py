from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.organization.models import OrganizationUnit
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalPartitionCandidateScope,
)
from open_work_hub_api.domains.retrieval.partition_adapter_registry import (
    RetrievalProjectionBinding,
    register_retrieval_partition_adapter,
    reset_retrieval_partition_adapters,
)
from open_work_hub_api.domains.retrieval.partitioning import (
    RetrievalPartitionConflict,
    RetrievalPartitionInvalidTarget,
    RetrievalPartitionUnbound,
    assign_default_partition,
    bind_projection,
    create_managed_partition,
    ensure_default_partition,
    flatten_read_scope,
    resolve_read_scope,
    resolve_resource_read_scope,
    transition_partition_candidate_scope,
)


@dataclass(frozen=True)
class _FakePartitionAdapter:
    adapter_id: str
    source_namespace: str
    resource_types: tuple[str, ...]
    allowed_candidate_scopes: tuple[str, ...] = ("workspace",)
    allowed_transitions: tuple[str, ...] = ()
    transition_mode: str = "generic"
    partition_id: str = "partition-a"

    def bind_resource_partition(
        self,
        db: Session,
        *,
        resource_type: str,
        resource_id: str,
    ) -> RetrievalProjectionBinding:
        del db
        return RetrievalProjectionBinding(
            resource_type=resource_type,
            resource_id=resource_id,
            partition_id=self.partition_id,
        )


@pytest.fixture
def db() -> Session:
    reset_retrieval_partition_adapters()
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
            OrganizationUnit.__table__,
            User.__table__,
            RetrievalPartition.__table__,
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                Workspace(id="workspace-a", key="workspace-a", name="Workspace A"),
                Workspace(id="workspace-b", key="workspace-b", name="Workspace B"),
                User(
                    id="user-a",
                    login_id="user-a",
                    email="user-a@example.com",
                    full_name="User A",
                    password_hash="hash",
                ),
                User(
                    id="user-b",
                    login_id="user-b",
                    email="user-b@example.com",
                    full_name="User B",
                    password_hash="hash",
                ),
            ]
        )
        session.commit()
        yield session
    reset_retrieval_partition_adapters()


def test_default_partition_is_stable_per_namespace_and_owner(db: Session) -> None:
    first = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind=RetrievalPartitionCandidateScope.WORKSPACE,
        workspace_id="workspace-a",
    )
    second = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )

    assert first.id == second.id
    assert first.source_namespace == "files"
    assert first.managed_workspace_id == "workspace-a"
    assert first.candidate_workspace_id == "workspace-a"
    assert first.metadata_version == 1


def test_assign_default_partition_dual_writes_source_row_once(db: Session) -> None:
    @dataclass
    class _SourceRow:
        retrieval_partition_id: str | None = None

    row = _SourceRow()
    first = assign_default_partition(
        db,
        target=row,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    second = assign_default_partition(
        db,
        target=row,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-b",
    )

    assert row.retrieval_partition_id == first
    assert second == first


def test_read_scope_unions_company_workspace_and_personal_partitions(db: Session) -> None:
    company = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="company",
    )
    workspace_a = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    workspace_b = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-b",
    )
    personal_a = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="personal",
        user_id="user-a",
    )
    personal_b = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="personal",
        user_id="user-b",
    )

    scope = resolve_read_scope(
        db,
        source_namespaces=["files", "docs"],
        workspace_id="workspace-a",
        user_id="user-a",
    )

    assert set(scope.for_source("files")) == {
        company.id,
        workspace_a.id,
        personal_a.id,
    }
    assert workspace_b.id not in scope.for_source("files")
    assert personal_b.id not in scope.for_source("files")
    assert scope.for_source("docs") == ()
    assert not scope.is_empty


def test_resource_read_scope_is_server_resolved_from_registered_adapter(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="company",
    )
    workspace = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    register_retrieval_partition_adapter(
        _FakePartitionAdapter(
            adapter_id="files",
            source_namespace="files",
            resource_types=("file_manager_file",),
            allowed_candidate_scopes=("workspace", "company"),
            partition_id=workspace.id,
        )
    )
    monkeypatch.setattr(
        "open_work_hub_api.domains.retrieval.default_partition_adapters."
        "ensure_retrieval_partition_adapters_registered",
        lambda: None,
    )

    scope = resolve_resource_read_scope(
        db,
        resource_types=["file_manager_file"],
        workspace_id="workspace-a",
        user_id="user-a",
    )

    assert set(flatten_read_scope(scope)) == {company.id, workspace.id}


def test_candidate_scope_transition_preserves_partition_identity(db: Session) -> None:
    partition = create_managed_partition(
        db,
        source_namespace="files",
        managed_workspace_id="workspace-a",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    register_retrieval_partition_adapter(
        _FakePartitionAdapter(
            adapter_id="files",
            source_namespace="files",
            resource_types=("file_manager_file",),
            allowed_candidate_scopes=("workspace", "company"),
            allowed_transitions=("corpus_scope_change",),
            partition_id=partition.id,
        )
    )
    original_id = partition.id

    transitioned = transition_partition_candidate_scope(
        db,
        partition_id=partition.id,
        adapter_id="files",
        transition_operation="corpus_scope_change",
        expected_metadata_version=1,
        candidate_scope_kind="company",
    )

    assert transitioned.id == original_id
    assert transitioned.managed_workspace_id == "workspace-a"
    assert transitioned.candidate_scope_kind == "company"
    assert transitioned.candidate_workspace_id is None
    assert transitioned.metadata_version == 2

    company_scope = resolve_read_scope(
        db,
        source_namespaces=["files"],
        workspace_id="workspace-b",
        user_id="user-b",
    )
    assert company_scope.for_source("files") == (original_id,)

    with pytest.raises(RetrievalPartitionConflict):
        transition_partition_candidate_scope(
            db,
            partition_id=partition.id,
            adapter_id="files",
            transition_operation="corpus_scope_change",
            expected_metadata_version=1,
            candidate_scope_kind="workspace",
            workspace_id="workspace-b",
        )


def test_files_source_owned_adapter_rejects_generic_candidate_scope_transition(
    db: Session,
) -> None:
    from open_work_hub_api.domains.files.source_access import FileManagerSourceAccessAdapter

    adapter = FileManagerSourceAccessAdapter()
    partition = create_managed_partition(
        db,
        source_namespace="files",
        managed_workspace_id="workspace-a",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    register_retrieval_partition_adapter(adapter)

    with pytest.raises(RetrievalPartitionConflict, match="owned by its source service"):
        transition_partition_candidate_scope(
            db,
            partition_id=partition.id,
            adapter_id=adapter.adapter_id,
            transition_operation="corpus_scope_change",
            expected_metadata_version=1,
            candidate_scope_kind="company",
        )

    assert partition.candidate_scope_kind == "workspace"
    assert partition.candidate_workspace_id == "workspace-a"
    assert partition.metadata_version == 1


def test_multiple_managed_company_partitions_coexist_with_company_default(
    db: Session,
) -> None:
    unmanaged_company = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="company",
    )
    workspace_a = create_managed_partition(
        db,
        source_namespace="files",
        managed_workspace_id="workspace-a",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    workspace_b = create_managed_partition(
        db,
        source_namespace="files",
        managed_workspace_id="workspace-b",
        candidate_scope_kind="workspace",
        workspace_id="workspace-b",
    )
    register_retrieval_partition_adapter(
        _FakePartitionAdapter(
            adapter_id="files",
            source_namespace="files",
            resource_types=("file_manager_file",),
            allowed_candidate_scopes=("workspace", "company"),
            allowed_transitions=("corpus_scope_change",),
            partition_id=workspace_a.id,
        )
    )

    for partition in (workspace_a, workspace_b):
        transition_partition_candidate_scope(
            db,
            partition_id=partition.id,
            adapter_id="files",
            transition_operation="corpus_scope_change",
            expected_metadata_version=1,
            candidate_scope_kind="company",
        )

    scope = resolve_read_scope(
        db,
        source_namespaces=["files"],
        workspace_id=None,
        user_id=None,
    )

    assert set(scope.for_source("files")) == {
        unmanaged_company.id,
        workspace_a.id,
        workspace_b.id,
    }


@pytest.mark.parametrize(
    ("scope_kind", "workspace_id", "user_id"),
    [
        ("company", "workspace-a", None),
        ("company", None, "user-a"),
        ("workspace", None, None),
        ("workspace", "workspace-a", "user-a"),
        ("personal", None, None),
        ("personal", "workspace-a", "user-a"),
        ("unknown", None, None),
    ],
)
def test_invalid_candidate_target_fails_before_writing(
    db: Session,
    scope_kind: str,
    workspace_id: str | None,
    user_id: str | None,
) -> None:
    with pytest.raises(RetrievalPartitionInvalidTarget):
        ensure_default_partition(
            db,
            source_namespace="files",
            candidate_scope_kind=scope_kind,
            workspace_id=workspace_id,
            user_id=user_id,
        )


def test_database_rejects_invalid_candidate_target(db: Session) -> None:
    db.add(
        RetrievalPartition(
            id="00000000-0000-0000-0000-000000000099",
            source_namespace="files",
            candidate_scope_kind="workspace",
            candidate_workspace_id=None,
            candidate_user_id=None,
        )
    )

    with pytest.raises(IntegrityError):
        db.flush()


def test_partition_id_cannot_be_changed(db: Session) -> None:
    partition = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )

    with pytest.raises(ValueError, match="immutable"):
        partition.id = "00000000-0000-0000-0000-000000000098"


def test_partition_adapter_binds_projection(db: Session) -> None:
    partition = ensure_default_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="workspace",
        workspace_id="workspace-a",
    )
    register_retrieval_partition_adapter(
        _FakePartitionAdapter(
            adapter_id="files",
            source_namespace="files",
            resource_types=("file_manager_file",),
            partition_id=partition.id,
        )
    )

    binding = bind_projection(
        db,
        resource_type="file_manager_file",
        resource_id="file-a",
    )

    assert binding == RetrievalProjectionBinding(
        resource_type="file_manager_file",
        resource_id="file-a",
        partition_id=partition.id,
    )


def test_partition_adapter_rejects_duplicate_resource_owner() -> None:
    register_retrieval_partition_adapter(
        _FakePartitionAdapter(
            adapter_id="files",
            source_namespace="files",
            resource_types=("file_manager_file",),
        )
    )

    with pytest.raises(ValueError, match="already have adapters"):
        register_retrieval_partition_adapter(
            _FakePartitionAdapter(
                adapter_id="other",
                source_namespace="other",
                resource_types=("file_manager_file",),
            )
        )


def test_bind_projection_fails_when_resource_has_no_partition_adapter(
    db: Session,
) -> None:
    with pytest.raises(RetrievalPartitionUnbound, match="not registered"):
        bind_projection(
            db,
            resource_type="file_manager_file",
            resource_id="file-a",
        )
