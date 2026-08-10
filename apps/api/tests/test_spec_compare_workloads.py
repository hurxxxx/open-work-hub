from __future__ import annotations

from types import SimpleNamespace

from ai_do_api.domains.ai.registry import AiCapabilityRegistry
from ai_do_api.domains.document_processing import DocumentExtractBundle, EvidenceBlock
from ai_do_api.domains.spec_compare import (
    SPEC_COMPARE_APP_ID,
    SPEC_COMPARE_COMPARE_TASK_KIND,
    SPEC_COMPARE_COMPARE_WORKLOAD_ID,
    SPEC_COMPARE_EXTRACT_TASK_KIND,
    SPEC_COMPARE_EXTRACT_WORKLOAD_ID,
    SPEC_COMPARE_REPORT_TASK_KIND,
    SPEC_COMPARE_REPORT_WORKLOAD_ID,
    register_ai_capabilities,
)
from ai_do_api.domains.spec_compare import pipeline, reporting
from ai_do_api.domains.spec_compare.contracts import ComparisonRow
from ai_do_api.domains.spec_compare.extraction import DocumentMarkdownChunk, SpecCandidate


def test_registers_independent_spec_compare_workloads() -> None:
    registry = AiCapabilityRegistry()

    register_ai_capabilities(registry)

    expected = {
        SPEC_COMPARE_EXTRACT_WORKLOAD_ID: SPEC_COMPARE_EXTRACT_TASK_KIND,
        SPEC_COMPARE_COMPARE_WORKLOAD_ID: SPEC_COMPARE_COMPARE_TASK_KIND,
        SPEC_COMPARE_REPORT_WORKLOAD_ID: SPEC_COMPARE_REPORT_TASK_KIND,
    }
    assert set(registry.llm_workloads) == set(expected)
    for workload_id, task_kind in expected.items():
        workload = registry.llm_workloads[workload_id]
        assert workload.task_kind == task_kind
        assert workload.app_ids == (SPEC_COMPARE_APP_ID,)
        assert workload.default_route == "local"
        assert workload.allowed_routes == ("local", "external")
        assert workload.allowed_providers == ()
        assert workload.external_data is True


def test_spec_compare_stages_execute_their_own_workloads(monkeypatch) -> None:
    captured: list[tuple[str, object]] = []

    def fake_pipeline_execute(workload_id, context, _db, **_kwargs):
        captured.append((workload_id, context))
        if workload_id == SPEC_COMPARE_EXTRACT_WORKLOAD_ID:
            text = (
                '{"items":[{"item_name":"정격 출력","value":"10 kW",'
                '"evidence_id":"base:block:1","source_text":"정격 출력: 10 kW"}]}'
            )
        else:
            text = (
                '{"rows":[{"spec_name":"정격 출력","base_value":"10 kW",'
                '"target_value":"12 kW","status":"different",'
                '"base_evidence_ids":["base:block:1"],'
                '"target_evidence_ids":["target:block:1"]}]}'
            )
        return SimpleNamespace(completion=SimpleNamespace(text=text))

    def fake_reporting_execute(workload_id, context, _db, **_kwargs):
        captured.append((workload_id, context))
        return SimpleNamespace(
            completion=SimpleNamespace(text="## AI 분석 요약\n\n정격 출력이 다릅니다.")
        )

    monkeypatch.setattr(pipeline, "execute_llm", fake_pipeline_execute)
    monkeypatch.setattr(reporting, "execute_llm", fake_reporting_execute)

    bundle = DocumentExtractBundle(
        document_id="base",
        filename="base.pdf",
        mime_type="application/pdf",
        evidence_blocks=[
            EvidenceBlock(
                document_id="base",
                block_id="base:block:1",
                locator_kind="page",
                locator_label="1페이지",
                section_path="성능",
                block_kind="paragraph",
                text="정격 출력: 10 kW",
            )
        ],
    )
    chunk = DocumentMarkdownChunk(
        chunk_id="base:chunk:1",
        document_id="base",
        section_path="성능",
        locator_label="1페이지",
        evidence_ids=["base:block:1"],
        markdown="정격 출력: 10 kW",
    )
    extracted = pipeline._extract_spec_items_with_llm(
        object(),
        workspace_id="workspace-1",
        actor_user_id="user-1",
        bundle=bundle,
        chunks=[chunk],
    )
    assert [item.item_name for item in extracted] == ["정격 출력"]

    base = SpecCandidate(
        candidate_id="base:1",
        document_id="base",
        spec_name="정격 출력",
        value="10 kW",
        evidence_id="base:block:1",
        locator_label="1페이지",
        section_path="성능",
    )
    target = SpecCandidate(
        candidate_id="target:1",
        document_id="target",
        spec_name="정격 출력",
        value="12 kW",
        evidence_id="target:block:1",
        locator_label="1페이지",
        section_path="성능",
    )
    compared = pipeline._compare_section_with_llm(
        object(), "workspace-1", "user-1", [base], [target]
    )
    assert [row.status for row in compared] == ["different"]

    report = reporting._render_report_analysis_with_llm(
        object(),
        workspace_id="workspace-1",
        actor_user_id="user-1",
        rows=[
            ComparisonRow(
                spec_name="정격 출력",
                base_value="10 kW",
                target_value="12 kW",
                status="different",
                summary="",
                base_evidence_ids=["base:block:1"],
                target_evidence_ids=["target:block:1"],
            )
        ],
        summary={"different": 1},
    )
    assert report.startswith("## AI 분석 요약")

    assert [workload_id for workload_id, _context in captured] == [
        SPEC_COMPARE_EXTRACT_WORKLOAD_ID,
        SPEC_COMPARE_COMPARE_WORKLOAD_ID,
        SPEC_COMPARE_REPORT_WORKLOAD_ID,
    ]
    assert all(context.app_id == SPEC_COMPARE_APP_ID for _workload_id, context in captured)
