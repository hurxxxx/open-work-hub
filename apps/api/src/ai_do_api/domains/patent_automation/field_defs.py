"""Field registry for the 특허현황관리 patent-status workbook.

The workbook is a fixed, known layout: a 3-row merged header band (row 2 =
group, row 3 = sub-group/blank, row 4 = label) with data from row 5, ~96
columns B..CR per year-sheet. We map by **column letter / position** for the
canonical import (robust against the merged-header quirk where
``combine_header_rows`` would only read 2 of the 3 header rows), and keep a
fuzzy label lookup for re-imports / variant files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from openpyxl.utils import column_index_from_string


@dataclass(frozen=True)
class PatentFieldDefinition:
    key: str
    label_ko: str
    group_ko: str
    column_letter: str
    type: str  # text | date | int | money | enum
    aliases: tuple[str, ...] = field(default=())
    is_promoted: bool = False


# Promoted keys are mirrored onto indexed PatentRecord columns.
PROMOTED_KEYS: frozenset[str] = frozenset(
    {
        "application_no",
        "registration_no",
        "invention_title",
        "inventors",
        "application_year",
        "application_date",
        "patent_status",
    }
)


def _d(key, label, group, col, typ) -> PatentFieldDefinition:
    return PatentFieldDefinition(
        key=key,
        label_ko=label,
        group_ko=group,
        column_letter=col,
        type=typ,
        is_promoted=key in PROMOTED_KEYS,
    )


PATENT_FIELD_DEFINITIONS: tuple[PatentFieldDefinition, ...] = (
    _d("no", "NO.", "NO.", "B", "int"),
    _d("submitter_name", "제출 실명", "제출정보", "C", "text"),
    _d("submit_team", "제출 팀명", "출원전현황", "D", "text"),
    _d("submit_date", "제출일자", "출원전현황", "E", "date"),
    _d("submit_metric", "제출실적", "출원전현황", "F", "int"),
    _d("dispatch_date", "발송일자", "출원전현황", "G", "date"),
    _d("invention_review_log", "발명기술서검토현황", "출원전현황", "H", "text"),
    _d("patent_review_target", "특허심의대상", "출원전현황", "I", "enum"),
    _d("patent_review_date", "특허심의일", "출원전현황", "J", "date"),
    _d("review_result", "심의결과", "출원전현황", "K", "enum"),
    _d("draft_request_date", "초안요청일자", "출원전현황", "L", "date"),
    _d("draft_spec_log", "초안명세서진행현황", "출원전현황", "M", "text"),
    _d("draft_in_progress", "초안진행중", "출원전현황", "N", "text"),
    _d("patent_office_mgmt_no", "특허사무소관리번호", "출원전현황", "O", "text"),
    _d("patent_office", "담당특허사무소", "출원전현황", "P", "text"),
    _d("joint_application_flag", "공동출원건", "출원전현황", "Q", "enum"),
    _d("joint_application", "공동출원", "출원전현황", "R", "text"),
    _d("priority_orig_app_no", "원출원번호", "우선권주장출원", "S", "text"),
    _d("priority_orig_app_date", "원출원일", "우선권주장출원", "T", "date"),
    _d("divisional_orig_app_no", "원출원번호", "분할/변경출원", "U", "text"),
    _d("divisional_orig_app_date", "원출원일", "분할/변경출원", "V", "date"),
    _d("application_no", "출원번호", "출원현황", "W", "text"),
    _d("application_date", "출원일자", "출원현황", "X", "date"),
    _d("application_year", "출원년도", "출원현황", "Y", "int"),
    _d("application_metric", "출원실적", "출원현황", "Z", "int"),
    _d("application_confirm", "출원확인", "출원현황", "AA", "enum"),
    _d("later_amendment", "추후보정사항", "출원현황", "AB", "text"),
    _d("foreign_app_target", "해외출원대상", "출원현황", "AC", "enum"),
    _d("foreign_app_confirm", "해외출원확인", "출원현황", "AD", "enum"),
    _d("priority_request", "우선권요청", "출원현황", "AE", "text"),
    _d("designated_countries", "출원지정국", "출원현황", "AF", "text"),
    _d("priority_date", "우선권일자", "출원현황", "AG", "date"),
    _d("foreign_app_log", "해외출원진행현황", "출원현황", "AH", "text"),
    _d("invention_title", "발명의명칭", "특허내용", "AI", "text"),
    _d("inventors", "발명자", "특허내용", "AJ", "text"),
    _d("abstract", "요약", "특허내용", "AK", "text"),
    _d("representative_claim", "대표청구항", "특허내용", "AL", "text"),
    _d("count", "COUNT", "COUNT", "AM", "int"),
    _d("tech_class_1", "기술분류(1)", "기술분류", "AN", "text"),
    _d("tech_class_2", "기술분류(2)", "기술분류", "AO", "text"),
    _d("tech_class_3", "기술분류(3)", "기술분류", "AP", "text"),
    _d("tech_class_4", "기술분류(4)", "기술분류", "AQ", "text"),
    _d("patent_category", "특허구분", "특허구분", "AR", "enum"),
    _d("patent_status", "특허상태", "특허상태", "AS", "enum"),
    _d("exam_claim_count", "심사청구항수", "심사현황", "AT", "int"),
    _d("exam_claim_cost", "심사청구비용", "심사현황", "AU", "money"),
    _d("exam_request_deadline_ym", "심사청구마감년월", "심사현황", "AV", "int"),
    _d("exam_request_target", "심사청구대상", "심사현황", "AW", "enum"),
    _d("exam_request_deadline_year", "심사청구마감년도", "심사현황", "AX", "int"),
    _d("oem_deadline_year", "OEM마감년도", "심사현황", "AY", "int"),
    _d("exam_request_log", "심사청구진행현황", "심사현황", "AZ", "text"),
    _d("exam_request_date", "심사청구일", "심사현황", "BA", "date"),
    _d("exam_progress_log", "심사진행현황", "심사현황", "BB", "text"),
    _d("exam_in_progress", "심사진행중", "심사현황", "BC", "enum"),
    _d("registration_no", "등록번호", "등록현황", "BD", "text"),
    _d("registration_date", "등록일", "등록현황", "BE", "date"),
    _d("registration_year", "등록년도", "등록현황", "BF", "int"),
    _d("registration_metric", "등록실적", "등록현황", "BG", "int"),
    _d("registration_confirm", "등록확인", "등록현황", "BH", "enum"),
    _d("registration_maintained", "등록유지", "특허유지관리현황", "BI", "enum"),
    _d("extinction_date", "소멸일자", "특허유지관리현황", "BJ", "date"),
    _d("extinction_reason", "소멸사유", "특허유지관리현황", "BK", "text"),
    _d("expiry_due_date", "만료예정일", "특허유지관리현황", "BL", "date"),
    _d("annuity_deadline_month", "마감월", "특허유지관리현황", "BM", "int"),
    _d("annuity_deadline_date", "마감일", "특허유지관리현황", "BN", "date"),
    _d("annuity_year", "연차", "특허유지관리현황", "BO", "int"),
    _d("annuity_payment_date", "납부일", "특허유지관리현황", "BP", "date"),
    _d("claim_count", "청구항수", "특허유지관리현황", "BQ", "int"),
    _d("kipo_fee", "특허청수수료", "특허유지관리현황", "BR", "money"),
    _d("agent_fee_with_vat", "한양 수수료 및 부가세", "특허유지관리현황", "BS", "money"),
    _d("fee_total", "합계", "특허유지관리현황", "BT", "money"),
    _d("annuity_manager", "연차료관리처", "특허유지관리현황", "BU", "text"),
    _d("eval_mass_production_applied", "양산적용", "발명자평가/양산성", "BV", "enum"),
    _d("eval_application_planned", "적용예정", "발명자평가/양산성", "BW", "enum"),
    _d("eval_design_concept", "설계구상", "발명자평가/양산성", "BX", "enum"),
    _d("eval_mass_production_models", "양산차종", "발명자평가/적용차종", "BY", "text"),
    _d("eval_development_models", "개발차종", "발명자평가/적용차종", "BZ", "text"),
    _d("eval_next_gen_tech", "차세대기술", "발명자평가/기술정도", "CA", "enum"),
    _d("eval_improvement_tech", "개량기술", "발명자평가/기술정도", "CB", "enum"),
    _d("eval_idea", "아이디어", "발명자평가/기술정도", "CC", "enum"),
    _d("reference_materials", "참조자료(논문,특허)", "발명자평가", "CD", "text"),
    _d("kipo_prior_art_docs", "특허청 선행기술조사문헌", "특허청 선행기술조사문헌", "CE", "text"),
    _d("leader_grade_s", "S등급", "팀장평가/출원등급", "CF", "enum"),
    _d("leader_grade_a", "A등급", "팀장평가/출원등급", "CG", "enum"),
    _d("leader_grade_b", "B등급", "팀장평가/출원등급", "CH", "enum"),
    _d("leader_tech_level_high", "상", "팀장평가/기술수준", "CI", "enum"),
    _d("leader_tech_level_mid", "중", "팀장평가/기술수준", "CJ", "enum"),
    _d("leader_tech_level_low", "하", "팀장평가/기술수준", "CK", "enum"),
    _d("deliberation_current_mass_production", "현양산적용", "특허심의현황", "CL", "enum"),
    _d("deliberation_mass_production_planned", "양산적용예정", "특허심의현황", "CM", "enum"),
    _d("deliberation_tech_right_preemption", "기술권리선점", "특허심의현황", "CN", "enum"),
    _d("deliberation_defensive_right", "방어권리획득", "특허심의현황", "CO", "text"),
    _d("deliberation_result", "심의결과", "특허심의결과", "CP", "text"),
    _d("deliberation_applied_models", "적용차종", "특허심의결과", "CQ", "text"),
    _d("deliberation_extinction_target", "소멸대상", "특허심의결과", "CR", "enum"),
)


PATENT_FIELD_LOOKUP: dict[str, PatentFieldDefinition] = {d.key: d for d in PATENT_FIELD_DEFINITIONS}
FIELD_BY_COLUMN: dict[str, PatentFieldDefinition] = {
    d.column_letter: d for d in PATENT_FIELD_DEFINITIONS
}


# ── 해외출원 시트 (별도 스키마) ─────────────────────────────────────────────────
# The 해외출원 sheet uses a different layout: a title/notes band (rows 1–11), a
# group-band on row 13, the actual column labels on row 14, and data from row 15.
# ~80 labelled columns B..CI. Promoted keys reuse the SAME names as the year
# sheets (application_no/registration_no/invention_title/inventors/
# application_year/application_date/patent_status) so PatentRecord's promoted
# columns and _apply_promoted work unchanged. source_sheet is set to 'overseas'.
OVERSEAS_HEADER_ROW = 14
OVERSEAS_DATA_START_ROW = 15
OVERSEAS_SOURCE_SHEET = "overseas"

OVERSEAS_FIELD_DEFINITIONS: tuple[PatentFieldDefinition, ...] = (
    _d("no", "NO.", "NO.", "B", "int"),
    _d("submit_team", "제출 팀-부서", "출원전현황", "C", "text"),
    _d("overseas_decision_date", "해외출원결정일", "출원전현황", "D", "date"),
    _d("patent_office", "담당특허사무소", "출원전현황", "E", "text"),
    _d("overseas_draft_request_date", "해외초안요청일", "출원전현황", "F", "date"),
    _d("domestic_priority_patent", "국내우선권 특허", "출원전현황", "G", "text"),
    _d("application_progress_log", "출원진행현황", "출원전현황", "H", "text"),
    _d("patent_office_mgmt_no", "특허사무소관리번호", "출원전현황", "I", "text"),
    _d("joint_application", "공동출원", "DA/CA/CIP", "J", "text"),
    _d("joint_application_confirm", "공동출원확정", "DA/CA/CIP", "K", "enum"),
    _d("orig_application", "원출원", "DA/CA/CIP", "L", "text"),
    _d("application_type", "출원유형", "출원현황", "M", "text"),
    _d("application_no", "출원번호", "출원현황", "N", "text"),
    _d("application_date", "출원일자", "출원현황", "O", "date"),
    _d("application_year", "출원년도", "출원현황", "P", "int"),
    _d("application_confirm", "출원확정", "출원현황", "Q", "enum"),
    _d("priority_date", "우선권일자", "출원현황", "R", "date"),
    _d("application_country", "출원국가", "출원현황", "S", "text"),
    _d("designated_country", "지정국", "출원현황", "T", "text"),
    _d("publication_no", "공개번호", "공개현황", "U", "text"),
    _d("publication_date", "공개일자", "공개현황", "V", "date"),
    _d("invention_title", "발명의명칭", "특허내용", "W", "text"),
    _d("inventors", "발명자", "특허내용", "X", "text"),
    _d("abstract", "요약", "특허내용", "Y", "text"),
    _d("representative_claim", "대표청구항", "특허내용", "Z", "text"),
    _d("count", "COUNT", "COUNT", "AA", "int"),
    _d("tech_class_1", "기술분류(1)", "기술분류", "AB", "text"),
    _d("tech_class_2", "기술분류(2)", "기술분류", "AC", "text"),
    _d("tech_class_3", "기술분류(3)", "기술분류", "AD", "text"),
    _d("tech_class_4", "기술분류(4)", "기술분류", "AE", "text"),
    _d("patent_category", "특허구분", "특허구분", "AF", "text"),
    _d("patent_status", "특허상태", "특허상태", "AG", "text"),
    _d("overseas_cost", "해외비용/관납료", "출원비용", "AH", "money"),
    _d("domestic_fee", "국내비용/수수료", "출원비용", "AI", "money"),
    _d("application_total", "출원총합계", "출원비용", "AJ", "money"),
    _d("post_application_log", "출원후진행현황", "출원유지관리현황", "AK", "text"),
    _d("maintenance_annuity_year", "출원유지연차", "출원유지관리현황", "AL", "int"),
    _d("maintenance_deadline_date", "출원유지마감일", "출원유지관리현황", "AM", "date"),
    _d("maintenance_payment_date", "출원유지납부일", "출원유지관리현황", "AN", "date"),
    _d("maintenance_fee", "출원유지료", "출원유지관리현황", "AO", "money"),
    _d("maintenance_fee_vat", "출원유지 수수료/부가세", "출원유지관리현황", "AP", "money"),
    _d("maintenance_fee_total", "출원유지료합계", "출원유지관리현황", "AQ", "money"),
    _d("exam_request_status", "심사청구현황", "심사현황", "AR", "text"),
    _d("exam_request_target", "심사청구대상", "심사현황", "AS", "enum"),
    _d("exam_request_deadline_year", "심사청구마감년도", "심사현황", "AT", "int"),
    _d("exam_request_deadline_ym", "심사청구마감년월", "심사현황", "AU", "text"),
    _d("exam_request_log", "심사청구진행현황", "심사현황", "AV", "text"),
    _d("exam_request_date", "심사청구일", "심사현황", "AW", "date"),
    _d("exam_progress_log", "심사진행현황", "심사현황", "AX", "text"),
    _d("exam_in_progress", "심사진행중", "심사현황", "AY", "text"),
    _d("prior_art_docs", "선행기술조사문헌", "심사현황", "AZ", "text"),
    _d("cited_inventions", "인용발명", "심사현황", "BA", "text"),
    _d("registration_progress_log", "등록진행현황", "등록현황", "BB", "text"),
    _d("registration_no", "등록번호", "등록현황", "BC", "text"),
    _d("registration_date", "등록일", "등록현황", "BD", "date"),
    _d("registration_year", "등록년도", "등록현황", "BE", "int"),
    _d("registration_confirm", "등록확정", "등록현황", "BF", "enum"),
    _d("registration_maintained", "등록유지", "등록현황", "BG", "enum"),
    _d("extinction_date", "소멸일자", "등록현황", "BH", "date"),
    _d("extinction_reason", "소멸사유", "등록현황", "BI", "text"),
    _d("expiry_due_date", "만료예정일", "등록현황", "BJ", "date"),
    _d("registration_cost", "등록비용", "등록비용현황", "BK", "money"),
    _d("registration_cost_vat", "등록 수수료/부가세", "등록비용현황", "BL", "money"),
    _d("registration_cost_total", "등록비합계", "등록비용현황", "BM", "money"),
    _d("registration_designated_country", "등록지정국", "등록비용현황", "BN", "text"),
    _d("designated_country_reg_cost", "지정국등록비용", "등록비용현황", "BO", "money"),
    _d("designated_country_reg_vat", "지정국등록 수수료/부가세", "등록비용현황", "BP", "money"),
    _d("designated_country_reg_total", "지정국등록비 합계", "등록비용현황", "BQ", "money"),
    _d("annuity_progress_log", "등록연차료진행현황", "등록유지비용현황", "BR", "text"),
    _d("annuity_year", "연차", "등록유지비용현황", "BS", "int"),
    _d("annuity_deadline_month", "마감월", "등록유지비용현황", "BT", "text"),
    _d("annuity_deadline_date", "연차료마감일", "등록유지비용현황", "BU", "date"),
    _d("annuity_payment_date", "납부일", "등록유지비용현황", "BV", "date"),
    _d("annuity_fee", "연차료", "등록유지비용현황", "BW", "money"),
    _d("annuity_fee_vat", "연차료 수수료 및 부가세", "등록유지비용현황", "BX", "money"),
    _d("annuity_total", "연차료 합계", "등록유지비용현황", "BY", "money"),
    _d("annuity_manager", "연차료관리처", "등록유지비용현황", "BZ", "text"),
    _d("eval_current_mass_production", "현양산적용", "특허분석현황", "CA", "enum"),
    _d("eval_mass_production_planned", "양산적용예정", "특허분석현황", "CB", "enum"),
    _d("eval_tech_right_preemption", "기술권리선점", "특허분석현황", "CC", "enum"),
    _d("eval_defensive_right", "방어권리획득", "특허분석현황", "CD", "text"),
    _d("eval_applied_models", "적용차종", "특허평가", "CE", "text"),
    _d("deliberation_result", "심의결과", "특허평가", "CF", "text"),
    _d("extinction_target", "소멸대상", "특허평가", "CG", "enum"),
    _d("domestic_priority_patent_detail", "국내우선권 특허(상세)", "국내우선권 특허", "CH", "text"),
    _d("patent_reward", "특허 보상", "특허 보상", "CI", "text"),
)

OVERSEAS_FIELD_LOOKUP: dict[str, PatentFieldDefinition] = {
    d.key: d for d in OVERSEAS_FIELD_DEFINITIONS
}


def overseas_field_keys() -> list[str]:
    return [d.key for d in OVERSEAS_FIELD_DEFINITIONS]


def overseas_field_labels() -> dict[str, str]:
    return {d.key: d.label_ko for d in OVERSEAS_FIELD_DEFINITIONS}


def overseas_column_position_mapping() -> dict[str, int]:
    """overseas field key -> 0-based column index (row-14 label positions)."""
    return {
        d.key: column_index_from_string(d.column_letter) - 1 for d in OVERSEAS_FIELD_DEFINITIONS
    }


# Accumulated "날짜 단계-->" progress columns → progress-event kind.
PROGRESS_LOG_FIELDS: dict[str, str] = {
    "invention_review_log": "발명기술서검토현황",
    "draft_spec_log": "초안명세서진행현황",
    "exam_request_log": "심사청구진행현황",
    "exam_progress_log": "심사진행현황",
}

DISCLOSURE_STAGE = "직무발명기술서 접수"


def field_keys() -> list[str]:
    return [d.key for d in PATENT_FIELD_DEFINITIONS]


def promoted_field_keys() -> list[str]:
    return [d.key for d in PATENT_FIELD_DEFINITIONS if d.is_promoted]


def field_labels() -> dict[str, str]:
    return {d.key: d.label_ko for d in PATENT_FIELD_DEFINITIONS}


def normalize_header(value: str) -> str:
    return " ".join(str(value).replace("﻿", "").replace("\n", " ").strip().lower().split())


def build_field_lookup() -> dict[str, str]:
    """Map normalized header text -> field key.

    Keys: the field key itself, the bare label (only when unique across the
    registry), and the ``"group - label"`` combination that matches
    ``combine_header_rows`` output.
    """
    label_counts: dict[str, int] = {}
    for d in PATENT_FIELD_DEFINITIONS:
        label_counts[normalize_header(d.label_ko)] = (
            label_counts.get(normalize_header(d.label_ko), 0) + 1
        )

    lookup: dict[str, str] = {}
    for d in PATENT_FIELD_DEFINITIONS:
        lookup[normalize_header(d.key)] = d.key
        lookup[normalize_header(f"{d.group_ko} - {d.label_ko}")] = d.key
        bare = normalize_header(d.label_ko)
        if label_counts[bare] == 1:
            lookup.setdefault(bare, d.key)
    return lookup


def suggested_mapping(headers: list[str]) -> dict[str, int]:
    """2-pass (exact then substring) header → column-index suggestion."""
    lookup = build_field_lookup()
    mapping: dict[str, int] = {}
    for index, header in enumerate(headers):
        norm = normalize_header(header)
        key = lookup.get(norm)
        if key and key not in mapping:
            mapping[key] = index
    for index, header in enumerate(headers):
        norm = normalize_header(header)
        if not norm:
            continue
        for lookup_key, field_key in lookup.items():
            if field_key in mapping:
                continue
            if lookup_key and (lookup_key in norm or norm in lookup_key):
                mapping[field_key] = index
                break
    return mapping


def column_position_mapping() -> dict[str, int]:
    """field key -> 0-based column index, for canonical position-based import."""
    return {d.key: column_index_from_string(d.column_letter) - 1 for d in PATENT_FIELD_DEFINITIONS}


_PROGRESS_STEP_RE = re.compile(r"^\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*(.+?)\s*$")


def parse_progress_log(text: str | None) -> list[tuple[str | None, str]]:
    """Split an accumulated ``YYYY.MM.DD 단계-->...`` log into (date, stage)."""
    if not text:
        return []
    steps: list[tuple[str | None, str]] = []
    for chunk in str(text).split("-->"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _PROGRESS_STEP_RE.match(chunk)
        if match:
            y, m, d, stage = match.groups()
            steps.append((f"{int(y):04d}-{int(m):02d}-{int(d):02d}", stage.strip()))
        else:
            steps.append((None, chunk))
    return steps


def extract_disclosure_date(review_log: str | None) -> str | None:
    """Date of the first ``직무발명기술서 접수`` step (drives year-sheet placement)."""
    for date_str, stage in parse_progress_log(review_log):
        if DISCLOSURE_STAGE in stage:
            return date_str
    # Fallback: first dated step.
    for date_str, _stage in parse_progress_log(review_log):
        if date_str:
            return date_str
    return None


_EXCEL_EPOCH = datetime(1899, 12, 30)
_DATE_RE = re.compile(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def parse_mixed_date(value: object) -> str | None:
    """Accept ``YYYY.MM.DD`` strings, datetimes, and Excel serials → ISO date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Heuristic: Excel date serials are < ~100000; larger numbers like
        # 202604 are year-month codes, not serials.
        if 1 <= float(value) < 100000:
            return (_EXCEL_EPOCH + timedelta(days=float(value))).strftime("%Y-%m-%d")
        return None
    match = _DATE_RE.match(str(value).strip())
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None


def year_from_iso(iso_date: str | None) -> int | None:
    if iso_date and len(iso_date) >= 4 and iso_date[:4].isdigit():
        return int(iso_date[:4])
    return None


def normalize_app_no(value: object) -> str | None:
    """Digits-only form of a domestic 출원/등록번호 for matching.

    Korean numbers like ``10-2025-0203274`` → ``1020250203274``. Overseas/raw
    numbers (US ``19/394,605``, CN ``ZL...``) are stripped of separators too,
    so the same helper yields a comparable token; callers should treat overseas
    matching as best-effort.
    """
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None
