"""Pure-function unit tests for the patent_automation domain.

DB-free: exercises field registry, invoice parsers (vendor detect, domestic /
overseas / markpro), numeric normalization, reconcile, and the three summary
xlsx builders. Mirrors behavior verified against the Jan–May reference files.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import openpyxl
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.patent_automation import field_defs as fd
from ai_do_api.domains.patent_automation import invoice_pipeline as ip
from ai_do_api.domains.patent_automation import service
from ai_do_api.domains.patent_automation.models import PatentCostLine, PatentCostRun
from ai_do_api.domains.patent_automation import summary_xlsx as sx
from ai_do_api.domains.patent_automation.disclosure_form import parse_disclosure_form


# ── field registry ──────────────────────────────────────────────────────────
def test_field_defs_registry() -> None:
    assert len(fd.PATENT_FIELD_DEFINITIONS) >= 90
    assert len(fd.OVERSEAS_FIELD_DEFINITIONS) == 86
    promoted = set(fd.promoted_field_keys())
    assert {"application_no", "registration_no", "invention_title", "inventors"} <= promoted
    # 승격 키는 국내/해외 동일 → 해외에도 동일 키 존재
    ov_keys = set(fd.overseas_field_keys())
    assert {"application_no", "invention_title", "patent_status"} <= ov_keys


def test_normalize_numeric_metric_and_money() -> None:
    # 실적/년월(YYYY.MM)은 6자리 YYYYMM로, 금액 노이즈는 반올림
    assert ip._to_int  # smoke
    assert fd  # smoke
    from ai_do_api.domains.patent_automation import service

    assert service._normalize_numeric("submit_metric", "2007.02") == "200702"
    assert service._normalize_numeric("application_metric", "200704") == "200704"
    assert service._normalize_numeric("kipo_fee", "254099.99999999997") == "254100"


# ── vendor detection ─────────────────────────────────────────────────────────
def test_detect_vendor() -> None:
    assert ip.detect_vendor("(주)마크프로\nDebit No. 126-0053") == "마크프로"
    assert ip.detect_vendor("특허법인 신세기 청구번호 POG26-005") == "신세기"
    assert ip.detect_vendor("유미특허법인 비용내역") == "유미"
    assert ip.detect_vendor("한라특허법인(유한)") == "한라"


def test_reconcile() -> None:
    assert ip.reconcile({"supply_amount": 100, "vat": 10, "line_total": 110})
    assert not ip.reconcile({"supply_amount": 100, "vat": 10, "line_total": 999})


# ── domestic 한라 page ────────────────────────────────────────────────────────
DOMESTIC_PAGE = (
    "비 용 청 구 서\n"
    "특허출원 제 10-2025-0203274 호\n"
    "명 칭 : 차량용 공조장치\n"
    "수수료 1300000 5 1300000\n"
    "수수료 부가세 130000\n"
    "관납료 46000 5 46000\n"
    "청 구 금 액 ③ ￦ 1,462,200\n"
)


def test_parse_domestic_page() -> None:
    line = ip.parse_domestic_page(DOMESTIC_PAGE, "국내출원")
    assert line is not None
    assert line["application_no"] == "10-2025-0203274"
    assert line["vat"] == 130000
    assert line["line_total"] == 1462200
    assert line["supply_amount"] == 1462200 - 130000
    assert ip.reconcile(line)


def test_parse_domestic_annuity_year() -> None:
    line = ip.parse_domestic_page(DOMESTIC_PAGE + "관납료 8 년차료\n", ip.SECTION_ANNUITY)
    assert line is not None
    assert line["annuity_year"] == "8"


def test_parse_domestic_annuity_year_ignores_calendar_year_in_title() -> None:
    line = ip.parse_domestic_page(
        "2026년 차량용 공조장치\n" + DOMESTIC_PAGE + "관납료 8 년차료\n",
        ip.SECTION_ANNUITY,
    )
    assert line is not None
    assert line["annuity_year"] == "8"


# ── overseas 신세기 ───────────────────────────────────────────────────────────
OVERSEAS_SINSEGI = (
    "사건의 명칭 미국특허출원 제19/394,605호 (차량용 듀얼 블로워 시스템)의 출원비용\n"
    "해외 비용 출 원 비 용 1,499,654원 USD 1,006.00\n"
    "소 계 1,499,654원\n"
    "착 수 금 102,730원\n"
    "당소 수수료 번 역 비 용 156,250원\n"
    "부 가 세 25,898원\n"
    "소 계 284,878원\n"
    "합 계 1,784,532원\n"
    "1USD=1,490.71원\n"
)


def test_parse_overseas_sinsegi() -> None:
    line = ip.parse_overseas_text(OVERSEAS_SINSEGI)
    assert line is not None
    assert line["application_no"] == "19/394,605"
    assert line["line_total"] == 1784532
    assert line["vat"] == 25898
    assert line["supply_amount"] == 1758634
    assert line["cost_details"]["대리인수수료"] == 258980  # 착수금 + 번역비
    assert line["cost_details"].get("균등분담업체수") is None  # 분담 근거 없는 단독 청구
    assert ip.reconcile(line)


# ── overseas 신세기 OA (당소 수수료가 "OA검토비용" — 착수금/번역비 라벨 아님) ──────
# 해외비용 소계(첫 '소 계 …원')로 원화비용을 직접 잡아야 당소수수료가 해외비용으로
# 오분류되지 않는다. 2차 OA는 해외비용 0원이고 전액이 국내 OA검토비용이다.
OVERSEAS_SINSEGI_OA = (
    "미국특허출원 제18/385,447호\n"
    "사건의 명칭\n"
    "(차량의 에어커튼 시스템)의 2차OA검토비용\n"
    "해외 비용 2차OA검토비용 0원 USD 0.00\n"
    "소 계 0원\n"
    "O A 검 토 비 용 25,330원\n"
    "당소 수수료\n"
    "부 가 세 2,533원\n"
    "소 계 27,863원\n"
    "합 계 27,863원\n"
)


def test_parse_overseas_sinsegi_oa() -> None:
    line = ip.parse_overseas_text(OVERSEAS_SINSEGI_OA)
    assert line is not None
    assert line["application_no"] == "18/385,447"
    assert line["line_total"] == 27863
    assert line["vat"] == 2533
    assert line["foreign_amount"] == 0.0  # 해외비용 0 → 외화 0
    assert line["foreign_cost_krw"] == 0  # 전액 국내 OA검토비용 (해외비용 오분류 금지)
    assert line["cost_details"]["대리인수수료"] == 25330
    assert ip.reconcile(line)


# ── overseas 유미 (금액-통화 순서 "(1115.00 EUR)" + "환율:1740" + 분담율) ─────────
# 청구서상 외화는 총액(1115.00 EUR)이나 HMC 분담분을 제외한 두원 몫만 청구되므로
# 표시 외화 = 원화비용 ÷ 환율 = 557.50 EUR 로 일관화한다.
OVERSEAS_YOUME = (
    "제 목: 독일 특허출원 102012113179.1\n"
    "차량용 응축기\n"
    "YOU ME 특허법인\n"
    "비용내역 공급가액 세액\n"
    "현지수수료\n"
    "출원유지료(14년차) (1115.00 EUR) 환율:1740 (2025-12-18) 1,940,100 0\n"
    "HMC 부담 -970,050 0\n"
    "소계 970,050 0\n"
    "합계 970,050 0\n"
    "총합계 (WON) 970,050\n"
)


def test_parse_overseas_youme_shared_cost() -> None:
    line = ip.parse_overseas_text(OVERSEAS_YOUME)
    assert line is not None
    assert line["application_no"] == "102012113179.1"
    assert line["line_total"] == 970050
    assert line["vat"] == 0
    assert line["foreign_currency"] == "EUR"
    assert line["fx_rate"] == 1740.0
    assert line["foreign_amount"] == 557.50  # 970,050 ÷ 1,740 (분담분)
    assert line["foreign_cost_krw"] == 970050
    assert line["cost_details"].get("균등분담업체수") is None  # HMC 부담만으로 단정 금지
    assert line["cost_details"]["환율기준일"] == "2025.12.18"
    assert "송금일" not in line["cost_details"]


def test_parse_overseas_annuity_year_ignores_calendar_year_in_title() -> None:
    line = ip.parse_overseas_text(
        OVERSEAS_YOUME.replace("차량용 응축기", "2026년 차량용 응축기")
    )
    assert line is not None
    assert line["annuity_year"] == "14"
    alternate_label = ip.parse_overseas_text(OVERSEAS_YOUME.replace("14년차", "15차유지료"))
    assert alternate_label is not None
    assert alternate_label["annuity_year"] == "15"


def test_overseas_sharing_and_fx_date_require_explicit_valid_evidence() -> None:
    assert ip._extract_equal_share_company_count("HMC 부담 -970,050") is None
    assert ip._extract_equal_share_company_count("비용분담 1 / 3") == 3
    assert ip._extract_equal_share_company_count("분담\n비율 1 / 3") == 3
    assert ip._extract_equal_share_company_count("1/2 지분") == 2
    assert ip._extract_equal_share_company_count("공동출원 2개사") is None
    assert ip._extract_equal_share_company_count("환율은 2026/1/3 기준") is None
    assert ip._extract_fx_reference_date("환율은 2026/05/20일자") == "2026.05.20"
    assert ip._extract_fx_reference_date("환율은 2026-13-40일자") is None
    assert (
        ip._extract_fx_reference_date("환율은 2026-13-40일자\n환율은 2026-05-20일자")
        == "2026.05.20"
    )
    assert ip._extract_fx_reference_date("환율 1,400 청구일 2026-05-20") is None
    assert ip._extract_fx_reference_date("환율 1,400 납부일 2026-05-20") is None
    assert ip._extract_fx_reference_date("환율 1,400 출원번호 2026-05-201234") is None
    assert ip._extract_fx_reference_date("환율: 1,400원 / USD (2026-05-20)") == "2026.05.20"
    unrelated_date = ip.parse_overseas_text(
        OVERSEAS_YOUME.replace("환율:1740 (2025-12-18)", "환율:1740\n청구일 2025-12-18")
    )
    assert unrelated_date is not None
    assert unrelated_date["cost_details"].get("환율기준일") is None
    full_amount = ip.parse_overseas_text(OVERSEAS_SINSEGI + "비용분담 1/3\n")
    assert full_amount is not None
    assert full_amount["cost_details"].get("균등분담업체수") is None
    mismatched = ip.parse_overseas_text(
        OVERSEAS_YOUME.replace("1115.00 EUR", "1000.00 EUR").replace(
            "HMC 부담", "비용분담 1/3\nHMC 부담"
        )
    )
    assert mismatched is not None
    assert mismatched["cost_details"].get("균등분담업체수") is None


# ── markpro 국내 연차 표 (3열: 관납료/수수료/합계) ─────────────────────────────
MARKPRO_DOMESTIC = (
    "Debit No. D26-0066\n"
    "번호 국가 권리 출원번호 등록번호 납부기한일 연차 항수 예상권리만료일\n"
    "발명의명칭\n"
    "권리인명\n"
    "비용분담정보 관납료(\\) 수수료(\\) 합계(\\)\n"
    "1 KR P 2013-0086164 10-2064159-00-00 2026-01-03 7 6 2033-07-22\n"
    "열교환기용 튜브\n"
    "주식회사 두원공조\n"
    "205,800 16,000 221,800\n"
)


def test_parse_markpro_domestic_3col() -> None:
    items = ip.parse_markpro_items(MARKPRO_DOMESTIC)
    assert len(items) == 1
    it = items[0]
    assert it["application_no"] == "10-2013-0086164"
    assert it["registration_no"] == "10-2064159"
    assert it["annuity_year"] == "7"
    assert it["supply_amount"] == 221800  # 관납료 + 수수료
    assert it["vat"] == 1600  # 수수료 × 10%
    assert it["line_total"] == 223400
    assert ip.reconcile(it)


# ── markpro 해외 등록유지 표 (6열: 부가세 컬럼 포함) ────────────────────────────
MARKPRO_OVERSEAS = (
    "Debit No. 126-0099\n"
    "총 건 수: 1건\n"
    "현지비용(US$) 현지비용(￦) 수수료(￦) 부가세(￦) 송금수수료(￦) 합계(￦)\n"
    "1 CN ZL201910260958.7 8 2039-04-02 1020190044248\n"
    "P 201910260958.7 2026-04-02 DOOWON CLIMATE CONTROL CO. LTD.\n"
    "차량용 냉난방 시스템\n"
    "376.62 561,239 130,000 13,000 31,549 735,788\n"
)


def test_parse_markpro_overseas_6col_vat() -> None:
    items = ip.parse_markpro_items(MARKPRO_OVERSEAS)
    assert len(items) == 1
    it = items[0]
    assert it["vat"] == 13000  # 부가세 컬럼을 직접 사용(5열 가정의 수수료×10% 아님)
    assert it["line_total"] == 735788
    assert it["supply_amount"] == 735788 - 13000
    assert ip.reconcile(it)


# ── domestic 유미 출원(총합계 (WON) + "합계 공급 부가세" 2칼럼 + 10-/제…호 없는 출원번호) ──
DOMESTIC_YUMI_FILING = (
    "청   구   서\n"
    "특허출원 2026-0091761\n"
    "냉매 모듈 및 이를 포함하는 열 관리 시스템\n"
    "비용내역 공급가액 세액\n"
    "수수료\n출원타임챠지\n2,200,000\n220,000\n"
    "HMC, KMC 부담\n-1,100,000\n-110,000\n"
    "관납료\n특허출원\n46,000\n0\n"
    "HMC, KMC 부담\n-23,000\n0\n"
    "소계\n1,100,000\n110,000\n소계\n23,000\n0\n"
    "합계\n1,123,000\n110,000\n"
    "총합계 (WON)\n1,233,000\n"
)


def test_parse_domestic_yumi_filing_total_won_and_app_no() -> None:
    line = ip.parse_domestic_page(DOMESTIC_YUMI_FILING, "국내출원")
    assert line is not None
    assert line["application_no"] == "10-2026-0091761"  # "특허출원 2026-…" → "10-" 보정
    assert line["supply_amount"] == 1123000  # "합 계" 2칼럼 직접 사용
    assert line["vat"] == 110000
    assert line["line_total"] == 1233000  # 총합계 (WON)
    assert ip.reconcile(line)


# ── domestic 한라 2026(부가세 단독 행 + 청구금액 ￦) ───────────────────────────────
DOMESTIC_HALLA_2026 = (
    "청   구   서\n"
    "명 칭 : 차량용 내부 열교환기를 갖는 전동식 컴프레서\n"
    "특허출원 제10-2026-0097676 호 건\n"
    "청구금액 : 일금일백사십육만이천이백원 (￦1,462,200)\n"
    "비 용 내 역\n"
    "수수료\n출원비용\n1,300,000\n1\n1,300,000\n"
    "부가세\n130,000\n소  계\n1,430,000\n"
    "관납료\n출원료\n32,200\n1\n32,200\n소  계\n32,200\n"
    "청 구 금 액 ( ① + ② )\n￦1,462,200\n"
)


def test_parse_domestic_halla_2026_standalone_vat() -> None:
    line = ip.parse_domestic_page(DOMESTIC_HALLA_2026, "국내출원")
    assert line is not None
    assert line["application_no"] == "10-2026-0097676"
    assert line["line_total"] == 1462200  # 청구금액 ￦
    assert line["vat"] == 130000  # "부가세\n130,000" 단독 행 폴백
    assert line["supply_amount"] == 1332200  # 합계 − 부가세
    assert ip.reconcile(line)


def test_parse_domestic_claim_amount_ascii_item_numbers() -> None:
    # 청구금액 라벨과 원화기호 사이에 항목번호/산식이 ASCII 숫자(③→"3", "( ① + ② )"→
    # "( 1 + 2 )")로 추출돼도 합계를 잡아야 한다. ([^\d] 기반 패턴이 그 숫자에서 멈춰
    # claim_total=0 → 다른 합계로 조용히 오산하던 회귀 방지.)
    for head in ("청 구 금 액 3 ￦ 1,462,200", "청 구 금 액 ( 1 + 2 ) ￦1,462,200"):
        page = (
            "청 구 서\n특허출원 제10-2026-0097676 호\n"
            "수수료\n출원비용\n1,300,000\n1\n1,300,000\n부가세\n130,000\n"
            "관납료\n출원료\n32,200\n1\n32,200\n" + head + "\n"
        )
        line = ip.parse_domestic_page(page, "국내출원")
        assert line is not None, head
        assert line["line_total"] == 1462200, head
        assert line["vat"] == 130000, head
        assert line["supply_amount"] == 1332200, head
        assert ip.reconcile(line), head


# ── domestic 원화기호가 백슬래시(\)인 청구서(의견제출) ───────────────────────────────
DOMESTIC_BACKSLASH_WON = (
    "청 구 서\n"
    "제 목 : 특허출원 제10-2021-0102192호의 OA대응 청구의 건\n"
    "청 구 내 역\n"
    "1) 대리인비용\nOA대응료 \\ 80,833\n부가세 \\ 8,083\n소 계 \\ 88,916\n"
    "2) 관납료\n관납료 \\ 1,333\n소 계 \\ 1,333\n"
    "3) 합 계 : \\90,249\n* 청 구 금 액 : \\90,249\n"
)


def test_parse_domestic_skips_zero_supply_noise_page() -> None:
    # 합계/요약 페이지: 부가세 숫자만 잡히고 공급가액이 없으면 청구 라인이 아니다.
    # (합계=부가세로 reconcile를 통과해 0원 노이즈 라인이 생기던 회귀 방지)
    noise = "비 용 청 구 서\n관납료 합계\n부가세\n22,400\n"
    assert ip.parse_domestic_page(noise, "연차료") is None


def test_parse_domestic_backslash_won_sign() -> None:
    line = ip.parse_domestic_page(DOMESTIC_BACKSLASH_WON, "의견제출")
    assert line is not None
    assert line["application_no"] == "10-2021-0102192"
    assert line["line_total"] == 90249  # 청구금액 \90,249 (백슬래시 원화기호)
    assert line["vat"] == 8083
    assert line["supply_amount"] == 82166
    assert ip.reconcile(line)


# ── overseas 한양국제특허(USD/WON 쌍·(A)/(B) 소계·중복 글자 "청청 구구 금금 액액") ─────
OVERSEAS_HANYANG = (
    "http://www.hanyanglaw.com\n청청 구구 서서\n"
    "제 목：차량의 공조 장치\n"
    "미국 특허출원(18/228,493) Miscellaneous Action대응료 청구의 건\n"
    "구분 청구내역 외화비용 원화비용\n"
    "·Miscellaneous Action대응료[두원공조] USD 175.00 WON 265,767\n"
    "해외비용 ·국외송금수수료 USD 0.00 WON 500\n"
    "소 계(A) USD 175.00 WON 266,267\n"
    "·대리인 수수료 WON 67,933\n"
    "국내비용 ·부가가치세(VAT) WON 6,793\n"
    "소 계(B) WON 74,726\n"
    "청청 구구 금금 액액 (A + B) WON 340,993\n"
    "※ 해외비용 환율은 2026-05-20일자 1,518.67 ￦/USD 입니다.\n"
    "(유)한양특허법인\n"
)


def test_detect_vendor_hanyang() -> None:
    assert ip.detect_vendor(OVERSEAS_HANYANG) == "한양"


def test_parse_overseas_hanyang() -> None:
    line = ip.parse_overseas_hanyang(
        OVERSEAS_HANYANG, filename="4-3. 미국출원특허 18228,493호의 1차 OA 비용청구서.pdf"
    )
    assert line is not None
    assert line["application_no"] == "18/228,493"
    assert line["line_total"] == 340993  # 청구금액 (A + B)
    assert line["vat"] == 6793
    assert line["supply_amount"] == 334200  # 합계 − 부가세
    assert line["foreign_currency"] == "USD"
    assert line["foreign_amount"] == 175.0
    assert line["fx_rate"] == 1518.67
    assert line["foreign_cost_krw"] == 265767  # 해외비용 소계(A) − 송금수수료
    assert line["cost_details"]["대리인수수료"] == 67933  # 공급가액 − 해외비용 소계(A)
    assert line["cost_details"]["송금수수료"] == 500
    assert line["cost_details"]["업무"] == "1차 OA"  # 파일명에서 추출
    assert line["cost_details"].get("균등분담업체수") is None
    assert line["cost_details"]["환율기준일"] == "2026.05.20"
    assert "송금일" not in line["cost_details"]
    assert ip.reconcile(line)


# ── 라우팅: 유미 국내 출원은 "총합계 (WON)"이 있어도 해외로 가지 않는다(버그 가드) ──
def test_parse_file_routes_yumi_filing_to_domestic(monkeypatch) -> None:
    monkeypatch.setattr(ip, "_pages_from_content", lambda *a, **k: [DOMESTIC_YUMI_FILING])
    lines = ip.parse_file(
        None,
        workspace_id="w",
        actor_user_id=None,
        filename="2-1. 특허출원 10-2026-0091761호 외 6건에 대한 특허출원 비용청구서.pdf",
        content=b"",
        mime_type="application/pdf",
        region_hint="산업",
    )
    assert len(lines) == 1
    assert lines[0]["region"] == "산업"  # 해외 오라우팅 금지
    assert lines[0]["section"] == "국내출원"
    assert lines[0]["application_no"] == "10-2026-0091761"


def test_parse_file_routes_hanyang_to_overseas(monkeypatch) -> None:
    monkeypatch.setattr(ip, "_pages_from_content", lambda *a, **k: [OVERSEAS_HANYANG])
    lines = ip.parse_file(
        None,
        workspace_id="w",
        actor_user_id=None,
        filename="4-3. 미국출원특허 18228,493호의 1차 OA 비용청구서.pdf",
        content=b"",
        mime_type="application/pdf",
        region_hint="산업",  # 국내 배치로 올려도 내용 신호로 해외 판정
    )
    assert len(lines) == 1
    assert lines[0]["region"] == "해외"
    assert lines[0]["application_no"] == "18/228,493"


def test_run_cost_ingest_reliability_warnings(monkeypatch) -> None:
    """검증 패널 경고: ① 파일명 '외 N건' 대비 추출 부족(누락 의심, 연차료 제외),
    ② 특허현황관리 미매칭(명칭·발명자 빈칸)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    fn_filing = "2-1. 특허출원 10-2026-0097676호 외 2건에 대한 특허출원 비용청구서.pdf"
    fn_annuity = "2-5. 등록특허 10-2026-0097676호 외 9건에 대한 연차료 비용청구서.pdf"
    pages = {fn_filing: [DOMESTIC_HALLA_2026], fn_annuity: [DOMESTIC_HALLA_2026]}
    monkeypatch.setattr(ip, "_pages_from_content", lambda filename, content, mime: pages[filename])
    with Session(engine) as db:
        ws = Workspace(id="w", key="w", name="W")
        u = User(id="u", login_id="u", email="u@t.t", full_name="U", password_hash="h")
        db.add_all([ws, u])
        db.commit()
        run = ip.run_cost_ingest(
            db, workspace=ws, user=u,
            files=[(fn_filing, b"x", "application/pdf"), (fn_annuity, b"x", "application/pdf")],
            region="산업", fiscal_period="2026-06",
        )
    msgs = run.warnings["messages"]
    # ① 출원 청구서: 3건('외 2건') 기대인데 1건만 → 누락 의심
    assert any("[누락 의심]" in m and "2-1" in m for m in msgs)
    # ① 연차료는 HMC 부담 제외가 정상 → 누락 의심 경고 안 함
    assert not any("[누락 의심]" in m and "2-5" in m for m in msgs)
    # ② 특허현황관리에 레코드 없음 → 미매칭 경고
    assert any("[미매칭]" in m for m in msgs)


