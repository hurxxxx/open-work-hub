from __future__ import annotations

from types import SimpleNamespace

from ai_do_api.domains.legacy_issues.ai_search import (
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
)
from ai_do_api.domains.legacy_issues.analysis_v2.execution import AnalysisSqlScope
from ai_do_api.domains.legacy_issues.analysis_v2.native_evidence import (
    NativeLegacyIssueEvidenceRetriever,
)
from ai_do_api.domains.legacy_issues.analysis_v2.retrieval import RetrievalRequest
from ai_do_api.domains.legacy_issues.models import LegacyIssueRecord
from ai_do_api.domains.retrieval.partitioning import (
    RetrievalPartitionId,
    RetrievalReadScope,
    RetrievalSourcePartitions,
)


class _Rows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows) -> None:
        self.rows = rows

    def execute(self, _statement):
        return _Rows(self.rows)


class _Acl:
    def __init__(self, allowed_ids: set[str]) -> None:
        self.allowed_ids = allowed_ids

    def authorize_many_resources(self, resources):
        return {
            (resource_type, resource_id)
            for resource_type, resource_id in resources
            if resource_id in self.allowed_ids
        }


def _read_scope() -> RetrievalReadScope:
    return RetrievalReadScope(
        sources=(
            RetrievalSourcePartitions(
                source_namespace="legacy_issues",
                partition_ids=(RetrievalPartitionId("partition-1"),),
            ),
        )
    )


def _profile() -> LegacyIssueSearchProfile:
    return LegacyIssueSearchProfile(
        semantic_enabled=True,
        vector_extension_available=True,
        vector_index_available=True,
        trigram_extension_available=True,
        full_text_enabled=True,
        searched_dataset_keys=("aircon",),
        searched_revision_ids=("revision-1",),
        candidate_count=1,
        evidence_count=1,
        methods=("exact",),
    )


def _evidence(record_id: str = "record-1") -> LegacyIssueEvidence:
    return LegacyIssueEvidence(
        evidence_id="E1",
        dataset_key="aircon",
        dataset_title="공조",
        revision_id="revision-1",
        revision_no=1,
        record_id=record_id,
        stable_record_id="stable-1",
        label="과거 인덱스 제목",
        values={"symptom": "과거 인덱스 본문"},
        matched_fields=("symptom",),
        matched_chunks=(),
        score=0.91,
        methods=("exact", "semantic"),
    )


def _record(
    *,
    record_id: str = "record-1",
    workspace_id: str = "workspace-1",
    module_key: str = "aircon",
    revision_id: str = "revision-1",
    partition_id: str | None = "partition-1",
) -> LegacyIssueRecord:
    return LegacyIssueRecord(
        id=record_id,
        workspace_id=workspace_id,
        dataset_key=module_key,
        module_key=module_key,
        revision_id=revision_id,
        retrieval_partition_id=partition_id,
        search_text="현재 DB의 증발기 결빙 대책",
        stable_record_id="stable-1",
        vehicle_model="SW PSV2",
    )


def test_native_evidence_rehydrates_current_record_and_revision_status() -> None:
    captured = {}

    def search_fn(
        _db,
        *,
        workspace,
        plan,
        limit,
        module_keys,
        candidate_record_authorizer,
    ):
        captured.update(
            {
                "workspace": workspace.id,
                "query": plan.query,
                "limit": limit,
                "module_keys": module_keys,
                "authorized_ids": candidate_record_authorizer(
                    ("record-1", "record-denied")
                ),
            }
        )
        return [_evidence()], _profile()

    retriever = NativeLegacyIssueEvidenceRetriever(
        db=_Db([(_record(), "draft", 7)]),  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),  # type: ignore[arg-type]
        acl_policy=_Acl({"record-1"}),  # type: ignore[arg-type]
        sql_scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("aircon",),
            revision_ids=("revision-1",),
        ),
        read_scope=_read_scope(),
        search_fn=search_fn,
    )

    hits = retriever.retrieve(
        RetrievalRequest(query="에바(증발기)가 얼어서 문제된 이력이 있어?", limit=2)
    )

    assert captured == {
        "workspace": "workspace-1",
        "query": "에바(증발기)가 얼어서 문제된 이력이 있어?",
        "limit": 20,
        "module_keys": frozenset({"aircon"}),
        "authorized_ids": frozenset({"record-1"}),
    }
    assert len(hits) == 1
    assert hits[0].text == "현재 DB의 증발기 결빙 대책"
    assert "과거 인덱스 본문" not in hits[0].text
    assert hits[0].metadata["title"] != "과거 인덱스 제목"
    assert hits[0].metadata["revision_status"] == "draft"
    assert hits[0].metadata["revision_no"] == 7


def test_native_evidence_drops_acl_and_server_scope_mismatches() -> None:
    evidence = [_evidence("record-1"), _evidence("record-2")]

    def search_fn(*_args, **_kwargs):
        return evidence, _profile()

    retriever = NativeLegacyIssueEvidenceRetriever(
        db=_Db(
            [
                (_record(record_id="record-1"), "published", 1),
                (
                    _record(
                        record_id="record-2",
                        module_key="unauthorized-module",
                    ),
                    "published",
                    1,
                ),
            ]
        ),  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),  # type: ignore[arg-type]
        acl_policy=_Acl({"record-1", "record-2"}),  # type: ignore[arg-type]
        sql_scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("aircon",),
            revision_ids=("revision-1",),
        ),
        read_scope=_read_scope(),
        search_fn=search_fn,
    )

    hits = retriever.retrieve(RetrievalRequest(query="결빙", limit=10))

    assert [hit.resource_id for hit in hits] == ["record-1"]


def test_native_evidence_preserves_legacy_null_partition_after_acl() -> None:
    def search_fn(*_args, **_kwargs):
        return [_evidence()], _profile()

    retriever = NativeLegacyIssueEvidenceRetriever(
        db=_Db([(_record(partition_id=None), "published", 1)]),  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),  # type: ignore[arg-type]
        acl_policy=_Acl({"record-1"}),  # type: ignore[arg-type]
        sql_scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("aircon",),
            revision_ids=("revision-1",),
        ),
        read_scope=_read_scope(),
        search_fn=search_fn,
    )

    hits = retriever.retrieve(RetrievalRequest(query="결빙", limit=1))

    assert hits[0].partition_id is None


def test_native_evidence_never_falls_back_to_stale_projection_text() -> None:
    def search_fn(*_args, **_kwargs):
        return [_evidence()], _profile()

    record = _record()
    record.search_text = ""
    record.symptom = "현재 증상"
    record.cause = "현재 원인"
    record.countermeasure = "현재 대책"
    record.field_values = {"note": "현재 메모"}
    retriever = NativeLegacyIssueEvidenceRetriever(
        db=_Db([(record, "published", 1)]),  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),  # type: ignore[arg-type]
        acl_policy=_Acl({"record-1"}),  # type: ignore[arg-type]
        sql_scope=AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("aircon",),
            revision_ids=("revision-1",),
        ),
        read_scope=_read_scope(),
        search_fn=search_fn,
    )

    hits = retriever.retrieve(RetrievalRequest(query="결빙", limit=1))

    assert "현재 증상" in hits[0].text
    assert "현재 메모" in hits[0].text
    assert "과거 인덱스 본문" not in hits[0].text
