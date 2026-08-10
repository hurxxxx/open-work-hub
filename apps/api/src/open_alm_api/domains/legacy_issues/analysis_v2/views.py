from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


ANALYSIS_VIEW_SCHEMA: Final = "legacy_issue_analysis"
ISSUE_RECORDS_VIEW_V1: Final = f"{ANALYSIS_VIEW_SCHEMA}.issue_records_v1"
CHECKLISTS_VIEW_V1: Final = f"{ANALYSIS_VIEW_SCHEMA}.vehicle_checklists_v1"
CHECKLIST_ITEMS_VIEW_V1: Final = f"{ANALYSIS_VIEW_SCHEMA}.vehicle_checklist_items_v1"


@dataclass(frozen=True, slots=True)
class AnalysisViewContract:
    """Public SQL surface exposed by a security-barrier analysis view.

    Workspace, retrieval-partition, revision-selection, and source ACL fields are
    deliberately absent. The database migration that creates these views must
    resolve those values server-side before a row reaches this interface.
    """

    name: str
    description: str
    identity_column: str
    columns: frozenset[str]


_ISSUE_COLUMNS = frozenset(
    {
        "issue_id",
        "stable_issue_id",
        "dataset_key",
        "module_key",
        "revision_no",
        "legacy_issue_number",
        "department",
        "major_category",
        "middle_category",
        "region_zone",
        "occurrence_stage",
        "occurrence_type",
        "oem_disclosure_status",
        "vehicle_model",
        "occurrence_date",
        "received_date",
        "issue_type",
        "cause_type",
        "supplier",
        "part_number",
        "process_name",
        "symptom",
        "cause",
        "countermeasure",
        "countermeasure_type",
        "action",
        "severity_grade",
        "confirmation_content",
        "check_plan",
        "applied",
        "reflection_result",
        "master_status",
        "search_text",
        "created_at",
        "updated_at",
    }
)

_CHECKLIST_COLUMNS = frozenset(
    {
        "checklist_id",
        "vehicle_model",
        "vehicle_code",
        "module_key",
        "checklist_status",
        "source_revision_no",
        "item_count",
        "completed_at",
        "created_at",
        "updated_at",
    }
)

_CHECKLIST_ITEM_COLUMNS = frozenset(
    {
        "checklist_item_id",
        "checklist_id",
        "source_issue_id",
        "stable_issue_id",
        "vehicle_model",
        "vehicle_code",
        "module_key",
        "checklist_status",
        "source_revision_no",
        "legacy_issue_number",
        "major_category",
        "middle_category",
        "region_zone",
        "occurrence_stage",
        "occurrence_type",
        "occurrence_date",
        "issue_type",
        "cause_type",
        "supplier",
        "part_number",
        "process_name",
        "symptom",
        "cause",
        "countermeasure",
        "severity_grade",
        "applied",
        "reflection_result",
        "search_text",
        "created_at",
        "updated_at",
    }
)

ANALYSIS_VIEW_CONTRACTS: Mapping[str, AnalysisViewContract] = MappingProxyType(
    {
        ISSUE_RECORDS_VIEW_V1: AnalysisViewContract(
            name=ISSUE_RECORDS_VIEW_V1,
            description=(
                "현재 유효 revision과 최종 ACL이 적용된 과거차 문제점 1건당 1행"
            ),
            identity_column="issue_id",
            columns=_ISSUE_COLUMNS,
        ),
        CHECKLISTS_VIEW_V1: AnalysisViewContract(
            name=CHECKLISTS_VIEW_V1,
            description=(
                "현재 유효 차량·모듈 체크리스트 문서 1개당 1행; item_count와 문서 수를 구분"
            ),
            identity_column="checklist_id",
            columns=_CHECKLIST_COLUMNS,
        ),
        CHECKLIST_ITEMS_VIEW_V1: AnalysisViewContract(
            name=CHECKLIST_ITEMS_VIEW_V1,
            description=(
                "현재 유효 차량·모듈 체크리스트 항목 1개당 1행; 문서 수 집계에 사용하지 않음"
            ),
            identity_column="checklist_item_id",
            columns=_CHECKLIST_ITEM_COLUMNS,
        ),
    }
)


def analysis_view_metadata() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "view_name": contract.name,
            "description": contract.description,
            "identity_column": contract.identity_column,
            "columns": sorted(contract.columns),
        }
        for contract in ANALYSIS_VIEW_CONTRACTS.values()
    )


__all__ = [
    "ANALYSIS_VIEW_CONTRACTS",
    "ANALYSIS_VIEW_SCHEMA",
    "CHECKLIST_ITEMS_VIEW_V1",
    "CHECKLISTS_VIEW_V1",
    "ISSUE_RECORDS_VIEW_V1",
    "AnalysisViewContract",
    "analysis_view_metadata",
]
