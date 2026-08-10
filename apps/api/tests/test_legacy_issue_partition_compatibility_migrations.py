from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    _full_text_candidates,
    _pgvector_candidates,
    _term_index_candidates,
    _trigram_candidates,
)
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.retrieval.models import RetrievalPartition
from open_alm_api.domains.retrieval.partitioning import ensure_default_partition


pytestmark = pytest.mark.migration

_EMBEDDING = [1.0, *([0.0] * 1023)]
_EMBEDDING_LITERAL = "[" + ",".join(str(value) for value in _EMBEDDING) + "]"


def test_postgres_candidate_paths_dual_read_null_and_authorized_partitions(
    application_postgres_dsn: str,
) -> None:
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db, db.begin():
            workspace = Workspace(
                id="legacy-partition-compat-workspace",
                key="legacy-partition-compat-workspace",
                name="Legacy partition compatibility",
            )
            db.add(workspace)
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
                id="legacy-partition-compat-revision",
                workspace_id=workspace.id,
                dataset_key="legacy_issue.common-master",
                revision_no=1,
                status="published",
            )
            records = [
                LegacyIssueRecord(
                    id="legacy-partition-record-allowed",
                    workspace_id=workspace.id,
                    retrieval_partition_id=allowed.id,
                    dataset_key="common-master",
                    revision_id=revision.id,
                ),
                LegacyIssueRecord(
                    id="legacy-partition-record-null",
                    workspace_id=workspace.id,
                    dataset_key="common-master",
                    revision_id=revision.id,
                ),
                LegacyIssueRecord(
                    id="legacy-partition-record-excluded",
                    workspace_id=workspace.id,
                    retrieval_partition_id=excluded.id,
                    dataset_key="common-master",
                    revision_id=revision.id,
                ),
            ]
            db.add(revision)
            db.add_all(records)
            db.flush()
            chunks = [
                _chunk(
                    chunk_id="legacy-partition-chunk-allowed",
                    record=records[0],
                    revision=revision,
                    partition_id=allowed.id,
                ),
                _chunk(
                    chunk_id="legacy-partition-chunk-null",
                    record=records[1],
                    revision=revision,
                    partition_id=None,
                ),
                _chunk(
                    chunk_id="legacy-partition-chunk-excluded",
                    record=records[2],
                    revision=revision,
                    partition_id=excluded.id,
                ),
            ]
            db.add_all(chunks)
            db.flush()

            plan = LegacyIssueAssistantSearchPlan(
                query="partition evidence",
                dataset_keys=("common-master",),
                primary_keywords=("partition",),
            )
            common = {
                "workspace": workspace,
                "dataset_keys": ("common-master",),
                "revision_ids": (revision.id,),
                "plan": plan,
                "limit": 20,
            }
            candidate_calls = (
                lambda partition_ids: _full_text_candidates(
                    db,
                    partition_ids=partition_ids,
                    **common,
                ),
                lambda partition_ids: _trigram_candidates(
                    db,
                    partition_ids=partition_ids,
                    **common,
                ),
                lambda partition_ids: _term_index_candidates(
                    db,
                    partition_ids=partition_ids,
                    **common,
                ),
                lambda partition_ids: _pgvector_candidates(
                    db,
                    workspace=workspace,
                    dataset_keys=("common-master",),
                    revision_ids=(revision.id,),
                    partition_ids=partition_ids,
                    query_embedding=_EMBEDDING,
                    limit=20,
                ),
            )

            for candidate_call in candidate_calls:
                authorized = candidate_call((allowed.id,))
                assert {row.id for row, _score, _method in authorized} == {
                    "legacy-partition-chunk-allowed",
                    "legacy-partition-chunk-null",
                }
                null_only = candidate_call(())
                assert {row.id for row, _score, _method in null_only} == {
                    "legacy-partition-chunk-null"
                }
    finally:
        engine.dispose()


def _chunk(
    *,
    chunk_id: str,
    record: LegacyIssueRecord,
    revision: LegacyIssueDataRevision,
    partition_id: str | None,
) -> LegacyIssueAiChunk:
    return LegacyIssueAiChunk(
        id=chunk_id,
        workspace_id=record.workspace_id,
        retrieval_partition_id=partition_id,
        dataset_key="common-master",
        revision_id=revision.id,
        record_id=record.id,
        chunk_key="summary",
        chunk_kind="record_summary",
        search_text="partition evidence",
        search_terms=["partition", "evidence"],
        embedding_vector=_EMBEDDING_LITERAL,
        embedding_dimensions=len(_EMBEDDING),
        embedding_status="embedded",
    )
