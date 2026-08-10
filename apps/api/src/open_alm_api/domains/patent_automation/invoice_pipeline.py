"""Parse uploaded PDF/XLSX invoices into classified, reconciled cost lines.

Strategy: per-vendor regex fast path (한라 국내, 신세기 해외) with an LLM
fallback (``llm_extract``) for unknown vendors or when reconciliation fails.
Each line stores **summary-ready** amounts:

* ``supply_amount`` (공급가액) — domestic: 수수료 + 관납료 ; overseas: 해외비용 + 대리인수수료
* ``vat`` (부가세) ; ``line_total`` (합계) = supply_amount + vat
* raw breakdown kept in ``cost_details`` for audit.

Reconciliation cross-checks ``supply_amount + vat == line_total`` and against
the invoice's stated 청구금액; mismatches flag ``reconciled=False`` for review.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.document_processing import extract_document
from open_alm_api.domains.patent_automation import field_defs as fd
from open_alm_api.domains.patent_automation import llm_extract
from open_alm_api.domains.patent_automation.models import (
    PatentCostLine,
    PatentCostRun,
    PatentRecord,
)


# Section keys used in the 산업재산권 summary (order matters).
SECTION_DOMESTIC_FILING = "국내출원"
SECTION_EXAM_REQUEST = "심사청구"
SECTION_OPINION = "의견제출"
SECTION_REEXAM = "재심사"
SECTION_REGISTRATION = "특허등록"
SECTION_ANNUITY = "연차료"
SECTION_OVERSEAS = "해외"

SUMMARY_SECTION_ORDER = [
    SECTION_DOMESTIC_FILING,
    SECTION_EXAM_REQUEST,
    SECTION_OPINION,
    SECTION_REEXAM,
    SECTION_REGISTRATION,
    SECTION_ANNUITY,
    SECTION_OVERSEAS,
]

# Checked against the service-type phrase ("...에 대한 <TYPE> 비용청구서"), most
# specific first; 출원 last so it doesn't shadow 심사청구/등록 etc.
_FILENAME_SECTION = [
    ("심사청구", SECTION_EXAM_REQUEST),
    ("재심사", SECTION_REEXAM),
    ("의견제출", SECTION_OPINION),
    ("등록유지료", SECTION_ANNUITY),
    ("유지료", SECTION_ANNUITY),
    ("연차료", SECTION_ANNUITY),
    ("특허등록", SECTION_REGISTRATION),
    ("등록", SECTION_REGISTRATION),
    ("특허출원", SECTION_DOMESTIC_FILING),
    ("출원", SECTION_DOMESTIC_FILING),
]

_RE_SERVICE_PHRASE = re.compile(r"대한\s*(.+?)\s*비용\s*청구서")


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    text = re.sub(r"[^\d.]", "", str(value))
    return float(text) if text else 0.0


def section_from_filename(filename: str) -> str:
    name = filename or ""
    # Prefer the actual service type from "...에 대한 <TYPE> 비용청구서"; the
    # leading "특허출원 제…호" subject would otherwise shadow it.
    phrase = _RE_SERVICE_PHRASE.search(name)
    segment = phrase.group(1) if phrase else name
    for keyword, section in _FILENAME_SECTION:
        if keyword in segment:
            return section
    return SECTION_DOMESTIC_FILING


def detect_vendor(text: str) -> str:
    compact = text.replace(" ", "")
    if "마크프로" in compact or "markpro" in text.lower() or "DebitNo." in compact:
        return "마크프로"
    # 한양국제특허법인(USD/WON·(A)/(B)·"청구금액 (A + B)" 형식) — 한라보다 먼저 검사.
    if "한양특허법인" in compact or "한양국제특허" in compact or "hanyanglaw" in text.lower():
        return "한양"
    if "한라특허법인" in compact:
        return "한라"
    if "특허법인신세기" in compact or "POG" in text:
        return "신세기"
    if "유미특허법인" in compact or "YOUME" in compact or "총합계(WON)" in compact:
        return "유미"
    return "기타"


# ── PDF → page texts ────────────────────────────────────────────────────────
def _pages_from_content(filename: str, content: bytes, mime_type: str) -> list[str]:
    bundle = extract_document(
        document_id=new_id(),
        filename=filename,
        mime_type=mime_type or "application/pdf",
        content=content,
    )
    return [block.text for block in bundle.evidence_blocks if block.text and block.text.strip()]


# ── domestic (한라) ────────────────────────────────────────────────────────────
_RE_APP_NO = re.compile(r"제\s*(\d{2}-\d{4}-\d{7})\s*호")
_RE_REG_NO = re.compile(r"제\s*(\d{2}-\d{6,7})\s*호")
_RE_TITLE = re.compile(r"명\s*칭\s*[:：]\s*(.+)")
_RE_SUPPLY = re.compile(r"수수료\s+[\d,]+\s+\d+\s+([\d,]+)")
_RE_VAT = re.compile(r"수수료\s*부가세\s+([\d,]+)")
# 한라 2026/기타 양식: 부가세가 "수수료부가세" 한 토큰이 아니라 단독 라벨로 찍히고
# ("부가세\n130,000" 또는 "부가세  ￦ 8,083"), 라벨과 숫자 사이에 ￦/공백이 낀다.
# 위 정규식이 실패할 때의 폴백(첫 숫자열까지의 비숫자 문자를 건너뜀).
_RE_VAT_STANDALONE = re.compile(r"부\s*가\s*세[^\d]{0,8}([\d,]+)")
_RE_GOV_FEE = re.compile(r"관납료\s+[\d,]+\s+\d+\s+([\d,]+)")
# 원화 기호는 추출기/폰트에 따라 ￦(U+FFE6)·₩(U+20A9)·\\(U+5C)로 제각각 렌더된다.
# 라벨과 기호 사이의 항목번호/산식(③·"( ① + ② )"·ASCII "3"·"( 1 + 2 )")을 건너뛰어야
# 하므로 "원화기호가 아닌 문자"를 허용한다([^\d]로 막으면 ASCII 숫자 표기를 놓침).
_RE_CLAIM_AMOUNT = re.compile(r"청\s*구\s*금\s*액[^￦₩\\]*[￦₩\\]\s*([\d,]+)")
_RE_APP_NO_LOOSE = re.compile(r"(\d{2}-\d{4}-\d{7})")  # "제…호" 없이 (10-2023-…) 형태도
# 유미 국내: "특허출원 2026-0091761"(제…호·"10-" 접두 없는 4-7자리) → "10-" 보정.
_RE_APP_NO_YUMI = re.compile(r"특허\s*출원\s*(\d{4}-\d{7})")
# 청구금액 ￦ 라인이 없는 국내(신세기/유미) 관납료-only 심사청구: "합 계"/"총합계 (WON)"
_RE_DOM_TOTAL_WON = re.compile(r"총\s*합\s*계\s*\(?\s*WON\s*\)?[^\d]*([\d,]+)")
_RE_DOM_TOTAL_SUM = re.compile(r"합\s*계\s+([\d,]+)")
# 유미 국내: "합 계 {공급가액} {부가세}" 두 칼럼(HMC/KMC 분담 차감 후 순액). 청구금액 ￦
# 라인이 없어 공급가액·부가세를 직접 못 잡을 때 이 합계행에서 두 칼럼을 읽는다.
_RE_DOM_SUPPLY_VAT = re.compile(r"합\s*계\s+([\d,]+)\s+([\d,]+)")
_RE_ANNUITY_YEAR = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:(?:년|연)\s*차(?:료)?|차\s*유지(?:료)?)"
    r"(?=$|[\s,.;:()\[\]/])"
)


def _is_invoice_page(text: str) -> bool:
    compact = text.replace(" ", "")
    # 청구금액 ￦(한라) 또는 관납료(신세기/유미 국내) 가 있는 청구서 페이지.
    return "청구서" in compact and ("청구금액" in compact or "관납료" in compact)


def _extract_annuity_year(text: str) -> str | None:
    for match in _RE_ANNUITY_YEAR.finditer(text):
        if 1 <= int(match.group(1)) <= 30:
            return match.group(1)
    return None


def parse_domestic_page(text: str, section: str) -> dict[str, Any] | None:
    if not _is_invoice_page(text):
        return None
    app_match = _RE_APP_NO.search(text)
    reg_match = _RE_REG_NO.search(text)
    title_match = _RE_TITLE.search(text)
    supply = _to_int(_RE_SUPPLY.search(text).group(1)) if _RE_SUPPLY.search(text) else 0
    vat_m = _RE_VAT.search(text) or _RE_VAT_STANDALONE.search(text)
    vat = _to_int(vat_m.group(1)) if vat_m else 0
    gov_fee = _to_int(_RE_GOV_FEE.search(text).group(1)) if _RE_GOV_FEE.search(text) else 0
    claim_total = (
        _to_int(_RE_CLAIM_AMOUNT.search(text).group(1)) if _RE_CLAIM_AMOUNT.search(text) else 0
    )

    # Universal rule across all 한라 domestic invoice types (출원/심사청구/의견제출/
    # 재심사/등록): 합계 = 청구금액(③), 공급가액 = 청구금액 − 부가세. 관납료는
    # 비과세라 공급가액에 포함되지만 별도 합산할 필요 없이 청구금액에서 역산된다.
    if claim_total > 0:
        total = claim_total
        supply_amount = total - vat
    else:
        # 청구금액 ￦ 없음(신세기/유미 국내 관납료-only) → 합계/총합계 (WON)에서 역산.
        won_m = _RE_DOM_TOTAL_WON.search(text) or _RE_DOM_TOTAL_SUM.search(text)
        if won_m:
            total = _to_int(won_m.group(1))
            # 유미 국내: "합 계 {공급가액} {부가세}" 두 칼럼을 직접 사용(수수료/관납료 라벨이
            # 한라식 "수수료 a b c"가 아니라 별행이라 supply/vat가 0으로 나오는 경우 보정).
            sv = _RE_DOM_SUPPLY_VAT.search(text) if (supply == 0 and vat == 0) else None
            if sv:
                supply_amount = _to_int(sv.group(1))
                vat = _to_int(sv.group(2))
            else:
                supply_amount = total - vat
        else:
            supply_amount = supply + gov_fee
            total = supply_amount + vat
    # 공급가액 0 = 청구 페이지가 아닌 합계/요약/연속 페이지(부가세 숫자만 우연히 잡혀
    # 합계=부가세로 reconcile를 통과하는 노이즈 라인 방지). 정상 청구는 공급가액>0.
    if supply_amount <= 0:
        return None
    app_no = (
        (app_match.group(1) if app_match else "")
        or (_RE_APP_NO_LOOSE.search(text).group(1) if _RE_APP_NO_LOOSE.search(text) else "")
        or ("10-" + _RE_APP_NO_YUMI.search(text).group(1) if _RE_APP_NO_YUMI.search(text) else "")
    )
    # 연차료 청구서(단일 특허)는 "…호 8 연차" / "관납료 8 년차료"처럼 년차 표기가 있다.
    # 비용요약 '5. 연차료 비용'의 년차 칸에 채워지도록 여기서 추출한다.
    annuity_year = _extract_annuity_year(text) if section == SECTION_ANNUITY else None
    return {
        "section": section,
        "region": "산업",
        "application_no": app_no,
        "registration_no": reg_match.group(1) if reg_match else "",
        "title": title_match.group(1).strip() if title_match else "",
        "annuity_year": annuity_year,
        "supply_amount": supply_amount,
        "vat": vat,
        "gov_fee": gov_fee,
        "line_total": total,
        "claim_total": claim_total,
        "cost_details": {
            "수수료": supply,
            "관납료": gov_fee,
            "부가세": vat,
            "청구금액": claim_total,
        },
    }


# ── overseas (신세기 / 마크프로) ─────────────────────────────────────────────────
# Universal rule (verified across 신세기 출원/OA/등록/유지료 and 마크프로 합산):
# 합계 = 청구 총액, 공급가액 = 합계 − 부가세 (송금수수료·대리인수수료·해외비용은
# 모두 합계에서 역산되므로 항목별 합산이 불필요).
# 출원번호는 공백 포함 가능("제10 2011 090 125.6호") → 캡처 후 공백 제거.
_RE_O_APPNO = re.compile(r"제\s*([0-9][0-9 \t/.,Xx-]*[0-9Xx])\s*호")
# 유미/한라 해외: "특허출원 102012113179.1" / "출원번호 102019111127.7"(제…호 아님)
_RE_O_APPNO_ALT = re.compile(
    r"(?:특허\s*출원|출원\s*번호)\s*(?:제\s*)?([0-9][0-9 \t/.,Xx-]*[0-9Xx])"
)
_RE_O_TITLE = re.compile(r"호\s*\(([^)]+)\)")
_RE_O_CCY = re.compile(r"\b(USD|EUR)\s*([\d,]+\.\d+)")
_RE_O_FX = re.compile(r"1\s*(?:USD|EUR)\s*=\s*([\d,]+\.?\d*)\s*원")
_RE_O_VAT = re.compile(r"부\s*가\s*세[^\d]*([\d,]+)")  # 원/￦ 무관
_RE_O_TOTAL = re.compile(r"합\s*계[^\d]*([\d,]+)\s*원")
_RE_O_TOTAL_CHONG = re.compile(r"총\s*계[^\d]*([\d,]+)")  # 한라 해외 유지료 "총 계 ￦..."
_RE_MP_VAT = re.compile(r"부\s*가\s*세[^\d]*([\d,]+)")
_RE_MP_TOTAL = re.compile(r"총비용\s*합계[^\d]*([\d,]+)")
_RE_DEBIT = re.compile(r"Debit\s*No\.\s*([\w-]+)")


_RE_O_TOTAL_WON = re.compile(r"총\s*합\s*계\s*\(?\s*WON\s*\)?[^\d]*([\d,]+)")  # 유미 등
_RE_O_TOTAL_LOOSE = re.compile(r"합\s*계\s+([\d,]+)")
# 신세기 당소수수료 내역(대리인수수료 = 착수금 + 번역비 + 기타 당소 항목)·송금수수료
_RE_O_FEE_START = re.compile(r"착\s*수\s*금[^\d]*([\d,]+)")
_RE_O_FEE_TRANS = re.compile(r"번\s*역\s*비\s*용[^\d]*([\d,]+)")
_RE_O_REMIT = re.compile(r"송\s*금\s*수\s*수\s*료[^\d]*([\d,]+)")
# 유미특허법인: "부가세" 라벨 없이 "세액" 컬럼 사용 → "합 계 {공급가액} {세액}".
_RE_O_SUM_VAT = re.compile(r"합\s*계\s+([\d,]+)\s+([\d,]+)")
# 유미: 금액-통화 순서 "(1115.00 EUR)" — 신세기의 통화-금액 순서와 반대.
_RE_O_CCY_ALT = re.compile(r"([\d,]+\.\d+)\s*(USD|EUR)")
# 유미: "환율:1740" — 신세기의 "1EUR=…원" 형식이 아님.
_RE_O_FX_ALT = re.compile(r"환\s*율\s*[:：]?\s*([\d,]+(?:\.\d+)?)")
# 신세기 해외비용 소계(첫 '소 계 …원') = 원화비용 + 송금수수료. 당소수수료가
# 착수금/번역비가 아닌 "OA검토비용" 등으로 표기돼도 정확히 분리하기 위한 앵커.
_RE_O_OVS_SUBTOTAL = re.compile(r"소\s*계\s*([\d,]+)\s*원")


def _extract_equal_share_company_count(text: str) -> int | None:
    """명시된 균등 분담률(예: '분담 1/3', '1/2 지분')의 전체 업체 수."""
    patterns = (
        r"(?:분담|부담|지분)\s*(?:비율|률|율)?\s*[:：]?\s*1\s*/\s*(\d+)",
        r"1\s*/\s*(\d+)\s*(?:분담|부담|지분)\s*(?:비율|률|율)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match and 2 <= int(match.group(1)) <= 20:
            return int(match.group(1))
    return None


def _extract_fx_reference_date(text: str) -> str | None:
    """청구환율 고시·기준일을 'YYYY.MM.DD'로. 예: '청구환율은 2026-05-21',
    '환율:1753 (2026-05-20)', '환율은 2026-05-20일자'."""
    marker = r"환[ \t]*율"
    reference_label = r"(?:기준|고시|적용)[ \t]*일"
    rate = r"[\d,]+(?:\.\d+)?"
    currency = r"[ \t]*(?:원)?(?:[ \t]*/[ \t]*(?:USD|EUR|JPY|CNY))?"
    date_value = (
        r"(?P<year>\d{4})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})(?!\d)"
    )
    patterns = (
        rf"{marker}(?:[ \t]*(?:은|는))?[ \t]*[:：]?[ \t]*{date_value}",
        rf"{marker}[ \t]*{reference_label}(?:[ \t]*(?:은|는))?[ \t]*[:：]?[ \t]*{date_value}",
        rf"{marker}[ \t]*[:：]?[ \t]*{rate}{currency}[ \t]*\([ \t]*{date_value}[ \t]*\)",
        rf"{marker}[ \t]*[:：]?[ \t]*{rate}{currency}[ \t]*{reference_label}"
        rf"(?:[ \t]*(?:은|는))?[ \t]*[:：]?[ \t]*{date_value}",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = date(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            except ValueError:
                continue
            return value.strftime("%Y.%m.%d")
    return None


def parse_overseas_text(text: str) -> dict[str, Any] | None:
    # 합계 표기는 벤더별로 "…원" / "총합계 (WON) …" / "합 계 … 0" 등으로 다양.
    total_match = (
        _RE_O_TOTAL_WON.search(text)
        or _RE_O_TOTAL.search(text)
        or _RE_O_TOTAL_CHONG.search(text)
        or _RE_O_TOTAL_LOOSE.search(text)
    )
    vat_match = _RE_O_VAT.search(text)
    if not total_match:
        return None
    app_match = _RE_O_APPNO.search(text) or _RE_O_APPNO_ALT.search(text)
    title_match = _RE_O_TITLE.search(text)
    ccy_match = _RE_O_CCY.search(text)
    if ccy_match:
        currency, foreign_amount = ccy_match.group(1), _to_float(ccy_match.group(2))
    else:
        alt = _RE_O_CCY_ALT.search(text)  # 유미: "(1115.00 EUR)" 금액-통화 순서
        currency = alt.group(2) if alt else ""
        foreign_amount = _to_float(alt.group(1)) if alt else 0.0
    fx_match = _RE_O_FX.search(text) or _RE_O_FX_ALT.search(text)
    fx_rate = _to_float(fx_match.group(1)) if fx_match else 0.0
    if vat_match:
        vat = _to_int(vat_match.group(1))
    else:
        # 유미: "부가세" 라벨 없이 "합 계 공급가액 세액" → 세액(2번째 수)을 VAT로.
        sm = _RE_O_SUM_VAT.search(text)
        vat = _to_int(sm.group(2)) if sm else 0
    line_total = _to_int(total_match.group(1))
    supply_amount = line_total - vat  # 공급가액 = 합계 − 부가세
    remit_fee = _to_int(_RE_O_REMIT.search(text).group(1)) if _RE_O_REMIT.search(text) else 0
    ovs_subtotal_m = _RE_O_OVS_SUBTOTAL.search(text)
    if ovs_subtotal_m:
        # 신세기: 해외비용 소계(첫 '소 계 …원') = 원화비용 + 송금수수료. 당소(대리인)
        # 수수료는 공급가액에서 해외비용 소계를 뺀 잔여 — "OA검토비용" 등 라벨이
        # 착수금/번역비가 아니어도 올바르게 분리된다(1차/2차 OA 오분류 방지).
        ovs_subtotal = _to_int(ovs_subtotal_m.group(1))
        foreign_krw = ovs_subtotal - remit_fee
        agent_fee = supply_amount - ovs_subtotal
    else:
        # 유미 등 '소 계 …원' 표기가 없는 청구서: 착수금 + 번역비(ex-VAT)로 역산.
        agent_fee = (
            _to_int(_RE_O_FEE_START.search(text).group(1)) if _RE_O_FEE_START.search(text) else 0
        ) + (_to_int(_RE_O_FEE_TRANS.search(text).group(1)) if _RE_O_FEE_TRANS.search(text) else 0)
        foreign_krw = supply_amount - agent_fee - remit_fee
    # 외화 표시 금액 = 원화비용 ÷ 환율 로 일관화. 직접 파싱이 안 됐거나(유미 금액-통화
    # 순서) 분담율 적용으로 청구서상 외화(총액)와 원화(분담분)가 어긋나는 경우를 보정.
    source_foreign_amount = foreign_amount
    company_count = None
    if fx_rate > 0 and foreign_krw > 0 and abs(foreign_amount * fx_rate - foreign_krw) > 2:
        foreign_amount = round(foreign_krw / fx_rate, 2)
        # 원문 외화총액과 실제 청구 원화가 어긋나 분담분으로 보정된 경우에만, 명시된
        # 1/N 분담률과 원문 총액의 수치 관계까지 확인해 총액 복원 근거로 저장한다.
        candidate_count = _extract_equal_share_company_count(text)
        if (
            candidate_count
            and source_foreign_amount > 0
            and abs(source_foreign_amount - foreign_amount * candidate_count) <= 0.11
        ):
            company_count = candidate_count
    annuity_year = _extract_annuity_year(text)
    work = next(
        (
            lbl
            for kw, lbl in (
                ("출원유지료", "출원유지료"),
                ("등록유지료", "등록유지료"),
                ("심사청구", "심사청구"),
                ("특허등록", "특허등록"),
                ("등록비용", "특허등록"),
                ("의견제출", "의견제출"),
                ("2차 OA", "2차 OA"),
                ("1차 OA", "1차 OA"),
                ("OA", "OA"),
                ("유지료", "출원유지료"),
                ("출원", "특허출원"),
            )
            if kw in text
        ),
        "해외",
    )
    return {
        "section": SECTION_OVERSEAS,
        "region": "해외",
        "application_no": re.sub(r"[ \t]", "", app_match.group(1)) if app_match else "",
        "registration_no": "",
        "title": title_match.group(1).strip() if title_match else "",
        "annuity_year": annuity_year,
        "supply_amount": supply_amount,
        "vat": vat,
        "gov_fee": 0,
        "line_total": line_total,
        "claim_total": line_total,
        "foreign_currency": currency,
        "foreign_amount": foreign_amount,
        "fx_rate": fx_rate,
        "foreign_cost_krw": foreign_krw,
        "cost_details": {
            "해외비용": foreign_krw,
            "대리인수수료": agent_fee,
            "송금수수료": remit_fee,
            "부가세": vat,
            "합계": line_total,
            "업무": work,
            "균등분담업체수": company_count,
            "외화총액": source_foreign_amount if company_count else None,
            "환율기준일": _extract_fx_reference_date(text),
        },
    }


# ── overseas (한양국제특허) ──────────────────────────────────────────────────────
# 한양 청구서는 금액을 "USD 175.00 / WON 265,767"처럼 외화·원화 쌍으로 나열하고,
# 해외비용 소계(A)·국내비용 소계(B)·"청구금액 (A + B)" 구조를 쓴다. 일반 해외 파서의
# "…원"/"합계" 정규식은 'WON' 표기·'(A+B)' 합계를 못 잡으므로 전용 파서로 처리.
_RE_HY_APPNO = re.compile(r"특허\s*출원\s*\(?\s*([0-9][0-9/.,\- ]*[0-9])\s*\)?")
_RE_HY_TITLE = re.compile(r"제\s*목\s*[:：]\s*(.+)")
_RE_HY_CCY = re.compile(r"\b(USD|EUR|JPY|CNY)\b\s*([\d,]+\.\d+)")
_RE_HY_FX = re.compile(r"([\d,]+\.\d+)\s*[￦₩\\]\s*/\s*(?:USD|EUR|JPY|CNY)")
_RE_HY_SUBTOTAL_A = re.compile(r"소\s*계\s*\(\s*A\s*\)[\s\S]{0,40}?WON\s*([\d,]+)")
_RE_HY_REMIT = re.compile(r"송\s*금\s*수\s*수\s*료[\s\S]{0,30}?WON\s*([\d,]+)")
_RE_HY_AGENT = re.compile(r"대\s*리\s*인\s*수\s*수\s*료[\s\S]{0,30}?WON\s*([\d,]+)")
_RE_HY_VAT = re.compile(r"부\s*가\s*가?\s*치?\s*세[\s\S]{0,30}?WON\s*([\d,]+)")
# extract_document가 굵은 헤더를 글자 중복("청청 구구 금금 액액")으로 뽑으므로 각 글자
# 뒤에 [\s+동일글자]를 허용한다.
_RE_HY_TOTAL = re.compile(r"청[\s청]*구[\s구]*금[\s금]*액[\s액]*[\s\S]{0,40}?WON\s*([\d,]+)")
_RE_HY_WORK = re.compile(r"(\d+\s*차\s*OA|OA대응|의견제출|특허등록|등록유지료|출원유지료|심사청구|특허출원)")


def parse_overseas_hanyang(text: str, filename: str = "") -> dict[str, Any] | None:
    """한양국제특허 해외 청구서(USD/WON 쌍·(A)/(B) 소계·"청구금액 (A + B)")."""
    total_m = _RE_HY_TOTAL.search(text)
    if not total_m:
        return None
    line_total = _to_int(total_m.group(1))
    vat = _to_int(_RE_HY_VAT.search(text).group(1)) if _RE_HY_VAT.search(text) else 0
    supply_amount = line_total - vat  # 공급가액 = 합계 − 부가세
    ovs_sub = _to_int(_RE_HY_SUBTOTAL_A.search(text).group(1)) if _RE_HY_SUBTOTAL_A.search(text) else 0
    remit = _to_int(_RE_HY_REMIT.search(text).group(1)) if _RE_HY_REMIT.search(text) else 0
    foreign_krw = ovs_sub - remit  # 원화비용 = 해외비용 소계(A) − 송금수수료
    agent_fee = supply_amount - ovs_sub  # 대리인수수료 = 공급가액 − 해외비용 소계(A)
    ccy_m = _RE_HY_CCY.search(text)
    currency = ccy_m.group(1) if ccy_m else ""
    foreign_amount = _to_float(ccy_m.group(2)) if ccy_m else 0.0
    fx_m = _RE_HY_FX.search(text)
    fx_rate = _to_float(fx_m.group(1)) if fx_m else 0.0
    source_foreign_amount = foreign_amount
    company_count = None
    if fx_rate > 0 and foreign_krw > 0 and abs(foreign_amount * fx_rate - foreign_krw) > 2:
        foreign_amount = round(foreign_krw / fx_rate, 2)
        candidate_count = _extract_equal_share_company_count(text)
        if (
            candidate_count
            and source_foreign_amount > 0
            and abs(source_foreign_amount - foreign_amount * candidate_count) <= 0.11
        ):
            company_count = candidate_count
    app_m = _RE_HY_APPNO.search(text)
    # 업무: 파일명("1차 OA …")을 우선, 없으면 본문에서 추출.
    work_m = _RE_HY_WORK.search(filename) or _RE_HY_WORK.search(text)
    work = re.sub(r"\s+", " ", work_m.group(1)).strip() if work_m else "OA"
    return {
        "section": SECTION_OVERSEAS,
        "region": "해외",
        "application_no": re.sub(r"[ \t]", "", app_m.group(1)) if app_m else "",
        "registration_no": "",
        "title": (_RE_HY_TITLE.search(text).group(1).strip() if _RE_HY_TITLE.search(text) else ""),
        "annuity_year": None,
        "supply_amount": supply_amount,
        "vat": vat,
        "gov_fee": 0,
        "line_total": line_total,
        "claim_total": line_total,
        "foreign_currency": currency,
        "foreign_amount": foreign_amount,
        "fx_rate": fx_rate,
        "foreign_cost_krw": foreign_krw,
        "cost_details": {
            "해외비용": foreign_krw,
            "대리인수수료": agent_fee,
            "송금수수료": remit,
            "부가세": vat,
            "합계": line_total,
            "업무": work,
            "균등분담업체수": company_count,
            "외화총액": source_foreign_amount if company_count else None,
            "환율기준일": _extract_fx_reference_date(text),
        },
    }


def parse_markpro(text: str) -> dict[str, Any] | None:
    """마크프로 합산 청구서(국내 연차료 / 해외 등록유지료). 한 청구서가 여러 건을
    묶으므로 Debit No.로 run 레벨에서 중복 제거한다. 공급가액 = 총비용합계 − 부가세."""
    total_match = _RE_MP_TOTAL.search(text) or _RE_O_TOTAL.search(text)
    if not total_match:
        return None
    is_overseas = "현지비용" in text
    vat_match = _RE_MP_VAT.search(text)
    vat = _to_int(vat_match.group(1)) if vat_match else 0
    line_total = _to_int(total_match.group(1))
    debit = _RE_DEBIT.search(text)
    count_match = re.search(r"총\s*건\s*수[:\s]*(\d+)", text)
    n = count_match.group(1) if count_match else ""
    return {
        "section": SECTION_OVERSEAS if is_overseas else SECTION_ANNUITY,
        "region": "해외" if is_overseas else "산업",
        "application_no": "",
        "registration_no": "",
        "title": f"{'해외' if is_overseas else '국내'} 연차료 일괄{f' {n}건' if n else ''} (마크프로)",
        "supply_amount": line_total - vat,
        "vat": vat,
        "gov_fee": 0,
        "line_total": line_total,
        "claim_total": line_total,
        "debit_no": debit.group(1) if debit else None,
        "cost_details": {
            "부가세": vat,
            "총비용합계": line_total,
            "debit_no": debit.group(1) if debit else None,
        },
    }


_RE_MP_OV_ROW = re.compile(r"^\s*(\d+)\s+([A-Z]{2})\s+(\S+)\s+(\d+)\s+\d{4}-\d{2}-\d{2}")
_RE_MP_OV_APP = re.compile(r"^\s*P\s+(\S+)\s+\d{4}-\d{2}-\d{2}")
_RE_MP_DOM_ROW = re.compile(r"^\s*(\d+)\s+KR\s+P\s+(\S+)\s+(\S+)\s+\d{4}-\d{2}-\d{2}\s+(\d+)\s+\d+")
_RE_ONLY_NUMS = re.compile(r"^[\d,.\s]+$")
_RE_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 금액줄이 단독이 아니라 분담정보(…50%) 끝에 붙는 경우도 있어, 줄 끝의 숫자열을 잡음.
_RE_TRAIL_NUMS = re.compile(r"(\d[\d,]*(?:\.\d+)?(?:\s+\d[\d,]*(?:\.\d+)?){2,6})\s*$")
_MP_NONTITLE = (
    "%",
    "주식회사 Open ALM",
    "현대자동차",
    "기아",
    "한온",
    "HYUNDAI",
    "MOTOR",
    "차기납부",
    "Credit",
)


def _markpro_title(block: list[str]) -> str:
    """발명의명칭 = 블록에서 한글이 있고 권리인/분담정보/금액줄이 아닌 첫 줄."""
    for raw in block:
        s = raw.strip()
        if not s or _RE_MP_OV_APP.match(s) or _RE_ONLY_NUMS.match(s):
            continue
        if any(m in s for m in _MP_NONTITLE):
            continue
        if re.search(r"[가-힣]", s):
            return s
    return ""


def parse_markpro_items(text: str) -> list[dict[str, Any]]:
    """마크프로 합산 청구서의 **건별 명세표**(국내 연차료 10건 표 / 해외 등록유지료
    16건 표)를 한 건씩 분리한다. 합산본 1줄이 아니라 원본 요약처럼 개별 행으로 나온다.

    부가세 = 당사수수료(건별) × 10%. 국내 합계열=관납료+수수료(공급가액, VAT 별도) →
    합계=공급+VAT. 해외 합계열=현지+수수료+송금+VAT(VAT 포함) → 공급=합계−VAT."""
    debit_m = _RE_DEBIT.search(text)
    debit_no = debit_m.group(1) if debit_m else None
    is_overseas = "현지비용" in text
    rows = text.split("\n")
    row_re = _RE_MP_OV_ROW if is_overseas else _RE_MP_DOM_ROW
    starts = [i for i, line in enumerate(rows) if row_re.match(line)]
    items: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(rows)
        block = rows[start:end]
        m = row_re.match(rows[start])
        amounts: list[str] | None = None
        need = 5 if is_overseas else 3
        for line in block:
            s = line.strip()
            if s.startswith("소계") or s.startswith("소 계") or s.startswith("No."):
                break  # 블록이 표 끝/다음 페이지 머리로 넘어가면 중단(꼬리 숫자 오취득 방지)
            tm = _RE_TRAIL_NUMS.search(line)  # 줄 끝의 숫자열(단독 또는 분담정보 끝에 붙음)
            if tm:
                toks = _RE_NUM_TOKEN.findall(tm.group(1))
                if len(toks) >= need:
                    amounts = toks
                    break
        if not amounts:
            continue
        total_col = _to_int(amounts[-1])
        if is_overseas:
            # 해외 5열 [현지외화, 현지원화, 수수료, 송금, 합계] 또는
            # 6+열 [현지외화, 현지원화, 수수료, 부가세, 송금, 합계] (부가세 컬럼 유무 다름).
            country, annuity = m.group(2), m.group(4)
            foreign_amount = _to_float(amounts[0])
            foreign_krw = _to_int(amounts[1])
            remit_fee = _to_int(amounts[-2])
            if len(amounts) >= 6:
                vat = _to_int(amounts[-3])  # 부가세 컬럼
            else:
                vat = round(_to_int(amounts[2]) * 0.1)  # 5열: 수수료×10%
            supply, line_total = total_col - vat, total_col
            agent_fee = supply - foreign_krw - remit_fee  # 대리인(당사)수수료 = 역산
            currency = "EUR" if country == "DE" else "USD"
            application_no = ""
            for line in block:
                pm = _RE_MP_OV_APP.match(line.strip())
                if pm:
                    application_no = pm.group(1)
                    break
            registration_no = ""  # 등록번호는 매칭 레코드의 등록(공고)번호 사용
            section, region = SECTION_OVERSEAS, "해외"
            items.append(
                {
                    "section": section,
                    "region": region,
                    "application_no": application_no,
                    "registration_no": registration_no,
                    "title": _markpro_title(block[1:]),
                    "annuity_year": annuity,
                    "supply_amount": supply,
                    "vat": vat,
                    "gov_fee": 0,
                    "line_total": line_total,
                    "claim_total": line_total,
                    "foreign_currency": currency,
                    "foreign_amount": foreign_amount,
                    "foreign_cost_krw": foreign_krw,
                    "debit_no": debit_no,
                    "cost_details": {
                        "해외비용": foreign_krw,
                        "대리인수수료": agent_fee,
                        "송금수수료": remit_fee,
                        "부가세": vat,
                        "합계": total_col,
                        "업무": "등록유지",
                        "debit_no": debit_no,
                    },
                }
            )
            continue
        else:
            # 국내 연차표는 [관납료, 수수료, 합계](3열) 또는 [관납료, 수수료, 부가세, 합계](4열).
            # 공급가액 = 관납료 + 수수료, 부가세는 4열이면 표값, 3열이면 수수료×10%.
            appno_raw, regno_raw, annuity = m.group(2), m.group(3), m.group(4)
            gov_fee_amt = _to_int(amounts[0])
            fee = _to_int(amounts[1])
            vat = _to_int(amounts[-2]) if len(amounts) >= 4 else round(fee * 0.1)
            supply = gov_fee_amt + fee
            line_total = supply + vat
            application_no = (
                ("10-" + appno_raw) if re.fullmatch(r"\d{4}-\d{7}", appno_raw) else appno_raw
            )
            registration_no = re.sub(r"-00-00$", "", regno_raw)
            section, region = SECTION_ANNUITY, "산업"
        items.append(
            {
                "section": section,
                "region": region,
                "application_no": application_no,
                "registration_no": registration_no,
                "title": _markpro_title(block[1:]),
                "annuity_year": annuity,
                "supply_amount": supply,
                "vat": vat,
                "gov_fee": 0,
                "line_total": line_total,
                "claim_total": line_total,
                "debit_no": debit_no,
                "cost_details": {
                    "수수료": fee,
                    "부가세": vat,
                    "합계열": total_col,
                    "debit_no": debit_no,
                },
            }
        )
    return items


def reconcile(line: dict[str, Any]) -> bool:
    """Core integrity: 공급가액 + 부가세 == 합계 (and 합계 > 0).

    The per-page 청구금액 regex is unreliable across invoice types, so it is
    kept in cost_details for reference but not used as a hard gate.
    """
    supply = _to_int(line.get("supply_amount"))
    vat = _to_int(line.get("vat"))
    total = _to_int(line.get("line_total"))
    return total > 0 and supply + vat == total


# ── record matching ────────────────────────────────────────────────────────────
def match_record(db: Session, workspace: Workspace, line: dict[str, Any]) -> PatentRecord | None:
    # 1) 출원번호(또는 등록번호)를 정규화해 application_no_norm과 대조 — 기존 동작.
    norm = fd.normalize_app_no(line.get("application_no")) or fd.normalize_app_no(
        line.get("registration_no")
    )
    if norm:
        rec = db.scalars(
            select(PatentRecord).where(
                PatentRecord.workspace_id == workspace.id,
                PatentRecord.application_no_norm == norm,
            )
        ).first()
        if rec:
            return rec
    # 2) 등록번호 컬럼으로 매칭 — 연차료/등록 청구서는 등록번호만 있는 경우가 많아
    #    출원번호 컬럼으로는 못 잡는다(예: 연차료 라인 10-1987015 → 출원 10-2012-…0139227).
    #    저장 형식 차이를 흡수하기 위해 raw 동등 비교(인덱스) 후 정규화 비교로 폴백.
    reg_raw = (line.get("registration_no") or "").strip()
    if not reg_raw:
        return None
    rec = db.scalars(
        select(PatentRecord).where(
            PatentRecord.workspace_id == workspace.id,
            PatentRecord.registration_no == reg_raw,
        )
    ).first()
    if rec:
        return rec
    reg_norm = fd.normalize_app_no(reg_raw)
    if not reg_norm:
        return None
    for candidate in db.scalars(
        select(PatentRecord).where(
            PatentRecord.workspace_id == workspace.id,
            PatentRecord.registration_no.isnot(None),
        )
    ):
        if fd.normalize_app_no(candidate.registration_no) == reg_norm:
            return candidate
    return None


# ── orchestration ──────────────────────────────────────────────────────────────
def parse_file(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    filename: str,
    content: bytes,
    mime_type: str,
    region_hint: str,
) -> list[dict[str, Any]]:
    pages = _pages_from_content(filename, content, mime_type)
    full_text = "\n".join(pages)
    vendor = detect_vendor(full_text)
    lines: list[dict[str, Any]] = []

    # 마크프로: 한 청구서가 여러 건을 묶은 합산본(국내 연차료 / 해외 등록유지료).
    # Debit No. 중복 제거는 run 레벨에서 처리.
    if vendor == "마크프로":
        # 합산 청구서의 건별 명세표를 개별 행으로 분리(원본 요약과 동일).
        items = [it for it in parse_markpro_items(full_text) if reconcile(it)]
        for it in items:
            it["vendor"] = "마크프로"
        # 혼합 묶음: 같은 PDF에 한라 개별 청구서 페이지가 섞인 경우(예: 연차 묶음)
        # → 그 페이지들도 파싱해 병합(출원번호로 중복 제거).
        mp_apps = {
            fd.normalize_app_no(it.get("application_no"))
            for it in items
            if it.get("application_no")
        }
        dom_section = section_from_filename(filename)
        for page in pages:
            dp = parse_domestic_page(page, dom_section)
            if dp is None or not reconcile(dp):
                continue
            norm = fd.normalize_app_no(dp.get("application_no"))
            if norm and norm in mp_apps:
                continue
            dp["vendor"] = "한라"
            items.append(dp)
            if norm:
                mp_apps.add(norm)
        if items:
            return items
        # 명세표 파싱 실패 시 합산 1줄로 폴백.
        parsed = parse_markpro(full_text)
        if parsed is not None and reconcile(parsed):
            parsed["vendor"] = "마크프로"
            lines.append(parsed)
        else:
            lines.extend(
                _llm_lines(
                    db, workspace_id, actor_user_id, full_text, "해외", SECTION_OVERSEAS, "해외"
                )
            )
        return lines

    # 라우팅은 **청구서 종류**(국내/해외 비용 청구서) 기준이 가장 신뢰도 높음.
    # 약한 마커(USD/해외비용)는 국내 묶음 청구서에도 우연히 들어 있어 오라우팅을
    # 유발하므로(예: 신세기/한라 혼합 국내 심사청구 12p 묶음) 강한 신호만 사용.
    compact = full_text.replace(" ", "")
    is_domestic_doc = any(
        k in compact for k in ("국내비용청구서", "국내비용을청구", "특허국내비용")
    )
    # 해외 판정은 **실제 해외비용 신호**(외화·환율·현지비용)와 해외 전문 벤더(신세기/한양)로만
    # 한다. 과거의 "총합계 (WON)"/"유미" 규칙은 유미 **국내** 청구서(총합계 (WON) 표기·관납료
    # footer의 '해외비용' 문구)를 해외로 오라우팅시켜 국내출원 섹션을 통째로 날렸으므로 제거.
    is_overseas_doc = (
        vendor in ("신세기", "한양")
        or any(
            k in compact
            for k in ("해외비용청구서", "해외비용을청구", "특허해외비용", "현지비용", "현지수수료", "외국비용")
        )
        or "환율" in full_text
        or bool(re.search(r"\b(USD|EUR|JPY|CNY|GBP)\b", full_text))
    )
    if not is_domestic_doc and (region_hint == "해외" or is_overseas_doc):
        parsed = (
            parse_overseas_hanyang(full_text, filename)
            if vendor == "한양"
            else parse_overseas_text(full_text)
        )
        if parsed is not None and reconcile(parsed):
            parsed["vendor"] = vendor
            lines.append(parsed)
        else:
            # Unknown/odd overseas format → LLM, but only keep lines that
            # reconcile (guards against the over-extraction seen in testing).
            lines.extend(
                _llm_lines(
                    db, workspace_id, actor_user_id, full_text, "해외", SECTION_OVERSEAS, "해외"
                )
            )
        return lines

    # Domestic: one 청구서 page per patent (한라). Universal 공급가액=청구금액−부가세.
    section = section_from_filename(filename)
    for page in pages:
        parsed = parse_domestic_page(page, section)
        if parsed is not None and reconcile(parsed):
            parsed["vendor"] = vendor
            lines.append(parsed)
    if not lines:
        lines.extend(
            _llm_lines(db, workspace_id, actor_user_id, full_text, "국내", section, "산업")
        )
    return lines


def _llm_lines(
    db, workspace_id, actor_user_id, text, domain_hint, section, region
) -> list[dict[str, Any]]:
    """LLM fallback that accepts only reconciled, de-duplicated lines."""
    try:
        llm = llm_extract.extract_invoice_json(
            db,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            page_text=text,
            domain_hint=domain_hint,
        )
    except Exception:  # noqa: BLE001 - LLM unavailable/misconfigured → no lines
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in llm.get("items", []) or []:
        line = _line_from_llm(item, section, region)
        key = (
            (line.get("application_no") or "")
            + "|"
            + (line.get("registration_no") or "")
            + "|"
            + str(line.get("line_total"))
        )
        if key in seen or not reconcile(line):
            continue
        seen.add(key)
        out.append(line)
    return out


def _line_from_llm(item: dict[str, Any], section: str, region: str) -> dict[str, Any]:
    supply = _to_int(item.get("supply_amount"))
    gov_fee = _to_int(item.get("gov_fee"))
    agent = _to_int(item.get("agent_fee"))
    foreign_cost = _to_int(item.get("foreign_cost_krw"))
    vat = _to_int(item.get("vat"))
    total = _to_int(item.get("line_total"))
    if region == "해외":
        supply_amount = foreign_cost + agent
    else:
        supply_amount = supply + gov_fee
    return {
        "section": section,
        "region": region,
        "application_no": str(item.get("app_no", "")),
        "registration_no": str(item.get("reg_no", "")),
        "title": str(item.get("title", "")),
        "annuity_year": str(item.get("annuity_year", "")),
        "supply_amount": supply_amount or supply,
        "vat": vat,
        "gov_fee": gov_fee,
        "line_total": total or (supply_amount + vat),
        "claim_total": total,
        "foreign_currency": str(item.get("foreign_currency", "")),
        "foreign_amount": _to_float(item.get("foreign_amount")),
        "fx_rate": _to_float(item.get("fx_rate")),
        "foreign_cost_krw": foreign_cost,
        "cost_details": {"llm": True, **item},
    }


def run_cost_ingest(
    db: Session,
    *,
    workspace: Workspace,
    user: User | None,
    files: list[tuple[str, bytes, str]],
    region: str,
    fiscal_period: str | None,
) -> PatentCostRun:
    # 청구서 번호(예: 4-1, 4-2 … 4-28) 자연정렬 → 요약 표기 순서를 원본과 일치시킴
    # (마크프로 등록유지 4-13~28이 자연스레 뒤로 정렬됨).
    def _natkey(fn: str) -> tuple:
        m = re.match(r"\s*(\d+)\s*-\s*(\d+)", fn or "")
        return (0, int(m.group(1)), int(m.group(2)), fn) if m else (1, 0, 0, fn or "")

    files = sorted(files, key=lambda f: _natkey(f[0]))
    run = PatentCostRun(
        id=new_id(),
        workspace_id=workspace.id,
        fiscal_period=fiscal_period,
        status="completed",
        source_filenames={"files": [f[0] for f in files]},
        created_by_id=user.id if user else None,
    )
    db.add(run)
    db.flush()

    warnings: list[str] = []
    industrial_total = 0
    overseas_total = 0
    seq_by_section: dict[str, int] = {}
    seen_debits: set[str] = set()  # 마크프로 합산본은 16개 파일로 중복 도착 → Debit No.로 1회만

    for filename, content, mime_type in files:
        try:
            parsed_lines = parse_file(
                db,
                workspace_id=workspace.id,
                actor_user_id=user.id if user else None,
                filename=filename,
                content=content,
                mime_type=mime_type,
                region_hint=region,
            )
        except Exception as error:  # noqa: BLE001
            warnings.append(f"[추출실패] {filename}: 파싱 실패 ({error})")
            continue
        if not parsed_lines:
            warnings.append(f"[추출실패] {filename}: 청구 항목을 찾지 못함 — 형식 미지원 가능, 수기 확인 필요")
            continue

        # 마크프로 합산 청구서는 여러 파일로 중복 도착(같은 표) → 파일 단위로 1회만
        # 처리(건별 명세는 다 살림). Debit No.가 없는 월도 있어, 없으면 건별 명세의
        # 내용 시그니처(출원번호 집합 + 합계 총액)로 중복 판정.
        mp_lines = [line for line in parsed_lines if line.get("vendor") == "마크프로"]
        if mp_lines:
            batch_debit = next((line.get("debit_no") for line in mp_lines if line.get("debit_no")), None)
            batch_key = batch_debit or (
                "mp:"
                + "|".join(sorted(str(line.get("application_no") or "") for line in mp_lines))
                + f":{sum(_to_int(line.get('line_total')) for line in mp_lines)}"
            )
            if batch_key in seen_debits:
                continue
            seen_debits.add(batch_key)

        # 검사 1: 파일명의 "외 N건"(= N+1건) 대비 실제 추출 건수가 적으면 누락 의심.
        # (예: 국내출원 7건짜리가 1건으로 붕괴된 오라우팅을 즉시 잡아낸다.)
        # 연차료는 제외: 일괄 청구서가 수십 건을 묶지만 대부분 HMC/KMC 100% 부담이라
        # Open ALM 비용 0으로 요약에서 정상 제외되므로 추출 건수가 표기보다 적은 게 정상이다.
        exp_m = re.search(r"외\s*(\d+)\s*건", filename)
        if exp_m and section_from_filename(filename) != SECTION_ANNUITY:
            expected = int(exp_m.group(1)) + 1
            if len(parsed_lines) < expected:
                warnings.append(
                    f"[누락 의심] {filename}: 청구서 표기 {expected}건('외 {exp_m.group(1)}건') 중 "
                    f"{len(parsed_lines)}건만 추출됨 — 누락 확인 필요"
                )

        for line in parsed_lines:
            ident = line.get("application_no") or line.get("registration_no") or line.get("title") or "-"
            ok = reconcile(line)
            if not ok:
                warnings.append(
                    f"[합계불일치] {filename} {ident}: "
                    f"공급가액 {line.get('supply_amount')}+부가세 {line.get('vat')} ≠ 합계 {line.get('line_total')}"
                )
            # 검사 3: 해외 라인은 항목 합(해외비용+대리인+송금+부가세)이 청구 합계와 같아야 한다.
            # 항목별로 독립 파싱되므로, 합계만 맞고 항목이 어긋나는 금액 오파싱을 잡는다.
            if line.get("region") == "해외":
                d = line.get("cost_details") or {}
                comp = (
                    _to_int(d.get("해외비용"))
                    + _to_int(d.get("대리인수수료"))
                    + _to_int(d.get("송금수수료"))
                    + _to_int(d.get("부가세"))
                )
                if comp and comp != _to_int(line.get("line_total")):
                    warnings.append(
                        f"[금액확인] {filename} {ident}: 해외 항목 합 {comp:,} ≠ 청구 합계 "
                        f"{_to_int(line.get('line_total')):,} — 금액 파싱 확인 필요"
                    )
            record = match_record(db, workspace, line)
            # 검사 2: 출원/등록번호가 있는데 특허현황관리에서 매칭이 안 되면 명칭·발명자·
            # 날짜가 비게 된다. 사용자가 빈칸 행을 사전에 인지하도록 경고.
            if record is None and (line.get("application_no") or line.get("registration_no")):
                warnings.append(
                    f"[미매칭] {filename} {ident}: 특허현황관리에서 매칭 건을 찾지 못함 — "
                    f"명칭·발명자·날짜가 비어 있음(출원번호/현황관리 확인 필요)"
                )
            section = line["section"]
            seq_by_section[section] = seq_by_section.get(section, 0) + 1
            cost_line = PatentCostLine(
                id=new_id(),
                workspace_id=workspace.id,
                run_id=run.id,
                record_id=record.id if record else None,
                region=line["region"],
                section=section,
                seq=seq_by_section[section],
                vendor=line.get("vendor"),
                application_no=(record.application_no if record else None)
                or line.get("application_no")
                or None,
                registration_no=(record.registration_no if record else None)
                or line.get("registration_no")
                or None,
                title=(record.invention_title if record else None) or line.get("title") or None,
                inventors=record.inventors if record else None,
                application_date=record.application_date if record else None,
                registration_date=record.field_values.get("registration_date")
                if record and record.field_values
                else None,
                annuity_year=line.get("annuity_year") or None,
                supply_amount=_to_int(line.get("supply_amount")),
                vat=_to_int(line.get("vat")),
                gov_fee=_to_int(line.get("gov_fee")),
                line_total=_to_int(line.get("line_total")),
                foreign_currency=line.get("foreign_currency") or None,
                foreign_amount=line.get("foreign_amount") or None,
                fx_rate=line.get("fx_rate") or None,
                foreign_cost_krw=_to_int(line.get("foreign_cost_krw")) or None,
                reconciled=ok,
                cost_details=line.get("cost_details"),
            )
            db.add(cost_line)
            if line["region"] == "해외":
                overseas_total += _to_int(line.get("line_total"))
            else:
                industrial_total += _to_int(line.get("line_total"))

    run.warnings = {"messages": warnings}
    run.industrial_total = industrial_total
    run.overseas_total = overseas_total
    db.commit()
    db.refresh(run)
    return run