# ── summary builders ─────────────────────────────────────────────────────────
def _line(**kw):
    base = dict(
        region="산업",
        section="국내출원",
        title="차량용 공조장치",
        application_no="10-2025-0203274",
        registration_no="",
        application_date="2025-12-18",
        registration_date=None,
        inventors="김민섭",
        annuity_year=None,
        vendor="한라",
        supply_amount=1332200,
        vat=130000,
        foreign_currency=None,
        foreign_amount=None,
        fx_rate=None,
        foreign_cost_krw=0,
        cost_details={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_import_scope_guard_preserves_other_scope() -> None:
    """부분 업로드(국내-only/해외-only)가 다른 scope의 공유 레코드를 미러 삭제하지 못하게 하는
    가드. 해외-only 업로드 시 국내(연도/수기) 레코드는 삭제 대상이 아니어야 한다."""
    from ai_do_api.domains.patent_automation import field_defs as fd
    from ai_do_api.domains.patent_automation import service

    ov = fd.OVERSEAS_SOURCE_SHEET
    # 해외-only 업로드: 해외 레코드만 삭제 대상, 국내(연도/수기=None)는 보존.
    assert service._in_import_scope(ov, imported_domestic=False, imported_overseas=True) is True
    assert (
        service._in_import_scope("2025", imported_domestic=False, imported_overseas=True) is False
    )
    assert service._in_import_scope(None, imported_domestic=False, imported_overseas=True) is False
    # 국내-only 업로드: 국내만 삭제 대상, 해외는 보존.
    assert service._in_import_scope("2024", imported_domestic=True, imported_overseas=False) is True
    assert service._in_import_scope(ov, imported_domestic=True, imported_overseas=False) is False
    # 라운드트립(전체 export 재임포트): 양쪽 모두 삭제 대상(완전 미러).
    assert service._in_import_scope("2024", imported_domestic=True, imported_overseas=True) is True
    assert service._in_import_scope(ov, imported_domestic=True, imported_overseas=True) is True


def test_delete_record_preserves_cost_lines_by_nulling_record_reference() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        workspace = Workspace(id="workspace-1", key="workspace", name="Workspace")
        user = User(
            id="user-1",
            login_id="user-1",
            email="user-1@example.test",
            full_name="User One",
            password_hash="hash",
        )
        db.add_all([workspace, user])
        db.commit()

        record = service.create_record(
            db,
            workspace=workspace,
            user=user,
            values={
                "application_no": "10-2025-0203274",
                "invention_title": "차량용 공조장치",
            },
            stable_record_id="stable-record-1",
        )
        run = PatentCostRun(
            id="run-1",
            workspace_id=workspace.id,
            fiscal_period="2026-01",
            status="completed",
        )
        db.add(
            PatentCostLine(
                id="line-1",
                workspace_id=workspace.id,
                run_id=run.id,
                record_id=record.id,
                region="산업",
                section="국내출원",
            )
        )
        db.add(run)
        db.commit()

        service.delete_record(db, workspace=workspace, user=user, record_id=record.id)

        cost_line = db.scalar(select(PatentCostLine).where(PatentCostLine.id == "line-1"))
        assert cost_line is not None
        assert cost_line.record_id is None


def test_build_approval_html_header_count_is_vat_count() -> None:
    from ai_do_api.domains.patent_automation import approval_html as ah

    lines = [
        _line(section="심사청구", supply_amount=500000, vat=0),  # 관납료만 → vat 0
        _line(section="심사청구", supply_amount=300000, vat=0),
        _line(section="의견제출", supply_amount=200000, vat=20000),  # vat 있음
        _line(section="의견제출", supply_amount=100000, vat=0),  # vat 없음
    ]
    html = ah.build_approval_html(lines, period="2026-01", count_amount=None)
    # 헤더 "N건" = vat>0 항목 수. 심사청구=0건, 의견제출=1건.
    assert "심사청구 비용: 800,000원 (부가세별도, 0건)" in html
    assert "의견제출 비용: 300,000원 (부가세별도, 1건)" in html
    assert "총&nbsp; 비&nbsp; 용 : <b>1,100,000원 (부가세별도)" in html
    assert "border:1px solid #000" in html and 'border="1"' not in html  # 실선 통일


def test_parse_count_amount_xlsx_roundtrip() -> None:
    from ai_do_api.domains.patent_automation import approval_html as ah

    lines = [_line(), _line(section="심사청구", supply_amount=839300, vat=0)]
    xlsx = sx.build_count_amount_summary(lines, period="2026-01", date_label="2026.01")
    ca = ah.parse_count_amount_xlsx(xlsx)
    assert ca["year"] == "2026"
    assert ca["rows"][0][0] == "1월"
    # 카테고리 셀은 리터럴 값(국내출원·심사청구) → 정확히 파싱. (월별비용/합계는 수식이라
    # openpyxl 생성 픽스처엔 캐시값이 없어 0; 실제 엑셀 파일은 캐시가 있어 정상 동작.)
    cats = ca["rows"][0][1]
    assert cats[0] == (1, 1332200)  # 국내출원
    assert cats[1] == (1, 839300)  # 심사청구


def test_build_industrial_summary_overseas_annotation() -> None:
    lines = [
        _line(),
        _line(
            region="해외",
            section="해외",
            title="차량용 듀얼 블로워 시스템",
            application_no="19/394,605",
            inventors="황우만",
            supply_amount=1758634,
            vat=25898,
            cost_details={"업무": "특허출원"},
        ),
    ]
    data = sx.build_industrial_summary(
        lines, title="2026년 1월 산업재산권 지출 비용 요약", date_label="2026.01"
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("[미국출원특허(19/394,605)건의 특허출원 비용]" in t for t in texts)


def test_korean_title_strips_english_paren() -> None:
    assert sx.korean_title("차량용 응축기(CONDENSER FOR VEHICLE)") == "차량용 응축기"
    assert (
        sx.korean_title("전기자동차의 폐열관리시스템 및 관리방법(SYSTEM AND METHOD)")
        == "전기자동차의 폐열관리시스템 및 관리방법"
    )
    # 한글 괄호·괄호 없는 명칭은 그대로 보존
    assert (
        sx.korean_title("내-외기 분리 유동 제어가 가능한 자동차용 공조 장치")
        == "내-외기 분리 유동 제어가 가능한 자동차용 공조 장치"
    )
    assert sx.korean_title("장치(제어방법)") == "장치(제어방법)"


def test_build_overseas_summary_fx_won_glyph_and_korean_title() -> None:
    lines = [
        _line(
            region="해외",
            section="해외",
            application_no="19/394,605",
            title="차량용 듀얼 블로워 시스템(DUAL BLOWER)",
            supply_amount=1758634,
            vat=25898,
            foreign_currency="USD",
            foreign_amount=1006.0,
            fx_rate=1490.71,
            foreign_cost_krw=1499654,
            cost_details={
                "업무": "특허출원",
                "해외비용": 1499654,
                "대리인수수료": 258980,
                "송금수수료": 0,
            },
        )
    ]
    data = sx.build_overseas_summary(
        lines, title="2026년 1월 해외특허 지출 비용 정리", date_label="2026.01"
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("1 USD = 1,490.71 \\)" in t for t in texts)  # 환율 라인 원화 글리프
    assert any('"차량용 듀얼 블로워 시스템"' in t for t in texts)  # 영문 병기 제거
    assert not any("DUAL BLOWER" in t for t in texts)


def test_build_overseas_summary_does_not_invent_sharing_or_remittance() -> None:
    parsed = ip.parse_overseas_text(OVERSEAS_YOUME)
    assert parsed is not None
    data = sx.build_overseas_summary(
        [_line(**parsed)],
        title="2026년 1월 해외특허 지출 비용 정리",
        date_label="2026.01",
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("출원유지료 비용\n(EUR 557.50)" in text for text in texts)
    assert not any("업체" in text for text in texts)
    assert any("환율 기준일: 2025.12.18" in text for text in texts)
    assert not any("송금되었음" in text for text in texts)


def test_build_overseas_summary_uses_explicit_equal_share_ratio() -> None:
    parsed = ip.parse_overseas_text(OVERSEAS_YOUME.replace("HMC 부담", "비용분담 1/2\nHMC 부담"))
    assert parsed is not None
    assert parsed["cost_details"]["균등분담업체수"] == 2
    assert parsed["cost_details"]["외화총액"] == 1115.0
    data = sx.build_overseas_summary(
        [_line(**parsed)],
        title="2026년 1월 해외특허 지출 비용 정리",
        date_label="2026.01",
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("출원유지료 비용\n(1115.00 EUR / 2업체)" in text for text in texts)


def test_build_overseas_summary_preserves_explicit_shared_amount_cents() -> None:
    line = _line(
        region="해외",
        section="해외",
        foreign_currency="USD",
        foreign_amount=175.25,
        cost_details={
            "업무": "특허출원",
            "해외비용": 100,
            "대리인수수료": 0,
            "송금수수료": 0,
            "균등분담업체수": 3,
            "외화총액": 525.75,
            "송금일": "2026.05.20",
        },
    )
    data = sx.build_overseas_summary(
        [line], title="2026년 1월 해외특허 지출 비용 정리", date_label="2026.01"
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("특허출원 비용\n(525.75 USD / 3업체)" in text for text in texts)
    assert any("환율 기준일: 2026.05.20" in text for text in texts)
    assert not any("송금되었음" in text for text in texts)


def test_build_overseas_summary_preserves_markpro_amount_without_share_evidence() -> None:
    parsed = ip.parse_markpro_items(MARKPRO_OVERSEAS)
    assert len(parsed) == 1
    parsed[0]["cost_details"]["업체수"] = 3  # 수정 전 MR parser가 저장한 legacy 기본값
    data = sx.build_overseas_summary(
        [_line(**parsed[0])],
        title="2026년 1월 해외특허 지출 비용 정리",
        date_label="2026.01",
    )
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any("등록유지 비용\n(USD 376.62)" in text for text in texts)
    assert not any("업체" in text for text in texts)


def test_build_count_amount_summary_row() -> None:
    lines = [_line(), _line(section="심사청구", supply_amount=839300, vat=0)]
    data = sx.build_count_amount_summary(lines, period="2026-01", date_label="2026.01")
    ws = openpyxl.load_workbook(BytesIO(data), data_only=True).worksheets[0]
    # 1월 행(r7): 출원 건수 C7=1 / 금액 D7=1,332,200
    assert ws["C7"].value == 1
    assert ws["D7"].value == 1332200


def test_summary_builders_normalize_compact_period() -> None:
    lines = [_line()]
    data = sx.build_count_amount_summary(lines, period="202606", date_label="2026.06")
    ws = openpyxl.load_workbook(BytesIO(data), data_only=True).worksheets[0]
    assert ws.title == "2026년 특허비용실적"
    assert ws["C12"].value == 1
    assert ws["D12"].value == 1332200

    industrial = sx.build_industrial_summary(
        lines, title="2026년 6월 산업재산권 지출 비용 요약", date_label="2026.06", period="202606"
    )
    assert openpyxl.load_workbook(BytesIO(industrial)).worksheets[0].title == "2026년 06월"


def test_build_overseas_summary_smoke() -> None:
    lines = [
        _line(
            region="해외",
            section="해외",
            application_no="19/394,605",
            supply_amount=1758634,
            vat=25898,
            foreign_currency="USD",
            foreign_amount=1006.0,
            fx_rate=1490.71,
            foreign_cost_krw=1499654,
            cost_details={
                "업무": "특허출원",
                "해외비용": 1499654,
                "대리인수수료": 258980,
                "송금수수료": 0,
            },
        )
    ]
    data = sx.build_overseas_summary(
        lines, title="2026년 1월 해외특허 지출 비용 정리", date_label="2026.01"
    )
    assert openpyxl.load_workbook(BytesIO(data)).worksheets[0].max_row > 5


# ── 직무발명신고서 파서 ────────────────────────────────────────────────────────
def test_parse_disclosure_form() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "직 무 발 명 신 고 서"
    ws["A5"] = "발명의 명칭"
    ws["C5"] = "차량용 에어벤트 풍량조절 시스템"
    ws["A7"] = "국문"
    ws["C7"] = "박재성\n김영민"
    ws["A9"] = "소속부서"
    ws["C9"] = "기술지원팀"
    buf = BytesIO()
    wb.save(buf)
    vals = parse_disclosure_form(buf.getvalue())
    assert vals["invention_title"] == "차량용 에어벤트 풍량조절 시스템"
    assert vals["inventors"] == "박재성,김영민"
    assert vals["submitter_name"] == "박재성"
    assert vals["submit_team"] == "기술지원팀"
