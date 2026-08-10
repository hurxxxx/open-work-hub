from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.legacy_issues.ai_search import (
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
    sanitize_legacy_issue_search_plan,
    search_legacy_issue_evidence,
)
from open_alm_api.domains.legacy_issues.analysis_v2.contracts import RetrievalHit
from open_alm_api.domains.legacy_issues.analysis_v2.execution import AnalysisSqlScope
from open_alm_api.domains.legacy_issues.analysis_v2.retrieval import RetrievalRequest
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.retrieval.partitioning import (
    RetrievalReadScope,
    flatten_read_scope,
)
from open_alm_api.domains.source_access import SourceAclPolicy


MAX_NATIVE_EVIDENCE_PREFETCH = 50
NativeSearchFunction = Callable[
    ...,
    tuple[list[LegacyIssueEvidence], LegacyIssueSearchProfile],
]


class NativeLegacyIssueEvidenceRetriever:
    """Use the CRUD-synchronized legacy search, then re-hydrate final ACL rows."""

    backend_id = "legacy-issues-native-postgres-v1"

    def __init__(
        self,
        *,
        db: Session,
        workspace: Workspace,
        acl_policy: SourceAclPolicy,
        sql_scope: AnalysisSqlScope,
        read_scope: RetrievalReadScope,
        search_fn: NativeSearchFunction = search_legacy_issue_evidence,
    ) -> None:
        readable_partitions = {
            str(value) for value in flatten_read_scope(read_scope)
        }
        if sql_scope.workspace_id != workspace.id:
            raise ValueError("native evidence scope escaped its workspace")
        if not set(sql_scope.partition_ids).issubset(readable_partitions):
            raise ValueError("native evidence scope contains unreadable partitions")
        self._db = db
        self._workspace = workspace
        self._acl_policy = acl_policy
        self._scope = sql_scope
        self._search = search_fn

    def retrieve(self, request: RetrievalRequest) -> tuple[RetrievalHit, ...]:
        plan = sanitize_legacy_issue_search_plan(
            question=request.query,
            dataset_keys=None,
        )
        prefetch = min(
            max(request.limit * 3, 20),
            MAX_NATIVE_EVIDENCE_PREFETCH,
        )
        evidence, _profile = self._search(
            self._db,
            workspace=self._workspace,
            plan=plan,
            limit=prefetch,
            module_keys=frozenset(self._scope.module_keys),
            candidate_record_authorizer=self._authorized_record_ids,
        )
        evidence_by_id = {
            item.record_id: item
            for item in evidence
            if item.record_id
        }
        if not evidence_by_id:
            return ()

        allowed_ids = self._authorized_record_ids(tuple(evidence_by_id))
        if not allowed_ids:
            return ()

        hydrated = self._db.execute(
            select(
                LegacyIssueRecord,
                LegacyIssueDataRevision.status,
                LegacyIssueDataRevision.revision_no,
            )
            .outerjoin(
                LegacyIssueDataRevision,
                LegacyIssueDataRevision.id == LegacyIssueRecord.revision_id,
            )
            .where(
                LegacyIssueRecord.id.in_(allowed_ids),
                LegacyIssueRecord.workspace_id == self._scope.workspace_id,
                LegacyIssueRecord.module_key.in_(self._scope.module_keys),
                LegacyIssueRecord.revision_id.in_(self._scope.revision_ids),
                or_(
                    LegacyIssueRecord.retrieval_partition_id.is_(None),
                    LegacyIssueRecord.retrieval_partition_id.in_(
                        self._scope.partition_ids
                    ),
                ),
            )
        ).all()
        current_rows = {
            record.id: (record, revision_status, revision_no)
            for record, revision_status, revision_no in hydrated
            if _row_in_scope(record, scope=self._scope)
        }

        hits: list[RetrievalHit] = []
        seen: set[str] = set()
        for item in evidence:
            if item.record_id in seen:
                continue
            current = current_rows.get(item.record_id)
            if current is None:
                continue
            seen.add(item.record_id)
            record, revision_status, revision_no = current
            text = _current_record_text(record)
            hits.append(
                RetrievalHit(
                    hit_id=f"legacy_issue_record:{record.id}",
                    text=text,
                    score=max(float(item.score or 0), 0),
                    resource_type="legacy_issue_record",
                    resource_id=record.id,
                    partition_id=record.retrieval_partition_id,
                    metadata={
                        "title": _record_title(record),
                        "dataset_key": item.dataset_key,
                        "dataset_title": item.dataset_title,
                        "revision_id": record.revision_id,
                        "revision_status": revision_status,
                        "revision_no": revision_no,
                        "module_key": record.module_key,
                        "stable_record_id": record.stable_record_id,
                        "vehicle_model": record.vehicle_model,
                        "methods": list(item.methods),
                        "matched_fields": list(item.matched_fields),
                    },
                )
            )
            if len(hits) >= request.limit:
                break
        return tuple(hits)

    def _authorized_record_ids(
        self,
        record_ids: tuple[str, ...],
    ) -> frozenset[str]:
        allowed = self._acl_policy.authorize_many_resources(
            ("legacy_issue_record", record_id) for record_id in record_ids
        )
        return frozenset(
            resource_id
            for resource_type, resource_id in allowed
            if resource_type == "legacy_issue_record"
        )


def build_native_legacy_issue_evidence_retriever(
    *,
    db: Session,
    workspace: Workspace,
    acl_policy: SourceAclPolicy,
    sql_scope: AnalysisSqlScope,
    read_scope: RetrievalReadScope,
) -> NativeLegacyIssueEvidenceRetriever:
    return NativeLegacyIssueEvidenceRetriever(
        db=db,
        workspace=workspace,
        acl_policy=acl_policy,
        sql_scope=sql_scope,
        read_scope=read_scope,
    )


def _row_in_scope(
    record: LegacyIssueRecord,
    *,
    scope: AnalysisSqlScope,
) -> bool:
    return (
        record.workspace_id == scope.workspace_id
        and record.module_key in scope.module_keys
        and record.revision_id in scope.revision_ids
        and (
            record.retrieval_partition_id is None
            or record.retrieval_partition_id in scope.partition_ids
        )
    )


def _current_record_text(
    record: LegacyIssueRecord,
) -> str:
    if record.search_text and record.search_text.strip():
        return record.search_text.strip()[:20_000]
    values = [
        _record_title(record),
        record.symptom,
        record.cause,
        record.countermeasure,
        *(record.field_values or {}).values(),
    ]
    text = "\n".join(
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    )
    return (text or record.id)[:20_000]


def _record_title(record: LegacyIssueRecord) -> str:
    return " / ".join(
        str(value).strip()
        for value in (
            record.legacy_issue_number,
            record.vehicle_model,
            record.symptom,
        )
        if value is not None and str(value).strip()
    ) or record.id


__all__ = [
    "NativeLegacyIssueEvidenceRetriever",
    "build_native_legacy_issue_evidence_retriever",
]
