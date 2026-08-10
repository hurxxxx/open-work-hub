from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import (
    OrgUnit,
    User,
    Workspace,
    WorkspaceUserBinding,
)
from ai_do_api.domains.legacy_issues import ai_search
from ai_do_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    _WeightedToken,
    _exact_candidates,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    DATASET_DEFINITIONS,
    copy_dataset_revision_records,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueAttachment,
    LegacyIssueAttachmentIndexJob,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.partitioning import (
    LegacyIssuePartitionMismatch,
    ensure_attachment_job_partition,
    ensure_attachment_partition,
    ensure_chunk_partition,
    ensure_record_partition,
    ensure_revision_partition,
)
from ai_do_api.domains.legacy_issues.source_access import (
    LegacyIssueRecordSourceAccessAdapter,
)
from ai_do_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
)
from ai_do_api.domains.rag.source_adapter_registry import (
    get_rag_resource_adapter,
    reset_rag_source_adapters,
)
from ai_do_api.domains.retrieval.default_partition_adapters import (
    ensure_retrieval_partition_adapters_registered,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition
from ai_do_api.domains.retrieval.partition_adapter_ids import (
    LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from ai_do_api.domains.retrieval.partition_adapter_registry import (
    RetrievalProjectionBinding,
    get_retrieval_partition_adapter,
    reset_retrieval_partition_adapters,
)
from ai_do_api.domains.retrieval.partitioning import (
    RetrievalPartitionUnbound,
    ensure_default_partition,
)
from ai_do_api.domains.source_access.default_adapters import (
    ensure_builtin_source_access_adapters_registered,
)
from ai_do_api.domains.source_access.policy import SourceAclPolicy
from ai_do_api.domains.source_access.registry import (
    get_source_access_adapter,
    reset_source_access_adapters,
)
from ai_do_api.domains.source_access.resource_types import (
    LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
)


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
            WorkspaceUserBinding.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRecord.__table__,
            LegacyIssueAttachment.__table__,
            LegacyIssueAiChunk.__table__,
            LegacyIssueAttachmentIndexJob.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def test_default_registries_share_source_owned_legacy_issue_partition_adapter() -> None:
    reset_retrieval_partition_adapters()
    reset_source_access_adapters()
    reset_rag_source_adapters()
    try:
        ensure_retrieval_partition_adapters_registered()
        ensure_builtin_source_access_adapters_registered()
        ensure_rag_source_adapters_registered()

        partition_adapter = get_retrieval_partition_adapter(
            LEGACY_ISSUES_RETRIEVAL_PARTITION_ADAPTER_ID
        )
        source_access_adapter = get_source_access_adapter(LEGACY_ISSUE_RECORD_RESOURCE_TYPE)

        assert isinstance(partition_adapter, LegacyIssueRecordSourceAccessAdapter)
        assert isinstance(source_access_adapter, LegacyIssueRecordSourceAccessAdapter)
        assert partition_adapter.partition_adapter_id == source_access_adapter.partition_adapter_id
        assert partition_adapter.resource_types == (LEGACY_ISSUE_RECORD_RESOURCE_TYPE,)
        assert partition_adapter.allowed_candidate_scopes == ("workspace",)
        assert partition_adapter.allowed_transitions == ()
        assert get_rag_resource_adapter(LEGACY_ISSUE_RECORD_RESOURCE_TYPE) is None
    finally:
        reset_rag_source_adapters()
        reset_source_access_adapters()
        reset_retrieval_partition_adapters()


def test_legacy_issue_source_access_enforces_workspace_membership_and_row_scope(
    db: Session,
) -> None:
    workspace_a = Workspace(id="workspace-a", key="workspace-a", name="Workspace A")
    workspace_b = Workspace(id="workspace-b", key="workspace-b", name="Workspace B")
    member = User(
        id="member",
        login_id="member",
        email="member@example.com",
        full_name="Member",
        password_hash="hash",
    )
    outsider = User(
        id="outsider",
        login_id="outsider",
        email="outsider@example.com",
        full_name="Outsider",
        password_hash="hash",
    )
    db.add_all(
        [
            workspace_a,
            workspace_b,
            member,
            outsider,
            WorkspaceUserBinding(
                id="binding-a",
                workspace=workspace_a,
                user=member,
                role="member",
            ),
            LegacyIssueRecord(
                id="record-a",
                workspace_id=workspace_a.id,
                dataset_key="common-master",
            ),
            LegacyIssueRecord(
                id="record-b",
                workspace_id=workspace_b.id,
                dataset_key="common-master",
            ),
        ]
    )
    db.commit()

    member_policy = SourceAclPolicy.for_workspace(db, workspace=workspace_a, user=member)
    outsider_policy = SourceAclPolicy.for_workspace(db, workspace=workspace_a, user=outsider)
    adapter = LegacyIssueRecordSourceAccessAdapter()

    assert adapter.can_read_resource(
        member_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="record-a",
    )
    assert adapter.can_read_rag_resource(
        member_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="record-a",
    )
    assert not adapter.can_read_resource(
        member_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="record-b",
    )
    assert not adapter.can_read_resource(
        outsider_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="record-a",
    )
    assert adapter.has_accessible_source(
        member_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
    )
    assert not adapter.has_accessible_source(
        outsider_policy,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
    )


def test_legacy_issue_partition_adapter_binds_record_partition(db: Session) -> None:
    workspace = Workspace(id="workspace-a", key="workspace-a", name="Workspace A")
    db.add(workspace)
    db.flush()
    partition = ensure_default_partition(
        db,
        source_namespace="legacy_issues",
        candidate_scope_kind="workspace",
        workspace_id=workspace.id,
    )
    db.add_all(
        [
            LegacyIssueRecord(
                id="bound-record",
                workspace_id=workspace.id,
                retrieval_partition_id=partition.id,
                dataset_key="common-master",
            ),
            LegacyIssueRecord(
                id="unbound-record",
                workspace_id=workspace.id,
                dataset_key="common-master",
            ),
        ]
    )
    db.commit()
    adapter = LegacyIssueRecordSourceAccessAdapter()

    assert adapter.bind_resource_partition(
        db,
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="bound-record",
    ) == RetrievalProjectionBinding(
        resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
        resource_id="bound-record",
        partition_id=partition.id,
    )
    with pytest.raises(RetrievalPartitionUnbound, match="missing a partition binding"):
        adapter.bind_resource_partition(
            db,
            resource_type=LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
            resource_id="unbound-record",
        )


def test_legacy_issue_children_inherit_one_revision_partition(db: Session) -> None:
    workspace = Workspace(id="workspace-a", key="workspace-a", name="Workspace A")
    db.add(workspace)
    db.flush()
    revision = LegacyIssueDataRevision(
        id="revision-a",
        workspace_id=workspace.id,
        dataset_key="legacy_issue.common-master",
        revision_no=1,
        status="published",
    )
    ensure_revision_partition(db, revision)
    db.add(revision)
    db.flush()
    record = LegacyIssueRecord(
        id="record-a",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
    )
    ensure_record_partition(db, record, revision=revision)
    db.add(record)
    db.flush()
    attachment = LegacyIssueAttachment(
        id="attachment-a",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        record_id=record.id,
        filename="evidence.txt",
        storage_key="legacy-issues/evidence.txt",
    )
    ensure_attachment_partition(db, attachment, record=record)
    db.add(attachment)
    db.flush()
    chunk = LegacyIssueAiChunk(
        id="chunk-a",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        record_id=record.id,
        attachment_id=attachment.id,
        chunk_key="attachment:attachment-a:0001",
        chunk_kind="attachment_text",
        search_text="evidence",
    )
    ensure_chunk_partition(db, chunk, record=record, attachment=attachment)
    job = LegacyIssueAttachmentIndexJob(
        id="job-a",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        attachment_id=attachment.id,
    )
    ensure_attachment_job_partition(db, job, attachment=attachment)

    assert {
        revision.retrieval_partition_id,
        record.retrieval_partition_id,
        attachment.retrieval_partition_id,
        chunk.retrieval_partition_id,
        job.retrieval_partition_id,
    } == {revision.retrieval_partition_id}

    chunk.retrieval_partition_id = "00000000-0000-0000-0000-000000000099"
    with pytest.raises(LegacyIssuePartitionMismatch, match="does not match attachment"):
        ensure_chunk_partition(db, chunk, record=record, attachment=attachment)


def test_draft_projection_rebuilds_current_text_and_reuses_only_exact_embeddings(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-copy", key="workspace-copy", name="Workspace Copy")
    revision_key = legacy_issue_dataset_revision_key(
        COMMON_MASTER_DATASET_KEY,
        "aircon",
    )
    source_revision = LegacyIssueDataRevision(
        id="published-copy",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        revision_no=1,
        status="published",
    )
    target_revision = LegacyIssueDataRevision(
        id="draft-copy",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        status="draft",
        base_revision_id=source_revision.id,
    )
    db.add(workspace)
    db.flush()
    ensure_revision_partition(db, source_revision)
    db.add(source_revision)
    db.flush()
    ensure_revision_partition(db, target_revision)
    db.add(target_revision)
    db.flush()
    source_record = LegacyIssueRecord(
        id="source-copy-record",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=source_revision.id,
        stable_record_id="stable-copy-record",
        field_values={"symptom": "압축기 소음"},
    )
    ensure_record_partition(db, source_record, revision=source_revision)
    db.add(source_record)
    db.flush()
    definition = DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY]
    monkeypatch.setattr(
        ai_search,
        "_legacy_embedding_client",
        lambda: pytest.fail("draft projection must not call the embedding provider"),
    )
    ai_search.reindex_legacy_issue_revision_ai_chunks(
        db,
        definition,
        workspace=workspace,
        revision=source_revision,
        embed=False,
    )
    source_summary = db.scalar(
        select(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.revision_id == source_revision.id,
            LegacyIssueAiChunk.chunk_key == "summary",
        )
    )
    source_field_chunk = db.scalar(
        select(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.revision_id == source_revision.id,
            LegacyIssueAiChunk.field_key == "symptom",
        )
    )
    assert source_summary is not None
    assert source_field_chunk is not None
    source_summary.search_text = source_summary.search_text.replace(
        f"{definition.title_ko} ",
        f"{definition.title_ko} revision: 1 ",
        1,
    )
    for source_chunk in (source_summary, source_field_chunk):
        source_chunk.embedding_vector = "[0.1]"
        source_chunk.embedding_model = ai_search.get_settings().rag_local_embedding_model
        source_chunk.embedding_dimensions = (
            ai_search.get_legacy_issue_settings().ai_embedding_dimensions
        )
        source_chunk.embedding_status = "embedded"
    db.flush()

    copy_dataset_revision_records(
        db,
        definition,
        workspace=workspace,
        source_revision=source_revision,
        target_revision=target_revision,
        module_key="aircon",
    )
    ai_search.reindex_legacy_issue_revision_ai_chunks(
        db,
        definition,
        workspace=workspace,
        revision=target_revision,
        embed=False,
        reuse_embeddings_from_revision=source_revision,
    )
    db.flush()

    target_record = db.scalar(
        select(LegacyIssueRecord).where(
            LegacyIssueRecord.revision_id == target_revision.id,
        )
    )
    assert target_record is not None
    target_summary = db.scalar(
        select(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.revision_id == target_revision.id,
            LegacyIssueAiChunk.record_id == target_record.id,
            LegacyIssueAiChunk.chunk_key == "summary",
        )
    )
    target_field_chunk = db.scalar(
        select(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.revision_id == target_revision.id,
            LegacyIssueAiChunk.record_id == target_record.id,
            LegacyIssueAiChunk.field_key == "symptom",
        )
    )
    assert target_summary is not None
    assert target_field_chunk is not None
    assert target_summary.search_text != source_summary.search_text
    assert target_summary.embedding_vector == source_summary.embedding_vector
    assert target_summary.embedding_status == "embedded"
    assert target_field_chunk.search_text == source_field_chunk.search_text
    assert target_field_chunk.embedding_vector == source_field_chunk.embedding_vector
    assert target_field_chunk.embedding_status == "embedded"
    assert target_field_chunk.retrieval_partition_id == target_revision.retrieval_partition_id


def test_legacy_issue_candidate_query_dual_reads_null_and_resolved_partition(
    db: Session,
) -> None:
    workspace = Workspace(id="workspace-a", key="workspace-a", name="Workspace A")
    foreign_workspace = Workspace(
        id="workspace-b",
        key="workspace-b",
        name="Workspace B",
    )
    db.add_all([workspace, foreign_workspace])
    db.flush()
    allowed = ensure_default_partition(
        db,
        source_namespace="legacy_issues",
        candidate_scope_kind="workspace",
        workspace_id=workspace.id,
    )
    excluded = RetrievalPartition(
        source_namespace="legacy_issues",
        managed_workspace_id=workspace.id,
        candidate_scope_kind="workspace",
        candidate_workspace_id=workspace.id,
        state="transitioning",
        metadata_version=1,
        is_default_ingest=False,
    )
    db.add(excluded)
    db.flush()
    revision = LegacyIssueDataRevision(
        id="revision-a",
        workspace_id=workspace.id,
        dataset_key="legacy_issue.common-master",
        revision_no=1,
        status="published",
    )
    foreign_revision = LegacyIssueDataRevision(
        id="revision-b",
        workspace_id=foreign_workspace.id,
        dataset_key="legacy_issue.common-master",
        revision_no=1,
        status="published",
    )
    allowed_record = LegacyIssueRecord(
        id="record-allowed",
        workspace_id=workspace.id,
        retrieval_partition_id=allowed.id,
        dataset_key="common-master",
        revision_id=revision.id,
    )
    excluded_record = LegacyIssueRecord(
        id="record-excluded",
        workspace_id=workspace.id,
        retrieval_partition_id=excluded.id,
        dataset_key="common-master",
        revision_id=revision.id,
    )
    legacy_record = LegacyIssueRecord(
        id="record-legacy-null",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
    )
    foreign_legacy_record = LegacyIssueRecord(
        id="record-foreign-legacy-null",
        workspace_id=foreign_workspace.id,
        dataset_key="common-master",
        revision_id=foreign_revision.id,
    )
    db.add_all(
        [
            revision,
            foreign_revision,
            allowed_record,
            excluded_record,
            legacy_record,
            foreign_legacy_record,
        ]
    )
    db.flush()
    db.add_all(
        [
            LegacyIssueAiChunk(
                id="chunk-allowed",
                workspace_id=workspace.id,
                retrieval_partition_id=allowed.id,
                dataset_key="common-master",
                revision_id=revision.id,
                record_id=allowed_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="partition evidence",
            ),
            LegacyIssueAiChunk(
                id="chunk-excluded",
                workspace_id=workspace.id,
                retrieval_partition_id=excluded.id,
                dataset_key="common-master",
                revision_id=revision.id,
                record_id=excluded_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="partition evidence",
            ),
            LegacyIssueAiChunk(
                id="chunk-legacy-null",
                workspace_id=workspace.id,
                dataset_key="common-master",
                revision_id=revision.id,
                record_id=legacy_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="partition evidence",
            ),
            LegacyIssueAiChunk(
                id="chunk-foreign-legacy-null",
                workspace_id=foreign_workspace.id,
                dataset_key="common-master",
                revision_id=foreign_revision.id,
                record_id=foreign_legacy_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="partition evidence",
            ),
        ]
    )
    db.flush()

    rows = _exact_candidates(
        db,
        workspace=workspace,
        dataset_keys=("common-master",),
        revision_ids=(revision.id,),
        partition_ids=(allowed.id,),
        token_specs=(_WeightedToken("partition", 1.0, "primary"),),
        limit=10,
    )

    assert {candidate.id for candidate, _score, _method in rows} == {
        "chunk-allowed",
        "chunk-legacy-null",
    }

    null_only_rows = _exact_candidates(
        db,
        workspace=workspace,
        dataset_keys=("common-master",),
        revision_ids=(revision.id,),
        partition_ids=(),
        token_specs=(_WeightedToken("partition", 1.0, "primary"),),
        limit=10,
    )

    assert [candidate.id for candidate, _score, _method in null_only_rows] == ["chunk-legacy-null"]


def test_legacy_issue_search_keeps_null_projection_when_no_partition_exists(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-a", key="workspace-a", name="Workspace A")
    revision = LegacyIssueDataRevision(
        id="revision-a",
        workspace_id=workspace.id,
        dataset_key="legacy_issue.common-master",
        revision_no=1,
        status="published",
    )
    record = LegacyIssueRecord(
        id="record-legacy-null",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        field_values={"notes": "partition evidence"},
    )
    db.add_all([workspace, revision, record])
    db.flush()
    chunk = LegacyIssueAiChunk(
        id="chunk-legacy-null",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        record_id=record.id,
        chunk_key="summary",
        chunk_kind="record_summary",
        search_text="partition evidence",
    )
    db.add(chunk)
    db.flush()
    assert db.query(RetrievalPartition).count() == 0
    monkeypatch.setattr(
        ai_search,
        "ensure_legacy_issue_ai_projection_for_effective_revisions",
        lambda *_args, **_kwargs: {"common-master": [revision]},
    )
    monkeypatch.setattr(ai_search, "_rerank_candidates", lambda *_args, **_kwargs: False)

    evidence, profile = ai_search.search_legacy_issue_evidence(
        db,
        workspace=workspace,
        plan=LegacyIssueAssistantSearchPlan(
            query="partition",
            dataset_keys=("common-master",),
            primary_keywords=("partition",),
        ),
        limit=5,
    )

    assert [item.record_id for item in evidence] == [record.id]
    assert profile.candidate_count == 1
    assert profile.evidence_count == 1
    assert db.query(RetrievalPartition).count() == 0


def test_legacy_issue_search_applies_record_acl_before_reranking(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(
        id="workspace-acl",
        key="workspace-acl",
        name="Workspace ACL",
    )
    revision = LegacyIssueDataRevision(
        id="revision-acl",
        workspace_id=workspace.id,
        dataset_key="legacy_issue.common-master",
        revision_no=1,
        status="published",
    )
    allowed_record = LegacyIssueRecord(
        id="record-allowed",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        field_values={"notes": "acl evidence"},
    )
    denied_record = LegacyIssueRecord(
        id="record-denied",
        workspace_id=workspace.id,
        dataset_key="common-master",
        revision_id=revision.id,
        field_values={"notes": "acl evidence"},
    )
    db.add_all([workspace, revision, allowed_record, denied_record])
    db.flush()
    db.add_all(
        [
            LegacyIssueAiChunk(
                id="chunk-allowed",
                workspace_id=workspace.id,
                dataset_key="common-master",
                revision_id=revision.id,
                record_id=allowed_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="acl evidence",
            ),
            LegacyIssueAiChunk(
                id="chunk-denied",
                workspace_id=workspace.id,
                dataset_key="common-master",
                revision_id=revision.id,
                record_id=denied_record.id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="acl evidence",
            ),
        ]
    )
    db.flush()
    monkeypatch.setattr(
        ai_search,
        "ensure_legacy_issue_ai_projection_for_effective_revisions",
        lambda *_args, **_kwargs: {"common-master": [revision]},
    )
    reranked_record_ids: list[str] = []

    def capture_rerank(candidates, **_kwargs):
        reranked_record_ids.extend(
            candidate.chunk.record_id for candidate in candidates.values()
        )
        return False

    monkeypatch.setattr(ai_search, "_rerank_candidates", capture_rerank)

    evidence, profile = ai_search.search_legacy_issue_evidence(
        db,
        workspace=workspace,
        plan=LegacyIssueAssistantSearchPlan(
            query="acl evidence",
            dataset_keys=("common-master",),
            primary_keywords=("acl", "evidence"),
        ),
        limit=5,
        candidate_record_authorizer=lambda _record_ids: frozenset(
            {allowed_record.id}
        ),
    )

    assert reranked_record_ids == [allowed_record.id]
    assert [item.record_id for item in evidence] == [allowed_record.id]
    assert profile.candidate_count == 1


def test_legacy_issue_search_uses_active_draft_instead_of_published_revision(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-effective", key="workspace-effective", name="Workspace")
    revision_key = legacy_issue_dataset_revision_key(
        COMMON_MASTER_DATASET_KEY,
        "aircon",
    )
    older_published = LegacyIssueDataRevision(
        id="older-published-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        revision_no=1,
        status="published",
    )
    published = LegacyIssueDataRevision(
        id="published-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        revision_no=2,
        status="published",
    )
    draft = LegacyIssueDataRevision(
        id="draft-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        status="draft",
        base_revision_id=published.id,
    )
    canceled = LegacyIssueDataRevision(
        id="canceled-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        status="canceled",
        base_revision_id=published.id,
    )
    older_record = LegacyIssueRecord(
        id="older-published-record",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=older_published.id,
        stable_record_id="stable-older-published",
        field_values={"problem": "effective keyword older"},
    )
    published_record = LegacyIssueRecord(
        id="published-record",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=published.id,
        stable_record_id="stable-published",
        field_values={"problem": "effective keyword published"},
    )
    draft_record = LegacyIssueRecord(
        id="draft-record",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=draft.id,
        stable_record_id="stable-draft",
        field_values={"problem": "effective keyword draft"},
    )
    canceled_record = LegacyIssueRecord(
        id="canceled-record",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=canceled.id,
        stable_record_id="stable-canceled",
        field_values={"problem": "effective keyword canceled"},
    )
    db.add_all(
        [
            workspace,
            older_published,
            published,
            draft,
            canceled,
            older_record,
            published_record,
            draft_record,
            canceled_record,
        ]
    )
    db.flush()
    db.add_all(
        [
            LegacyIssueAiChunk(
                id="older-published-summary",
                workspace_id=workspace.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id=older_published.id,
                record_id=older_record.id,
                stable_record_id=older_record.stable_record_id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="effective keyword older",
            ),
            LegacyIssueAiChunk(
                id="published-summary",
                workspace_id=workspace.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id=published.id,
                record_id=published_record.id,
                stable_record_id=published_record.stable_record_id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="effective keyword published",
            ),
            LegacyIssueAiChunk(
                id="draft-summary",
                workspace_id=workspace.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id=draft.id,
                record_id=draft_record.id,
                stable_record_id=draft_record.stable_record_id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="effective keyword draft",
            ),
            LegacyIssueAiChunk(
                id="canceled-summary",
                workspace_id=workspace.id,
                dataset_key=COMMON_MASTER_DATASET_KEY,
                revision_id=canceled.id,
                record_id=canceled_record.id,
                stable_record_id=canceled_record.stable_record_id,
                chunk_key="summary",
                chunk_kind="record_summary",
                search_text="effective keyword canceled",
            ),
        ]
    )
    db.flush()
    monkeypatch.setattr(ai_search, "_rerank_candidates", lambda *_args, **_kwargs: False)

    evidence, profile = ai_search.search_legacy_issue_evidence(
        db,
        workspace=workspace,
        plan=LegacyIssueAssistantSearchPlan(
            query="effective keyword",
            dataset_keys=(COMMON_MASTER_DATASET_KEY,),
            primary_keywords=("effective", "keyword"),
        ),
        limit=5,
        module_keys=frozenset({"aircon"}),
    )

    assert [item.record_id for item in evidence] == [draft_record.id]
    assert profile.searched_revision_ids == (draft.id,)

    draft.status = "canceled"
    db.flush()

    fallback = ai_search._effective_revision_for_ai(
        db,
        workspace=workspace,
        dataset_key=revision_key,
    )

    assert fallback is not None
    assert fallback.id == published.id


def test_effective_draft_projection_repairs_partially_indexed_records(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-draft", key="workspace-draft", name="Workspace Draft")
    revision_key = legacy_issue_dataset_revision_key(
        COMMON_MASTER_DATASET_KEY,
        "aircon",
    )
    published = LegacyIssueDataRevision(
        id="published-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        revision_no=1,
        status="published",
    )
    draft = LegacyIssueDataRevision(
        id="draft-aircon",
        workspace_id=workspace.id,
        dataset_key=revision_key,
        status="draft",
        base_revision_id=published.id,
    )
    first_record = LegacyIssueRecord(
        id="draft-record-1",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=draft.id,
        stable_record_id="stable-1",
        field_values={"problem": "draft first"},
    )
    second_record = LegacyIssueRecord(
        id="draft-record-2",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        module_key="aircon",
        revision_id=draft.id,
        stable_record_id="stable-2",
        field_values={"problem": "draft second"},
    )
    partial_chunk = LegacyIssueAiChunk(
        id="draft-summary-1",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        revision_id=draft.id,
        record_id=first_record.id,
        stable_record_id=first_record.stable_record_id,
        chunk_key="summary",
        chunk_kind="record_summary",
        search_text="draft first",
    )
    db.add_all(
        [
            workspace,
            published,
            draft,
            first_record,
            second_record,
        ]
    )
    db.flush()
    db.add(partial_chunk)
    db.flush()
    monkeypatch.setattr(
        ai_search,
        "get_dataset_definition_with_all_module_fields",
        lambda *_args, **_kwargs: DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
    )
    monkeypatch.setattr(
        ai_search,
        "_legacy_embedding_client",
        lambda: pytest.fail("projection repair must not call the embedding provider"),
    )

    def repair_in_caller_transaction(_db, *, revision_id, **_kwargs):
        revision = db.get(LegacyIssueDataRevision, revision_id)
        assert revision is not None
        ai_search._repair_legacy_issue_record_projection_without_embeddings(
            db,
            DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
            workspace=workspace,
            revision=revision,
        )
        return True, 0

    monkeypatch.setattr(
        ai_search,
        "_repair_legacy_issue_ai_projection_in_new_transaction",
        repair_in_caller_transaction,
    )

    selected = ai_search.ensure_legacy_issue_ai_projection_for_effective_revisions(
        db,
        workspace=workspace,
        dataset_keys=(COMMON_MASTER_DATASET_KEY,),
        module_keys=frozenset({"aircon"}),
    )

    summary_record_ids = set(
        db.scalars(
            select(LegacyIssueAiChunk.record_id).where(
                LegacyIssueAiChunk.workspace_id == workspace.id,
                LegacyIssueAiChunk.dataset_key == COMMON_MASTER_DATASET_KEY,
                LegacyIssueAiChunk.revision_id == draft.id,
                LegacyIssueAiChunk.attachment_id.is_(None),
                LegacyIssueAiChunk.chunk_key == "summary",
            )
        )
    )
    assert [revision.id for revision in selected[COMMON_MASTER_DATASET_KEY]] == [draft.id]
    assert summary_record_ids == {first_record.id, second_record.id}


def test_projection_repair_commits_in_independent_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
    revision = LegacyIssueDataRevision(
        id="draft-aircon",
        workspace_id=workspace.id,
        dataset_key=legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        ),
        status="draft",
    )
    events: list[str] = []

    class RepairSession:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            events.append("exit")

        @staticmethod
        def get(model, row_id):
            assert model is Workspace
            assert row_id == workspace.id
            return workspace

        @staticmethod
        def commit():
            events.append("commit")

    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        lambda _db, *, workspace, dataset_key, for_update=False: (
            revision if for_update else pytest.fail("repair must lock the effective revision")
        ),
    )
    monkeypatch.setattr(
        ai_search,
        "_legacy_issue_projection_counts",
        lambda *_args, **_kwargs: (2, 1, 1, 0),
    )
    monkeypatch.setattr(
        ai_search,
        "get_dataset_definition_with_all_module_fields",
        lambda *_args, **_kwargs: DATASET_DEFINITIONS[COMMON_MASTER_DATASET_KEY],
    )
    monkeypatch.setattr(
        ai_search,
        "_repair_legacy_issue_record_projection_without_embeddings",
        lambda repair_db, _definition, *, workspace, revision: (
            events.append("repair_records") or True
        ),
    )

    repaired = ai_search._repair_legacy_issue_ai_projection_in_new_transaction(
        object(),
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        revision_dataset_key=revision.dataset_key,
        revision_id=revision.id,
        attachment_limit=0,
        session_factory=RepairSession,
    )

    assert repaired == (True, 0)
    assert events == ["enter", "repair_records", "commit", "exit"]


def test_projection_repair_requeues_existing_draft_unindexed_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
    revision = LegacyIssueDataRevision(
        id="draft-aircon",
        workspace_id=workspace.id,
        dataset_key=legacy_issue_dataset_revision_key(
            COMMON_MASTER_DATASET_KEY,
            "aircon",
        ),
        status="draft",
    )
    attachment = LegacyIssueAttachment(
        id="draft-attachment",
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        revision_id=revision.id,
        stable_record_id="stable-1",
        record_id="draft-record",
        filename="evidence.pdf",
        content_type="application/pdf",
        size_bytes=123,
        storage_key="legacy-issues/evidence.pdf",
        index_status="not_indexed",
    )
    events: list[str] = []

    class RepairSession:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            events.append("exit")

        @staticmethod
        def get(model, row_id):
            assert model is Workspace
            assert row_id == workspace.id
            return workspace

        @staticmethod
        def scalars(_statement):
            return [attachment]

        @staticmethod
        def commit():
            events.append("commit")

    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        lambda _db, *, workspace, dataset_key, for_update=False: (
            revision if for_update else pytest.fail("repair must lock the effective revision")
        ),
    )
    monkeypatch.setattr(
        ai_search,
        "_legacy_issue_projection_counts",
        lambda *_args, **_kwargs: (1, 1, 1, 1),
    )
    monkeypatch.setattr(
        ai_search,
        "_repair_legacy_issue_record_projection_without_embeddings",
        lambda *_args, **_kwargs: pytest.fail("complete record projection must not reindex"),
    )

    def fake_enqueue(_db, *, attachment, trigger):
        assert trigger == "effective_revision_reconcile"
        attachment.index_status = "pending"
        events.append("enqueue")

    monkeypatch.setattr(
        "ai_do_api.domains.legacy_issues.attachment_indexing."
        "enqueue_legacy_issue_attachment_index_job",
        fake_enqueue,
    )

    repaired = ai_search._repair_legacy_issue_ai_projection_in_new_transaction(
        object(),
        workspace_id=workspace.id,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        revision_dataset_key=revision.dataset_key,
        revision_id=revision.id,
        attachment_limit=25,
        session_factory=RepairSession,
    )

    assert repaired == (True, 1)
    assert attachment.index_status == "pending"
    assert events == ["enter", "enqueue", "commit", "exit"]


def test_attachment_reconciliation_budget_is_shared_across_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
    revisions = {
        module_key: LegacyIssueDataRevision(
            id=f"draft-{module_key}",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                module_key,
            ),
            status="draft",
        )
        for module_key in ("aircon", "heat-exchanger")
    }
    repair_limits: list[tuple[str, int]] = []

    monkeypatch.setattr(
        ai_search,
        "get_legacy_issue_settings",
        lambda: type("Settings", (), {"ai_attachment_index_enabled": True})(),
    )
    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        lambda _db, *, workspace, dataset_key: next(
            revision for revision in revisions.values() if revision.dataset_key == dataset_key
        ),
    )
    monkeypatch.setattr(
        ai_search,
        "_legacy_issue_projection_counts",
        lambda *_args, **_kwargs: (1, 1, 1, 20),
    )

    def fake_repair(
        _db,
        *,
        revision_id: str,
        attachment_limit: int,
        **_kwargs,
    ) -> tuple[bool, int]:
        repair_limits.append((revision_id, attachment_limit))
        actual_count = 7 if revision_id == "draft-aircon" else 20
        return True, min(actual_count, attachment_limit)

    monkeypatch.setattr(
        ai_search,
        "_repair_legacy_issue_ai_projection_in_new_transaction",
        fake_repair,
    )

    selected = ai_search.ensure_legacy_issue_ai_projection_for_effective_revisions(
        object(),
        workspace=workspace,
        dataset_keys=(COMMON_MASTER_DATASET_KEY,),
        module_keys=frozenset(revisions),
    )

    assert repair_limits == [
        ("draft-aircon", 25),
        ("draft-heat-exchanger", 18),
    ]
    assert [revision.id for revision in selected[COMMON_MASTER_DATASET_KEY]] == [
        "draft-aircon",
        "draft-heat-exchanger",
    ]


def test_record_projection_repair_runs_after_attachment_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
    revisions = {
        module_key: LegacyIssueDataRevision(
            id=f"draft-{module_key}",
            workspace_id=workspace.id,
            dataset_key=legacy_issue_dataset_revision_key(
                COMMON_MASTER_DATASET_KEY,
                module_key,
            ),
            status="draft",
        )
        for module_key in ("aircon", "compressor-electric", "heat-exchanger")
    }
    repair_limits: list[tuple[str, int]] = []

    monkeypatch.setattr(
        ai_search,
        "get_legacy_issue_settings",
        lambda: type("Settings", (), {"ai_attachment_index_enabled": True})(),
    )
    monkeypatch.setattr(
        ai_search,
        "_effective_revision_for_ai",
        lambda _db, *, workspace, dataset_key: next(
            revision for revision in revisions.values() if revision.dataset_key == dataset_key
        ),
    )

    def fake_projection_counts(
        _db,
        *,
        revision_id: str,
        **_kwargs,
    ) -> tuple[int, int, int, int]:
        if revision_id == "draft-aircon":
            return 1, 1, 1, 30
        if revision_id == "draft-compressor-electric":
            return 2, 1, 1, 10
        return 1, 1, 1, 10

    monkeypatch.setattr(
        ai_search,
        "_legacy_issue_projection_counts",
        fake_projection_counts,
    )

    def fake_repair(
        _db,
        *,
        revision_id: str,
        attachment_limit: int,
        **_kwargs,
    ) -> tuple[bool, int]:
        repair_limits.append((revision_id, attachment_limit))
        return True, attachment_limit

    monkeypatch.setattr(
        ai_search,
        "_repair_legacy_issue_ai_projection_in_new_transaction",
        fake_repair,
    )

    selected = ai_search.ensure_legacy_issue_ai_projection_for_effective_revisions(
        object(),
        workspace=workspace,
        dataset_keys=(COMMON_MASTER_DATASET_KEY,),
        module_keys=frozenset(revisions),
    )

    assert repair_limits == [
        ("draft-aircon", 25),
        ("draft-compressor-electric", 0),
    ]
    assert [revision.id for revision in selected[COMMON_MASTER_DATASET_KEY]] == [
        "draft-aircon",
        "draft-compressor-electric",
        "draft-heat-exchanger",
    ]
