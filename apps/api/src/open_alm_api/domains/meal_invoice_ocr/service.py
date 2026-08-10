from __future__ import annotations

import base64
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.domains.meal_invoice_ocr.schemas import (
    MealInvoiceExtractResponse,
    MealInvoiceDocument,
    MealInvoiceRow,
    MealInvoiceRowSource,
)

# 업로드 상한(식당 명세표 몇 장 기준). patent_prior_art 와 같은 성격의 보수적 상한.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 100 * 1024 * 1024
# 요청당 파일 수 상한. 작은 파일을 대량으로 올려 (파일 수 × 페이지)만큼 장시간 LLM 호출이
# 발생하는 것을 막는다.
MAX_FILES_PER_REQUEST = 20
# 명세표는 보통 1~2장. 안전하게 문서당 최대 페이지 상한을 둔다.
MAX_PAGES_PER_DOC = 5
# 한 요청의 실제 vision gateway 호출 상한. pass-2가 필요 없는 문서는 기존처럼 최대 40페이지까지
# 처리하고, pass-2를 수행한 경우에만 실제 호출 예산을 추가 차감한다.
MAX_VISION_CALLS_PER_REQUEST = 40
MAX_TOTAL_OCR_PAGES = 40
# 비전 모델이 이미지를 최대 픽셀로 다시 다운샘플하므로, DPI 를 과하게 올리면 오히려 작고 흐린
# 손글씨 마커('중' 등)가 사라진다. 마커 인식이 잘 되던 180 을 유지한다.
RENDER_DPI = 180
# 화면 표시용 페이지 이미지는 더 낮은 DPI 로 렌더해 응답 크기를 줄인다.
PAGE_IMG_DPI = 120
# 렌더 픽셀 상한(폭×높이). 작은 파일이라도 MediaBox 가 거대하면 고정 DPI 로 렌더 시 픽셀 폭발 →
# 워커 OOM 이 가능하다. 목표 DPI 로 계산한 픽셀이 이 상한을 넘으면 스케일을 낮춰(다운스케일) 방어한다.
# (A4 300DPI ≈ 8.7MP 이므로 24MP 는 정상 명세표엔 영향 없고 비정상 MediaBox 만 막는다.)
MAX_RENDER_PIXELS = 24_000_000
# 25행 표도 잘리지 않도록 넉넉히.
MAX_NEW_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 240.0


@dataclass
class _VisionCallBudget:
    """요청 단위 vision gateway 호출 횟수를 실제 호출 직전에 원자적으로 차감한다."""

    limit: int = MAX_VISION_CALLS_PER_REQUEST
    used: int = 0

    @property
    def available(self) -> bool:
        return self.used < self.limit

    def consume(self) -> None:
        if not self.available:
            raise RuntimeError("vision call budget exhausted")
        self.used += 1


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

_PROMPT = (
    "이 거래명세표 이미지의 모든 품목 행을 정확히 추출해. JSON만 출력해라(설명 문장 금지). "
    "★★★ 표의 '첫 줄부터 마지막 줄까지' 한 줄도 빠짐없이 전부 추출하는 것이 가장 중요하다. "
    "손글씨가 흐리거나 겹쳐 있거나 애매해도 절대 행을 통째로 건너뛰지 마라. "
    "값이 불확실하면 물음표(?)를 붙여서라도 반드시 그 행을 포함시켜라. "
    "위에서 아래로 줄을 하나씩 세면서 진행하고, 빈 줄이 아닌 모든 데이터 줄을 담아라. "
    "특히 홍고추·청양고추처럼 비슷한 품목이 연속으로 적힌 줄을 하나로 합치거나 누락하지 마라. "
    "★★★ 원산지 표시 확인: 각 품목 행마다 품목명 오른쪽·옆 여백이나 괄호 안에 손으로 작게 쓴 원산지 표시가 "
    "있는지 한 줄씩 반드시 살펴라. 두 종류이고 둘 다 똑같이 중요하다. "
    "(1) '중' 또는 한자 '中' 한 글자 마커는 그 품목이 '중국산'(수입)이라는 뜻이니 원산지를 '중국산'으로 채운다. "
    "(2) '(미국산)'·'(호주산)'·'(중국산)'처럼 괄호 안이나 품목 옆에 흘려 쓴 '나라 원산지'는 그 나라 원산지다"
    "(중국뿐 아니라 미국·호주·베트남 등 어떤 나라든 똑같이 잡아라). "
    "(3) 나라를 한두 글자로 줄여 괄호에 쓰기도 한다: '(중)'→중국산, '(베트)'→베트남산, '(미)'→미국산, '(호)'→호주산. "
    "이 축약 표시도 반드시 그 나라 원산지로 채워라. "
    "손글씨라 흐리거나 작게 쓰여 있어도 절대 놓치지 말고 그 행의 원산지를 그 나라로 채워라. 표시가 전혀 없으면 국내산. "
    '스키마: {"거래처":"공급자 상호","거래일":"YYYY-MM-DD","합계금액":"숫자",'
    '"공급가액":"부가세 제외 공급가액 소계 숫자(없으면 합계금액과 동일)",'
    '"품목":[{"품명":"","규격":"","수량":"","단위":"","단가":"","금액":"",'
    "\"원산지\":\"기본값은 '국내산'. 명세표 어디든(품명 옆·괄호 안·콤마 뒤·손글씨) '나라 원산지'가 "
    "나오면 그 원산지로 채운다. 나라명은 '~산'으로 정규화(중국→중국산, 미국→미국산). "
    "예: '낙지(중국산/냉동/절단)'→중국산, '…,중국산,스카이푸드'→중국산, '(냉동,중국)'→중국산, '두부(미국)'→미국산. "
    "품목 옆에 흘려 쓴 독립된 '중'(中) 한 글자도 중국산. "
    "단 등급·상태 표기는 원산지가 아니다: '(국비상)'·'국비상'(국내산 비상품)·'(상품)'·'냉동'·'실온' 등은 국내산 유지. "
    "상호·제조사·브랜드(예: 태화·대상·청정원·동원·스카이푸드 등)도 원산지가 아니다. 절대 원산지에 넣지 마라. "
    "원산지에 채울 수 있는 것은 (a)실제 나라 이름(중국·미국·베트남 등)과 (b)위에서 말한 손글씨 '중'(中) 표시 두 가지뿐이다. "
    "이 둘 중 하나면 반드시 채우고(‘중’ 표시는 중국산으로), 그 외 상호·브랜드 등은 국내산으로 둬라. "
    '원산지·브랜드 텍스트는 품명 값에서 빼라(품명은 순수 품목명만). 나라 원산지가 전혀 없으면 국내산.",'
    '"box":[y1,y2]}]}. '
    "box 는 해당 품목 행이 이미지에서 차지하는 세로 구간을 0~1000 으로 정규화한 [상단y, 하단y] 이다"
    "(이미지 맨 위=0, 맨 아래=1000). "
    "품명에 괄호로 된 부가설명(예: '생삼겹(국비상)')이 있으면 괄호와 그 안 내용은 빼고 순수 품목명만 적어(→'생삼겹'). "
    "단, 괄호 안이 '나라 원산지'(예: '두부(미국산)'·'낙지(중국산)')면 절대 그냥 버리지 말고 그 나라를 원산지 칸으로 "
    "옮긴 뒤 품명에는 괄호 앞 품목명만 남겨라(→품명 '두부'·'낙지', 원산지 '미국산'·'중국산'). "
    "★★ 괄호 안 내용은 브랜드·보관(실온/냉동)·용량(5kg)·포장이지 '품목'이 아니다(나라 원산지는 위 예외로 원산지 칸으로 옮긴다). 품목은 언제나 '괄호 앞' 텍스트다. "
    "절대 괄호 안 글자로 품목명을 만들지 마라. 예: '쇠고기맛냉면육수(면사랑/실온/5kg)EA'→'냉면육수'(괄호 앞이 품목, "
    "'면사랑'은 브랜드지 품목이 아님), '동치미맛냉면육수(면사랑/실온/5kg)'→'냉면육수'. "
    "그리고 '동치미맛·쇠고기맛·매운맛' 같은 '~맛' 표현과 맛 수식어도 빼고 재료 이름만 남겨라. "
    "라면·면류(컵라면·봉지면·사발면 등)는 제품 핵심 이름만 남겨라. "
    "컵/컵라면/큰사발면/사발면/봉지/개입/입/용량(g)·제조사(농심·오뚜기·팔도 등)·소/대 같은 수식어는 모두 빼라. "
    "예: '신라면컵라면(6입) 농심'→'신라면', '진라면컵(소)'→'진라면', '오징어짬뽕컵 6입'→'오징어짬뽕', "
    "'사리곰탕 큰사발면(111g/EA)'→'사리곰탕'. "
    "그 외 품목명도 앞에 붙은 영문·한글 브랜드(be chef·오쉐프·동원·청정원·내츄럴스파이스 등)와 홍보 수식어"
    "(햇살담은·진하고구수한·진하고·고소한·오래오래 등), 뒤에 붙은 등급·상품 수식어(골드·실속·특선·프리미엄 등)를 "
    "모두 빼고 '상품명'이 아니라 '가장 일반적인 재료/품목 단어'만 남겨라. "
    "예: '양조식초'→'식초', 'be chef. 이온물엿(9Kg/동원홈푸드)EA'→'이온물엿', "
    "'햇살담은 진간장골드13L'→'진간장', '[비축]진하고구수한된장(참고율/14KG)BOX'→'된장', '오쉐프생생얼음'→'얼음'. "
    "★★ 브랜드·상품라인 이름이 품목 '앞'에 오고 실제 식재료가 '뒤'에 오는 경우가 많다. 이때 브랜드만 빼고 "
    "뒤의 '실제 식재료 이름'을 반드시 남겨라. 절대 브랜드만 남기고 진짜 품목을 버리지 마라. "
    "예: '내츄럴스파이스 월계수입(90g/EA)'→'월계수잎'(내츄럴스파이스=브랜드, 월계수잎=실제 품목, '입'은 '잎'의 오독). "
    "무엇이 실제 식재료인지 상식으로 판단하라(향신료 브랜드명이 아니라 '월계수잎'이 품목이다). "
    "품목명 끝이나 중간의 단위·용량·포장 표기(EA·BOX·KG·L·ML·g·13L·5kg 등)는 모두 빼라. "
    "명세표에 '단위' 칸(Box·ea·PK·Kg·통·박스 등)이 따로 있으면 그 값을 '단위'에 넣고 '수량'엔 숫자만 넣어라. "
    "전용 '단위' 칸이 없고 '규격'(스펙) 칸에 '낱·박스·박·봉·봉지·통·개·팩·포·판·병·ea·kg' 같은 단위·포장 표기를 "
    "적어둔 명세표가 있다. 이때는 그 표기를 '단위'에 넣어라('규격'엔 두지 마라). 다만 규격 칸이 크기·호수·등급 등 "
    "진짜 규격이면(예: '특호'·'1호'·'대') '규격'에 두고 '단위'는 빈 문자열로 둬라. "
    "단위 칸이 없고 손글씨 수량에 단위가 붙어 있으면(예: '30K') 그대로 '수량'에 두고 '단위'는 빈 문자열로 둬라. "
    "★ 단위는 반드시 다음 10개 중 하나로만 적어라: ea, k, 박스, pk, pac, 통, 10k, 판, 단, 병 (kg 은 k 로). "
    "손글씨가 이 중 무엇에 가장 가까운지 판단해 그 값으로 적고, 목록에 없거나 애매하면 억지로 지어내지 말고 "
    "'단위'를 빈 문자열로 둬라(예: 'c'·'동' 같은 목록 밖 표기를 새로 만들지 마라). "
    "손글씨는 최대한 판독하고, 판독이 불확실하면 값 끝에 물음표(?)를 붙여. 모든 숫자는 쉼표를 제거해."
)

# 재판독(pass-2) 프롬프트. 전체 페이지를 한 번에 넣으면 비전 모델이 이미지를 최대 픽셀로 다운샘플하면서
# 품목명 옆 원산지('(미국산)' 등)와 수량 옆 단위('박스'·'통' 등) 같은 작은 손글씨가 뭉개지거나 통째로
# 누락된다. 데이터 행 band 만 잘라 확대해 다시 넣으면 같은 모델이 훨씬 안정적으로 읽는다(실효 해상도↑).
# 원산지는 오탐 방지를 위해 '국내산 기본 + 첫 글자 확실할 때만 나라'로, 단위는 있는 그대로 읽게 지시한다.
_RESCAN_PROMPT = (
    "이 이미지는 거래명세표의 품목 데이터 행들을 확대한 것이다. 위에서 아래로 각 행의 품명·원산지·단위를 "
    "순서대로 읽어라. "
    "[원산지] 대부분 '국내산'이다. 괄호 안이나 옆에 '국내산'이라 적혀 있거나 아무 원산지 표기가 없으면 반드시 "
    "'국내산'으로 둬라. 괄호 안 글자를 한 글자씩 정확히 판독하되, 첫 글자가 '미'일 때만 미국산, '중'이거나 한자 "
    "'中'일 때만 중국산, '호'면 호주산, '베'나 '베트'면 베트남산처럼 '국내산이 아님'이 확실할 때만 그 나라로 바꿔라. "
    "축약 표기도 그대로 인정한다: '(중)'→중국산, '(베트)'→베트남산, '(미)'→미국산, '(호)'→호주산. 애매하면 국내산. "
    "'(국내산)'을 중국산·미국산으로 함부로 바꾸지 마라. 품목 옆 흘려 쓴 '중'(中) 한 글자만 있으면 중국산이다. "
    "[단위] 수량 숫자 바로 옆(또는 규격 칸)에 손으로 쓴 '단위'를 읽어라. 단위는 반드시 다음 목록 중 하나로만 "
    "적어라: ea, k, 박스, pk, pac, 통, 10k, 판, 단, 병. 손글씨를 이 목록 중 '가장 비슷한' 것으로 판독하고, "
    "목록에 없는 다른 단어(송이·봉·포 등)를 새로 만들지 마라. kg 은 k 로 적는다. 숫자는 단위가 아니다. "
    "단위 표기가 정말 안 보이면 빈 문자열로 둔다(억지로 지어내지 마라). "
    'JSON만 출력: {"행":[{"품명":"","원산지":"","단위":""}]}'
)

# band 위아래 여백(페이지 높이 비율). box 경계가 살짝 잘려도 글자가 포함되도록.
_BAND_PAD_FRAC = 0.02
# 행 수가 어긋나 위치 정렬을 못 믿을 때, 재판독 행을 원본 행에 품명 유사도로 짝지을 하한.
#
# 이 경로에는 위치 정렬이라는 뒷받침이 없어 유사도가 유일한 근거다. 게다가 행 수가 다르다는 것은
# 짝이 없는 원본 행이 존재한다는 뜻이라, 그리디 매칭이 남은 재판독 행을 엉뚱한 행에 억지로 붙인다.
# 그런데 여기서 옮기는 값은 원산지(법적으로 민감)와 단위(수량의 의미를 바꿈)다.
#
# 그래서 모듈이 이미 '같은 품목'의 기준으로 쓰는 0.72(_VOCAB_MATCH_MIN·_LEARN_FUZZY_MIN·
# _NAME_SUGGEST_MIN)와 같은 값으로 맞춘다. 예전 0.55 는 서로 다른 실재 품목을 짝지었다.
# 손글씨 사진 실측(pass-1 14행 vs 재판독 10행):
#   유지 : 부추 1.00, 정채 1.00, 방울토마토 1.00, 청양고추↔청양추 0.889
#   배제 : 깐감자↔깐강마늘 0.667, 양파↔양상추 0.615  ← 서로 다른 품목. 0.55 에서는 통과했다
#   이미 배제되던 쓰레기 판독 : (추) 0.500, 쪽 0.400, <1홍기>(베트) 0.353
# 이식을 놓치는 것보다 엉뚱한 행에 이식하는 것이 나쁘므로 재현율보다 정확도를 택한다.
_RESCAN_NAME_MIN = 0.72
# 확대 재판독 품명을 검수 후보로 제시하려면, 대장(실제 품목)과 이 이상 유사해야 한다.
_NAME_SUGGEST_MIN = 0.72
# 위치(index) 정렬 쌍에서 원산지·단위를 옮기려면, 1차 품명과 재판독 품명이 이 이상 비슷해야 한다.
# 개수만 우연히 같고 행이 어긋난 경우(모델이 행을 병합·분리) 서로 다른 품목에 원산지·단위가 이식되는
# 것을 막는 하한이다. 이 경로는 '행 수가 같다 + 위치가 같다'는 독립 근거가 있어 유사도 요구를 낮게
# 둘 수 있다. 짧은 한글 토큰끼리 우연히 겹쳐 0.4대가 나오는 오탐만 걷어내는 목적이다.
_RESCAN_ALIGN_MIN = 0.5
# 학습 자동적용 퍼지 매칭 하한(자모 유사도). OCR 오독 변형('고칫갸루'↔'고찻가루')은 잡고, 다른
# 품목('양파'↔'양상추'≈0.62)은 배제하도록 0.72 로 둔다.
_LEARN_FUZZY_MIN = 0.72
_RESCAN_UNIT_OPTIONS = frozenset({"ea", "k", "박스", "pk", "pac", "통", "10k", "판", "단", "병"})
_RESCAN_UNIT_ALIASES = {
    "box": "박스",
    "박": "박스",
    "상자": "박스",
    "pack": "pac",
    "팩": "pac",
}
# 일부 명세표는 전용 '단위' 칸 없이 '규격' 칸에 단위성 표기(낱·박스·봉 등)를 손으로 적는다. 규격 값이
# 아래 '알려진 단위' 하나와 정확히 일치하면 단위로 승격한다(크기·호수·등급 등 진짜 규격은 승격하지 않음).
# 정규화 규칙은 단위/수량과 동일하다: .strip().lower().replace("kg","k"). 따라서 영문은 소문자, kg 는 k 로 둔다.
_KNOWN_UNIT_TOKENS = frozenset(
    {
        # 한글 개수·포장 단위
        "낱",
        "낱개",
        "개",
        "봉",
        "봉지",
        "포",
        "포대",
        "통",
        "박스",
        "박",
        "상자",
        "케이스",
        "팩",
        "판",
        "짝",
        "병",
        "캔",
        "말",
        "되",
        "근",
        "각",
        "마리",
        "손",
        "축",
        "첩",
        "매",
        "장",
        "세트",
        "자루",
        "단",
        "묶음",
        "줄",
        "쪽",
        # 영문·무게·부피 단위(소문자, kg→k 정규화 후 형태)
        "ea",
        "box",
        "pk",
        "pack",
        "can",
        "k",
        "g",
        "l",
        "ml",
        "cc",
    }
)

# 대문자 L 한 글자는 리터 단위뿐 아니라 크기 등급(Large)으로도 널리 쓰인다. 규격 칸에서는 문맥 없이
# 단위로 확정할 수 없으므로 원문을 보존한다. 명시적 단위 칸과 소문자 l 은 기존 단위 정규화를 따른다.
_AMBIGUOUS_SPEC_UNIT_TOKENS = frozenset({"L"})


def _norm_token(value: object) -> str:
    """수량/단위 공통 정규화: 앞뒤 공백 제거·소문자·'kg'→'k'. 비교·승격·분리에 쓴다."""
    return str(value or "").strip().lower().replace("kg", "k")


def _promotable_spec_unit(value: object) -> str:
    raw = str(value or "").strip()
    if raw in _AMBIGUOUS_SPEC_UNIT_TOKENS:
        return ""
    normalized = _norm_token(raw)
    return normalized if normalized in _KNOWN_UNIT_TOKENS else ""


# 정규화된 수량에서 (숫자부, 단위부)를 분리. "24 낱"·"24낱"·"24" 모두 처리한다.
# 숫자부는 반드시 숫자로 시작하고 선택적 선행 부호와 후행 불확실 표시(?)만 허용한다. 나머지 부분이
# 실제 단위로 보이려면 문자도 포함해야 한다. 분수·범위·자유 텍스트를 단위로 오인해 버리지 않기 위함이다.
_QTY_SPLIT_RE = re.compile(r"^\s*([+-]?\d[\d.,]*\??)\s*(.*)$")


def split_qty(value: object) -> tuple[str, str]:
    """수량 문자열을 (숫자, 단위)로 분리한다(정규화 후). 공백 형식과 붙은 형식 모두 지원."""
    s = _norm_token(value)
    m = _QTY_SPLIT_RE.match(s)
    if not m:
        return s, ""
    num = m.group(1).strip()
    unit = m.group(2).strip()
    if unit and ("?" in unit or not any(char.isalpha() for char in unit)):
        return s, ""
    return num, unit


def _quantity_already_ends_with_unit(quantity: str, unit: str) -> bool:
    """불확실 표시 앞에 선택 단위가 독립된 후행 토큰으로 이미 있는지 확인한다."""
    if not quantity or not unit:
        return False
    candidate = quantity[:-1].rstrip() if quantity.endswith("?") else quantity.rstrip()
    if not candidate.endswith(unit):
        return False
    unit_start = len(candidate) - len(unit)
    if unit_start == 0:
        return True
    preceding = candidate[unit_start - 1]
    unit_first = unit[0]
    # 같은 문자권의 더 긴 단어 끝과 우연히 겹친 suffix는 제외한다("pack"의 k, "낱개"의 개 등).
    # 숫자·구두점이나 다른 문자권 뒤의 같은 suffix는 명시 단위 칸과 일치하는 이미 붙은 단위다.
    return not (
        unit_first.isalpha() and preceding.isalpha() and unit_first.isascii() == preceding.isascii()
    )


# 품명에서 괄호/대괄호 부가설명(예: "생삼겹(국비상)"·"[비축]된장" → "생삼겹"·"된장") 제거. 반각·전각 모두.
_PAREN_RE = re.compile(r"[\(（\[【][^\)）\]】]*[\)）\]】]")
# 품명 끝에 붙은 단위·용량 표기(예: "진간장골드13L", "…EA", "…5KG", "…BOX") 제거용.
_TRAIL_UNIT_RE = re.compile(r"[\s/·,]*\d*\.?\d*\s*(?:EA|BOX|PK|KG|ML|L|G)\s*$", re.IGNORECASE)
# 품명 앞에 붙은 영문 브랜드(예: "be chef. 이온물엿" → "이온물엿") 제거. 한글이 시작되기 전까지의 라틴 구간만.
_LATIN_BRAND_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 .&'\-]*?[.\s]+(?=[가-힣])")
# 품명 끝에 붙은 등급·상품 수식어(예: "진간장골드" → "진간장") 제거.
_GRADE_SUFFIX_RE = re.compile(
    r"(골드플러스|골드|실속|특선|프리미엄|오리지날|오리지널|플러스|스페셜)$"
)

# 품명 텍스트에 명시된 원산지(예: "…,중국산,스카이푸드" 또는 "(냉동,중국)"). '국비상'은 국내산이므로 제외.
# 나라 어간(산 없이)만 써도 인식하되, '중국식'·'일본식' 같은 단어 오탐을 막으려고 앞뒤가
# 한글이 아닐 때(구분자·괄호·공백·경계)만 매칭한다. 뒤의 '산'은 선택.
_ORIGIN_STEMS = [
    "국내",
    "중국",
    "미국",
    "베트남",
    "태국",
    "인도",
    "러시아",
    "우크라이나",
    "이탈리아",
    "호주",
    "일본",
    "페루",
    "프랑스",
    "칠레",
    "브라질",
    "필리핀",
    "폴란드",
    "스페인",
    "노르웨이",
    "벨기에",
    "영국",
    "캐나다",
    "터키",
    "미얀마",
    "수입",
    "외국",
]
_ORIGIN_ALT = "|".join(sorted(_ORIGIN_STEMS, key=len, reverse=True))
# 명시적 '~산'(예: '중국산낙지')은 뒤에 한글이 붙어도 원산지로 인정한다. 앞 경계만 요구.
_ORIGIN_EXPLICIT_RE = re.compile(r"(?<![가-힣])(" + _ORIGIN_ALT + r")산")
# '산' 없는 어간('중국')은 '중국식'·'일본식' 같은 오탐을 막으려 앞뒤 비한글 경계에서만 인식.
_ORIGIN_BARE_RE = re.compile(r"(?<![가-힣])(" + _ORIGIN_ALT + r")(?![가-힣])")

# 손글씨 원산지 축약 마커 → 나라 원산지. 명세표에 '(중)'·'(베트)'처럼 나라를 줄여 쓴다.
# 나라 전체 이름은 _ORIGIN_STEMS 로 잡히므로, 여기서는 축약형만 보강한다.
_ORIGIN_ABBR = {
    "중": "중국산",
    "중국": "중국산",
    "베트": "베트남산",
    "베트남": "베트남산",
    "미": "미국산",
    "미국": "미국산",
    "호": "호주산",
    "호주": "호주산",
}
# 품명 옆/안 괄호에 줄여 쓴 원산지 마커(예: '고춧가루(중)'·'디포리(베트)'). 괄호로 감싸여 있어
# 오탐 위험이 낮으므로 한 글자 축약('(중)'·'(미)')도 인정한다. 긴 표기 우선(중국 > 중).
_PAREN_ORIGIN_RE = re.compile(r"[（(]\s*(중국|베트남|미국|호주|중|베트|미|호)\s*[）)]")


def _find_origin_stems(text: str) -> list[str]:
    """텍스트에서 원산지 어간 목록을 뽑는다. 명시 '~산'을 먼저 보고, 그다음 경계 어간을 본다."""
    text = str(text or "")
    return _ORIGIN_EXPLICIT_RE.findall(text) + _ORIGIN_BARE_RE.findall(text)


def _strip_origin_text(text: str) -> str:
    """품명에서 원산지 표기('~산' 및 경계 어간)를 제거한다."""
    return _ORIGIN_BARE_RE.sub("", _ORIGIN_EXPLICIT_RE.sub("", str(text or "")))


def _confirmed_origin(raw: object) -> str:
    """값에서 '근거가 있는' 원산지만 돌려준다. 근거가 없으면 빈 문자열(기본값을 만들지 않는다).

    ``_normalize_origin`` 과 달리 목록 밖 값(상호·브랜드·빈값)을 '국내산'으로 강제하지 않는다.
    호출측이 다른 칸(규격 등)을 이어서 볼 수 있게 '판단 불가'와 '국내산 확인'을 구분한다.
    명시적 '국내산'은 근거 있는 값이므로 빈 문자열이 아니라 '국내산'으로 돌려준다.
    """
    text = str(raw or "").strip()
    # 손글씨 '중'(中) 마커: 나라명 목록엔 없지만 중국산으로 인정(품목 옆 흘려 쓴 표시).
    if text in {"중", "中", "중국"}:
        return "중국산"
    # 축약 마커('베트'·'미'·'호' 등)를 나라 원산지로 인정한다('(베트)'→베트남산).
    if text in _ORIGIN_ABBR:
        return _ORIGIN_ABBR[text]
    return _printed_country_origin(text)


def _printed_country_origin(raw: object) -> str:
    """텍스트에 인쇄된 '나라 이름'만 원산지로 읽는다. 축약·한 글자 마커는 인정하지 않는다.

    ``_confirmed_origin`` 과 달리 '중'·'中'·'(미)' 같은 축약 마커를 보지 않는다. 이 마커들은 농산물
    명세표의 크기 등급('감자 중'·'고구마 中'·'비마늘(중)')과 구분할 수 없어서, 문서 원문을 그대로
    읽는 경로(재판독 품명 등)에서는 국내산 농산물을 중국산으로 뒤집는다.
    비국내산 어간이 있으면 그것을 우선한다(칸에 '국내산/중국산'이 함께 오는 경우).
    """
    found = _find_origin_stems(str(raw or ""))
    if not found:
        return ""
    stem = next((f for f in found if f != "국내"), found[0])
    return stem if stem.endswith("산") else f"{stem}산"


# 규격 칸을 구분자로 조각내는 패턴. 조각 '전체'가 나라 표기일 때만 원산지로 인정한다(아래 참조).
_SPEC_SEGMENT_RE = re.compile(r"[,，/·|()（）\[\]【】]+")
# 조각 전체가 나라 표기인지 검사. '중국'·'중국산' 은 인정, '중국산고춧가루사용' 은 불인정.
_SPEC_ORIGIN_TOKEN_RE = re.compile(r"^(" + _ORIGIN_ALT + r")산?$")
# 단어에 붙은 괄호 주석('고춧가루(중국산)'·'대두(미국산)/밀(호주산)'). 원료명 뒤에 그 원료의
# 원산지를 적은 표기라 품목 원산지가 아니다. 규격 전체가 괄호인 관측값('(냉동,중국)')과 달리
# 앞에 단어가 붙어 있는 것으로 구분한다.
_SPEC_ATTACHED_PAREN_RE = re.compile(r"(?<=[0-9A-Za-z가-힣])\s*[(（\[【][^)）\]】]*[)）\]】]")


def _origin_from_spec(value: object) -> str:
    """규격 칸에서 원산지를 읽는다. 구분자로 나눈 조각 '전체'가 나라 표기일 때만 인정한다.

    규격 칸에는 크기 등급·호수·용량·브랜드·보관이 섞여 온다. 그래서 품명 옆 손글씨 마커용 규칙을
    그대로 쓰면 안 된다.
    - 축약 마커(_ORIGIN_ABBR: '중'→중국산, '미'→미국산, '호'→호주산)는 규격의 크기 등급과 구분할 수
      없다. 농산물 명세표의 '대/중/소'와 '특호/1호'가 흔해서, '중'을 중국산으로 읽으면 국내산 농산물을
      중국산으로 오표기한다. 축약은 괄호로 감싸인 품명 옆 표기에서만 쓰고 여기서는 인정하지 않는다.
    - 문장에 섞인 원료 원산지 문구('중국산 고춧가루 사용')는 그 품목의 원산지가 아니다. 가공식품
      규격에 흔하므로 조각 전체가 나라 표기일 것을 요구해 걸러낸다. 같은 문구를 괄호로 적은 형태
      ('고춧가루(중국산)'·'대두(미국산)/밀(호주산)')는 조각 전체가 나라 표기가 되므로, 단어에 붙은
      괄호 주석을 먼저 떼어 낸다(_SPEC_ATTACHED_PAREN_RE).

    여러 나라 표기가 오면 비국내산을 우선한다('국내산/중국산'·'중국,국내'). 규격 칸 작성 순서 때문에
    수입 원산지가 국내산으로 뒤집히지 않게, 모듈의 다른 원산지 판독(_confirmed_origin)과 같은 규칙을
    쓴다.

    원산지는 틀리면 곤란한 항목이라 재현율보다 정확도를 택한다. 실제 관측된 규격
    ('중국산,스카이푸드', '냉동,중국')은 이 규칙으로 정상 인식된다.
    """
    text = _SPEC_ATTACHED_PAREN_RE.sub("", str(value or ""))
    stems: list[str] = []
    for segment in _SPEC_SEGMENT_RE.split(text):
        match = _SPEC_ORIGIN_TOKEN_RE.match(re.sub(r"\s+", "", segment))
        if match:
            stems.append(match.group(1))
    if not stems:
        return ""
    stem = next((s for s in stems if s != "국내"), stems[0])
    if stem == "국내":
        return "국내산"
    return stem if stem.endswith("산") else f"{stem}산"


def _foreign_origin(raw: object) -> str:
    """비국내산 원산지만 돌려준다. 국내산이거나 근거가 없으면 빈 문자열.

    모델이 채우는 '원산지' 칸의 '국내산'은 근거가 아니라 기본값이다(프롬프트가 "표시가 없으면
    국내산", "애매하면 국내산"으로 지시한다). 이 값을 근거로 취급하면 뒤에 있는 실제 문서 텍스트
    (품명 원문·규격)에서 나라를 찾는 경로가 전부 막힌다. 그래서 판단 필드의 국내산은 '미확인'으로
    보고 넘기고, 문서에 인쇄된 나라 표기만 근거로 쓴다.
    """
    origin = _confirmed_origin(raw)
    return "" if origin == "국내산" else origin


def _normalize_origin(raw: str) -> str:
    """LLM 이 준 원산지 값을 알려진 나라 목록으로 검증한다.

    나라 이름(중국·미국 등)이면 '~산'으로 정규화해 돌려주고, 목록에 없는 값(상호·브랜드·빈값 등)은
    모델이 지어낸 것으로 보고 무조건 '국내산'으로 강제한다.
    손글씨 마커 '중'(中) 한 글자만 온 경우는 중국산으로 인정한다.
    """
    return _confirmed_origin(raw) or "국내산"


def _extract_origin(name: str) -> tuple[str, str]:
    """품명 텍스트에서 명시적 원산지(나라)를 뽑고, 그 단어를 뺀 품명을 함께 돌려준다.

    반환: (원산지 또는 "", 원산지 제거된 품명). 비국내산이 있으면 그것을 우선한다.
    '중국'처럼 '산'이 없어도 '중국산'으로 정규화한다.
    """
    text = str(name or "")
    # 모델이 원산지 마커를 품명에 붙여 보내는 경우도 잡는다.
    # 한자 '中' 은 어디 있든 중국산 마커로 본다(품명엔 中을 쓰지 않으므로 오탐 없음).
    if "中" in text:
        return ("중국산", text.replace("中", "").strip())
    # 한글 '중' 은 '중멸치'·'중란'처럼 단어 일부일 수 있으니, 공백으로 분리된 독립 토큰일 때만 마커로 인정.
    if re.search(r"(?:^|\s)중(?=\s|$)", text):
        return ("중국산", re.sub(r"(?:^|\s)중(?=\s|$)", " ", text).strip())
    # 괄호 안 축약 원산지 마커('고춧가루(중)'→중국산, '디포리(베트)'→베트남산).
    # _clean_item_name 이 괄호를 통째로 지우기 전에 여기서 원산지로 옮긴다.
    paren = _PAREN_ORIGIN_RE.search(text)
    if paren:
        return (_ORIGIN_ABBR[paren.group(1)], _PAREN_ORIGIN_RE.sub("", text).strip())
    found = _find_origin_stems(text)
    if not found:
        return ("", text)
    stem = next((f for f in found if f != "국내"), found[0])
    origin = stem if stem.endswith("산") else f"{stem}산"
    return (origin, _strip_origin_text(text))


def _clean_item_name(name: str) -> str:
    cleaned = _PAREN_RE.sub("", str(name or ""))
    # '제품명,원산지,브랜드'처럼 콤마로 나뉘면 첫 조각(제품명)만 남긴다.
    if re.search(r"[,，]", cleaned):
        first = re.split(r"[,，]", cleaned)[0]
        if first.strip():
            cleaned = first
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 앞에 붙은 영문 브랜드 구간 제거(예: "be chef. 이온물엿" → "이온물엿").
    cleaned = _LATIN_BRAND_PREFIX_RE.sub("", cleaned).strip()
    # 끝에 남은 라틴 단위/용량 토큰과 등급어를 반복 제거(예: "…13L", "…KG", "…EA", "…골드").
    prev = ""
    while prev != cleaned:
        prev = cleaned
        cleaned = _TRAIL_UNIT_RE.sub("", cleaned).strip()
        cleaned = _GRADE_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned


@dataclass(frozen=True)
class MealInvoiceUpload:
    filename: str
    content_type: str
    content: bytes


def _data_url(content: bytes, *, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"


# 업로드 콘텐츠 형식 검증(확장자·선언 MIME 을 믿지 않고 실제 매직바이트로 판별). 인증 사용자가
# 임의 바이트를 문서 파서(PyMuPDF)에 투입하지 못하게 하는 서버측 allowlist.
_PDF_MAGIC = b"%PDF"
_IMAGE_MAGICS = (
    b"\x89PNG\r\n\x1a\n",  # png
    b"\xff\xd8\xff",  # jpeg
    b"BM",  # bmp
    b"II*\x00",  # tiff (little-endian)
    b"MM\x00*",  # tiff (big-endian)
)


def _is_pdf(content: bytes) -> bool:
    return content[:8].startswith(_PDF_MAGIC)


def _is_image(content: bytes) -> bool:
    head = content[:16]
    if any(head.startswith(magic) for magic in _IMAGE_MAGICS):
        return True
    # WEBP: 'RIFF'....'WEBP'
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def is_supported_invoice_upload(content: bytes) -> bool:
    """추출 업로드가 실제 PDF 또는 지원 이미지인지 매직바이트로 확인한다."""
    return _is_pdf(content) or _is_image(content)


def _detect_filetype(content: bytes) -> str:
    """실제 콘텐츠(매직바이트)로 fitz 파서 타입을 판별한다. 미지원이면 빈 문자열.

    업로드 허용 판정(is_supported_invoice_upload)과 동일한 근거(콘텐츠)로 파서 타입을 정한다.
    파일명 suffix 에 의존하면 확장자가 없거나 틀린 정상 PDF/이미지가 허용은 통과하고 렌더만
    실패해 200 + 빈 결과가 되므로, suffix 가 아니라 매직바이트를 파서에 넘긴다.
    """
    if _is_pdf(content):
        return "pdf"
    head = content[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return "tif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return ""


def _open_document(upload: MealInvoiceUpload):
    """업로드 파일을 fitz 문서로 연다(PDF/이미지 공통). 호출측이 close 한다."""
    import fitz  # PyMuPDF. ppt_generator 가 이미 의존하는 배포된 패키지.

    # 파서 타입은 파일명이 아니라 감지한 매직바이트로 정한다(허용 판정과 동일 근거).
    filetype = _detect_filetype(upload.content)
    if not filetype:
        # 검증을 통과한 업로드만 도달하므로 이론상 없음. 방어적으로 suffix 폴백.
        suffix = Path(upload.filename or "").suffix.lower()
        filetype = suffix.lstrip(".") if suffix in _IMAGE_SUFFIXES else "pdf"
        if filetype == "jpeg":
            filetype = "jpg"
    return fitz.open(stream=upload.content, filetype=filetype)


def _clamped_scale(page, dpi: int) -> float:
    """목표 DPI 스케일을 렌더 픽셀 상한(MAX_RENDER_PIXELS) 안으로 낮춰 돌려준다.

    거대한 MediaBox(작은 파일이라도)로 인한 픽셀 폭발/워커 OOM 을 막는 방어선이다.
    """
    scale = dpi / 72.0
    rect = page.rect
    pixels = (rect.width * scale) * (rect.height * scale)
    if pixels > MAX_RENDER_PIXELS > 0:
        scale *= (MAX_RENDER_PIXELS / pixels) ** 0.5
    return scale


def _render_page_png(page) -> bytes:
    import fitz

    scale = _clamped_scale(page, RENDER_DPI)
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")


def _render_page_display_data_url(page) -> str:
    """화면 표시용 페이지 전체 이미지(저DPI PNG data URL)."""
    import fitz

    scale = _clamped_scale(page, PAGE_IMG_DPI)
    png = page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
    return _data_url(png)


def _call_vision(
    png: bytes,
    *,
    db: Session,
    workspace_id: str,
    actor_user_id: str | None,
    fewshot: str = "",
    prompt: str | None = None,
    workload_id: str | None = None,
) -> str:
    """플랫폼 LLM gateway 로 비전 OCR 을 호출한다(정책·토큰 예산·llm_call 감사 적용).

    관리자가 선택한 local Vision 모델을 쓰는 local_only task라 외부 egress는 없다. 원문 vLLM
    엔드포인트를 직접 부르지 않고 gateway 를 경유해 플랫폼 계약(감사/예산)을 지킨다.

    prompt: 기본은 전체 추출 프롬프트(_PROMPT). 원산지 재판독(pass-2) 같은 다른 목적의 호출은
    자체 프롬프트를 넘긴다.
    """
    from open_alm_api.core.llm import LlmTaskContext
    from open_alm_api.domains.ai.gateway import LlmWorkloadContext, execute_llm
    from open_alm_api.domains.meal_invoice_ocr import APP_ID
    from open_alm_api.domains.meal_invoice_ocr.task_kinds import (
        MEAL_INVOICE_OCR_RESCAN_TASK_KIND,
        MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID,
        MEAL_INVOICE_OCR_TASK_KIND,
        MEAL_INVOICE_OCR_WORKLOAD_ID,
    )

    selected_workload_id = workload_id or MEAL_INVOICE_OCR_WORKLOAD_ID
    workload_task_kinds = {
        MEAL_INVOICE_OCR_WORKLOAD_ID: MEAL_INVOICE_OCR_TASK_KIND,
        MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID: MEAL_INVOICE_OCR_RESCAN_TASK_KIND,
    }
    try:
        selected_task_kind = workload_task_kinds[selected_workload_id]
    except KeyError as error:
        raise ValueError(
            f"unsupported meal invoice OCR workload: {selected_workload_id}"
        ) from error

    context = LlmTaskContext(
        source="meal_invoice_ocr",
        workspace_id=workspace_id,
        task_kind=selected_task_kind,
        app_id=APP_ID,
        actor_user_id=actor_user_id,
    )
    text = (prompt if prompt is not None else _PROMPT) + fewshot
    result = execute_llm(
        selected_workload_id,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": _data_url(png)}},
                ],
            }
        ],
        max_tokens=MAX_NEW_TOKENS,
        temperature=0,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        reasoning_effort="none",
    )
    return result.completion.text


def _invoke_vision(
    png: bytes,
    *,
    budget: _VisionCallBudget | None = None,
    **kwargs: Any,
) -> str:
    """테스트 대체 호출에도 유지되는 요청 예산 경계 뒤에서 vision gateway를 실행한다."""
    if budget is not None:
        budget.consume()
    return _call_vision(png, **kwargs)


def _render_band_png(page_png: bytes, y0_frac: float, y1_frac: float) -> bytes:
    """페이지의 세로 구간을 자르고 픽셀 상한 안에서 최대 2배 확대한 PNG를 만든다.

    데이터 행 구간만 잘라 확대해 넣으면 그 부분이 vision 모델 입력에서 차지하는 픽셀이 늘어, 전체
    페이지 다운샘플로 뭉개졌던 작은 손글씨의 실효 해상도가 올라간다. 출력은 기존 페이지 렌더 상한인
    ``MAX_RENDER_PIXELS``를 절대 넘지 않는다. 표가 페이지 대부분을 차지하면 확대하지 않아, 24MP
    페이지를 96MP로 키우는 메모리 폭증을 막는다.
    """
    import io

    from PIL import Image

    with Image.open(io.BytesIO(page_png)) as image:
        width, height = image.size
        top = max(0, int(y0_frac * height))
        bottom = min(height, int(y1_frac * height))
        if bottom <= top:
            return page_png
        band = image.crop((0, top, width, bottom))
    try:
        band_pixels = max(1, band.width * band.height)
        scale = min(2.0, math.sqrt(MAX_RENDER_PIXELS / band_pixels))
        target_size = (
            max(1, int(band.width * scale)),
            max(1, int(band.height * scale)),
        )
        if target_size != band.size:
            resized = band.resize(
                target_size,
                Image.Resampling.LANCZOS,
            )
            band.close()
            band = resized
        out = io.BytesIO()
        band.save(out, format="PNG")
        return out.getvalue()
    finally:
        band.close()


def _canonical_rescan_unit(raw: object) -> str:
    """pass-2 단위를 서버 소유 고정 목록으로 검증한다. 목록 밖 값은 신뢰하지 않는다."""
    unit = _norm_token(raw)
    canonical = _RESCAN_UNIT_ALIASES.get(unit, unit)
    return canonical if canonical in _RESCAN_UNIT_OPTIONS else ""


def _maybe_suggest_name(
    item: dict[str, Any], best_row: dict[str, Any], catalog: dict[str, Any]
) -> bool:
    """확대 재판독 품명이 대장과 1차 품명보다 더/같게 맞으면 검수 후보로 남긴다.

    같은 거래처에서도 실제 품목이 반복될 수 있고 pass-1/pass-2가 서로 다른 정상 카탈로그 품명을
    읽을 수 있으므로 자동 변경하지 않는다. 반환값은 후보를 기록했는지 여부다.
    """
    from open_alm_api.domains.meal_invoice_ocr.catalog import best_match as catalog_match

    p2_clean = _clean_item_name(_extract_origin(str(best_row.get("품명", "")))[1])
    p1_clean = _clean_item_name(_extract_origin(str(item.get("품명", "")))[1])
    if not p2_clean or p2_clean == p1_clean:
        return False
    _key2, s2 = catalog_match(p2_clean, catalog)
    if s2 < _NAME_SUGGEST_MIN:
        return False
    _key1, s1 = catalog_match(p1_clean, catalog)
    if s2 >= s1:
        item["_rescan_name_candidate"] = str(best_row.get("품명", ""))
        return True
    return False


def _has_rescan_band(payload: dict[str, Any]) -> bool:
    """payload에 유효한 행 box가 있어 pass-2 확대 재판독이 가능한지 확인한다."""
    boxes = [
        item["box"]
        for item in payload.get("품목", [])
        if isinstance(item, dict)
        and isinstance(item.get("box"), list)
        and len(item["box"]) == 2
        and all(isinstance(value, (int, float)) for value in item["box"])
    ]
    if not boxes:
        return False
    y0 = max(0.0, (min(box[0] for box in boxes) / 1000.0) - _BAND_PAD_FRAC)
    y1 = min(1.0, (max(box[1] for box in boxes) / 1000.0) + _BAND_PAD_FRAC)
    return y1 > y0


def _rescan_band_into_payload(
    page_png: bytes,
    payload: dict[str, Any],
    *,
    db: Session,
    workspace_id: str,
    actor_user_id: str | None,
    catalog: dict[str, Any] | None = None,
    budget: _VisionCallBudget | None = None,
    row_counts: list[tuple[int, int]] | None = None,
) -> bool:
    """데이터 행 band 를 확대해 품명·원산지·단위를 재판독하고 payload 행에 보강한다(in-place).

    row_counts: 넘기면 (pass-1 행 수, pass-2 행 수)를 append 한다. 두 회차가 같은 표를 다르게 분할한
    것이므로, 수가 다르면 표 행 분할이 불확실하다는 신호다(호출측이 경고로 노출한다).

    전체 페이지를 한 번에 넣으면 비전 모델이 작은 손글씨(품명 옆 원산지, 수량 옆 단위)를 다운샘플로
    뭉개거나 통째로 놓치고, 불확실한 품명은 문맥상 그럴듯한 다른 품목으로 지어낸다(회차마다 흔들림).
    box 로 데이터 행 세로 구간을 잡아 확대 재판독하면 같은 모델이 훨씬 안정적으로 읽는다. 이 재판독은
    vision gateway 를 1회 더 호출하지만(페이지당 pass-1 + pass-2), 한 번의 호출로 품명·원산지·단위를
    함께 돌려주므로 보강 항목별로 호출을 나누지는 않는다.

    행 정렬: 재판독 행 수가 1차와 같으면 위치(순서)로 정렬한다(밴드도 같은 행을 위→아래로 읽으므로
    가장 정확하고, 품명이 크게 오독돼도 대응돼 품명 후보를 제시할 수 있다). 수가 다르면 순서를 못 믿으므로
    품명 유사도로 매칭하고 원산지·단위만 보강한다(품명 후보는 제시하지 않음).

    - 원산지: '국내산 → 실제 나라'로만 승격(이미 나라면 유지).
    - 단위: 재판독이 읽은 단위를 우선(실효 해상도↑). 숫자는 보존하고 '단위' 칸만 교체.
    - 품명: 위치 정렬일 때만, 재판독 이름이 대장 실제 품목과 더/같게 잘 맞으면 검수 후보로 제시한다.

    반환: 재판독 비전 호출을 실제로 수행했으면 True(호출 예산 차감용).
    """
    items = [it for it in payload.get("품목", []) if isinstance(it, dict)]
    boxes = [
        it["box"]
        for it in items
        if isinstance(it.get("box"), list)
        and len(it["box"]) == 2
        and all(isinstance(v, (int, float)) for v in it["box"])
    ]
    if not boxes:
        return False
    y0 = max(0.0, (min(b[0] for b in boxes) / 1000.0) - _BAND_PAD_FRAC)
    y1 = min(1.0, (max(b[1] for b in boxes) / 1000.0) + _BAND_PAD_FRAC)
    if y1 <= y0:
        return False
    band_png = _render_band_png(page_png, y0, y1)
    from open_alm_api.domains.meal_invoice_ocr.task_kinds import (
        MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID,
    )

    raw = _invoke_vision(
        band_png,
        budget=budget,
        db=db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        prompt=_RESCAN_PROMPT,
        workload_id=MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID,
    )
    parsed = _parse_json_object(raw) or {}
    rescanned = [r for r in parsed.get("행", []) if isinstance(r, dict)]
    if not rescanned:
        return True

    # 행 수가 같으면 위치(index)로 정렬 — 밴드도 같은 순서로 읽으므로 가장 정확하고, 품명이 크게
    # 오독돼도 대응된다(품명 후보 제시에 필요). 다르면 순서 신뢰 불가 → 품명 유사도 매칭(원산지·단위만).
    aligned_by_index = len(rescanned) == len(items)
    if row_counts is not None:
        row_counts.append((len(items), len(rescanned)))
    if aligned_by_index:
        pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = list(zip(items, rescanned))
    else:
        from open_alm_api.domains.meal_invoice_ocr.vocab import best_match

        available_rows = list(rescanned)
        pairs = []
        for item in items:
            candidate_names = [str(r.get("품명", "")) for r in available_rows]
            best_name, best_score = best_match(str(item.get("품명", "")), candidate_names)
            row = None
            if best_name and best_score >= _RESCAN_NAME_MIN:
                match_index = next(
                    (
                        index
                        for index, candidate in enumerate(available_rows)
                        if str(candidate.get("품명", "")) == best_name
                    ),
                    None,
                )
                if match_index is not None:
                    row = available_rows.pop(match_index)
            pairs.append((item, row))

    from open_alm_api.domains.meal_invoice_ocr.vocab import _score as _name_score

    for item, best_row in pairs:
        if best_row is None:
            continue
        # 품명은 대장과 맞아도 자동 변경하지 않고 검수 후보로만 남긴다.
        if aligned_by_index and catalog:
            _maybe_suggest_name(item, best_row, catalog)
        # 위치(index) 정렬 쌍은 개수만 우연히 같고 행이 어긋났을 수 있다(모델이 행 병합·분리). 이름이
        # 충분히 비슷한(같은 행일 개연성이 있는) 쌍에만 원산지·단위를 옮긴다 —
        # 그렇지 않으면 엉뚱한 품목에 원산지/단위가 이식된다. (수 불일치 매칭 경로는 위치 근거가 없어
        # 짝을 고를 때 이미 같은-품목 기준인 _RESCAN_NAME_MIN 을 통과했으므로 여기서 또 보지 않는다.)
        if aligned_by_index:
            p1_name = _clean_item_name(_extract_origin(str(item.get("품명", "")))[1])
            p2_name = _clean_item_name(_extract_origin(str(best_row.get("품명", "")))[1])
            if _name_score(p1_name, p2_name) < _RESCAN_ALIGN_MIN:
                continue
        # 단위: 재판독이 읽은 단위를 우선. 숫자는 보존하고 '단위' 칸만 채운다(수량에 박힌 단위와 겹쳐
        # "6 k 박스"처럼 되지 않게, 수량은 숫자부만 남기고 단위는 전용 칸으로 옮긴다).
        unit_read = _canonical_rescan_unit(best_row.get("단위", ""))
        if unit_read:
            qty_num, _embedded = split_qty(item.get("수량", ""))
            item["수량"] = qty_num
            item["단위"] = unit_read
            if _promotable_spec_unit(item.get("규격", "")):
                item["규격"] = ""
        # 원산지: 국내산 → 실제 나라로만 승격.
        #
        # 근거는 두 곳에서 본다. (1) 재판독 '원산지' 칸, (2) 함께 읽은 '품명' 텍스트. 재판독 프롬프트는
        # 품명을 정제하지 않고 원문 그대로 읽으므로('고추명가낙지볶음소스,중국산,스카이푸드'), 원산지 칸이
        # 기본값 국내산으로 와도 품명 텍스트에는 인쇄된 나라가 남아 있는 회차가 있다. pass-1 은 품명을
        # 정제하면서 이 나라 표기를 흘리므로(관측), 원문을 읽는 이 경로가 마지막 복구 지점이다.
        #
        # 품명 텍스트는 인쇄된 '나라 이름'만 근거로 본다(_printed_country_origin). 재판독은 품명을
        # 정제하지 않고 원문 그대로 읽으므로 '감자 중'·'고구마 中'·'비마늘(중)' 같은 크기 등급이 그대로
        # 오는데, 축약 마커를 나라로 읽으면 pass-1 의 국내산 행을 중국산으로 덮는다(규격 칸에서
        # 축약을 인정하지 않는 _origin_from_spec 과 같은 이유).
        new_origin = _foreign_origin(best_row.get("원산지", "")) or _foreign_origin(
            _printed_country_origin(best_row.get("품명", ""))
        )
        if new_origin:
            origin_in_name, _ = _extract_origin(str(item.get("품명", "")))
            current = origin_in_name or _normalize_origin(str(item.get("원산지", "")))
            if current == "국내산":
                item["원산지"] = new_origin
    return True


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_number(value: str) -> float | None:
    """문자열에서 숫자를 뽑는다(쉼표·단위·물음표 제거). 뽑을 수 없으면 None."""
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def annotate_row(row: MealInvoiceRow) -> MealInvoiceRow:
    """수량*단가 와 금액 대조 결과를 금액검증 필드에 채운다."""
    qty = parse_number(row.수량)
    unit = parse_number(row.단가)
    amount = parse_number(row.금액)
    verdict = ""
    if qty is not None and unit is not None and amount is not None:
        expected = qty * unit
        verdict = "OK" if abs(expected - amount) < 1 else f"확인({int(round(expected))})"
    row.금액검증 = verdict
    return row


def annotate_document(doc: MealInvoiceDocument) -> MealInvoiceDocument:
    """행 금액 합계를 공급가액/합계금액과 대조해 합계검증을 채운다.

    부가세가 분리된 양식은 행 금액 합계 = 공급가액(부가세 제외)이고 합계금액 = 총금액(부가세 포함)이라
    둘 중 하나와만 맞아도 정상이다. 어느 기준과도 안 맞을 때만 불일치로 표시한다.
    """
    doc.품목 = [annotate_row(row) for row in doc.품목]
    row_amounts = [parse_number(row.금액) for row in doc.품목]
    if not any(a is not None for a in row_amounts):
        doc.합계검증 = ""
        return doc
    row_sum = sum(a for a in row_amounts if a is not None)
    refs: list[tuple[str, float]] = []
    for label, raw in (("공급가액", doc.공급가액), ("합계", doc.합계금액)):
        value = parse_number(raw)
        if value is not None:
            refs.append((label, value))
    if not refs:
        doc.합계검증 = ""
    elif any(abs(row_sum - value) < 1 for _, value in refs):
        doc.합계검증 = "일치"
    else:
        parts = ", ".join(f"{label} {int(round(value))}" for label, value in refs)
        doc.합계검증 = f"불일치(행합 {int(round(row_sum))} vs {parts})"
    return doc


# 이 이상 유사하고 OCR 품명과 다르면 사전 후보로 제시(자동 덮어쓰기는 하지 않음).
_VOCAB_MATCH_MIN = 0.72


def annotate_vocab(doc: MealInvoiceDocument, vocab: list[str] | None) -> MealInvoiceDocument:
    """각 품명을 사전에 매칭해 다른 정규 품명이 유력하면 사전후보/사전점수를 채운다."""
    if not vocab:
        return doc
    from open_alm_api.domains.meal_invoice_ocr.vocab import best_match, confusable_alt

    for row in doc.품목:
        if not row.품명.strip():
            continue
        if row.사전후보:
            continue
        best, score = best_match(row.품명, vocab)
        if best and best != row.품명 and score >= _VOCAB_MATCH_MIN:
            row.사전후보 = best
            row.사전점수 = round(score, 3)
            continue
        # 읽은 품명이 사전에 그대로 있어(정상 품명) 위 제안이 안 떴을 때: 첫 음절이 같은 헷갈리는
        # 대안(양파↔양상추 등)이 사전에 있으면 대안 칩으로 제안한다(값은 안 바꿈, 검수자 원클릭 교정용).
        alt, alt_score = confusable_alt(row.품명, vocab)
        if alt:
            row.사전후보 = alt
            row.사전점수 = round(alt_score, 3)
    return doc


def annotate_catalog(
    doc: MealInvoiceDocument, catalog: dict[str, Any] | None
) -> MealInvoiceDocument:
    """각 품명을 기준 카탈로그(영양사 대장)에 매칭해 품목/단위/단가 제안을 채운다.

    OCR 이 읽은 값은 덮어쓰지 않는다(카탈로그는 제안만). 품명은 사전후보(없을 때만), 단위는
    단위후보 칩으로 제시하고, 단위가 아예 비어 있을 때만 최빈 단위를 기본값으로 채운다. 단가는
    단가후보에 대표값(최근)을 넣는다.

    (과거에 'OCR 단위가 이력에 없으면 오독으로 보고 카탈로그 단위로 교체 + 문서 내 전파'를 했으나,
    채소 거래처처럼 대부분 품목이 kg 이력인 대장에서는 실제로 박스/송이로 온 정상 단위를 k 로 뭉개는
    오작동이 있어 제거했다. OCR 단위를 신뢰하고 다른 단위는 칩 제안으로만 노출한다.)
    """
    if not catalog:
        return doc
    from open_alm_api.domains.meal_invoice_ocr.catalog import (
        best_match as catalog_match,
        units_for as catalog_units_for,
    )

    for row in doc.품목:
        if not row.품명.strip():
            continue
        key, score = catalog_match(row.품명, catalog)
        if not key or score < _VOCAB_MATCH_MIN:
            continue
        entry = catalog.get(key) or {}
        # 품목 제안: 사전(vocab)이 이미 채웠으면 존중하고, 비었을 때만 카탈로그 정식명 제안.
        if not row.사전후보 and key != row.품명:
            row.사전후보 = key
            row.사전점수 = round(score, 3)
        # 유사한 품목들(여러 카탈로그 키)의 단위를 합산해 빈도순으로 전부 제시(제안 칩).
        units = catalog_units_for(row.품명, catalog)
        if units:
            row.단위후보목록 = units
            row.단위후보 = units[0]
            # OCR 이 단위를 아예 못 뽑았을 때만(수량이 순수 숫자) 카탈로그 최빈 단위를 기본값으로 채운다.
            # OCR 이 읽은 단위는 신뢰해 덮어쓰지 않는다(카탈로그와 달라도 칩으로만 제안).
            q = (row.수량 or "").strip()
            if q and not re.search(r"[^\d.,\s]", q):
                row.수량 = f"{q} {units[0]}"
        price = str(entry.get("단가", "") or "").strip()
        if price:
            row.단가후보 = price
    return doc


def _document_from_payload(
    payload: dict[str, Any],
    *,
    filename: str,
    page_no: int,
    page_image: str = "",
) -> MealInvoiceDocument:
    # per-row 크롭은 모델이 균일 격자를 찍어 실제 표와 어긋나(누적 드리프트) 신뢰할 수 없어 제거했다.
    # 대신 문서마다 원본 페이지 전체 이미지 하나를 표시한다(드리프트 없음).
    items_raw = payload.get("품목")
    rows: list[MealInvoiceRow] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            # 정제 전 OCR 품명 원문. 학습 키로만 쓰고 화면에는 정제 결과를 보여준다.
            raw_ocr_name = str(item.get("품명", "") or "").strip()
            origin_in_name, name_wo_origin = _extract_origin(item.get("품명", ""))
            cleaned_item_name = _clean_item_name(name_wo_origin)
            # 명세표에 단위 칸이 따로 있으면(Box/ea/PK...) 수량 숫자 뒤에 붙여 "1.0Box" 형태로 합친다.
            # (앱은 수량 칸에서 숫자+단위를 분리해 단위 드롭다운으로 보여준다.)
            # 영어 단위는 전부 소문자로 표시(한글 단위는 .lower() 영향 없음). 'kg'는 'k'로 통일.
            # 수량·단위 양쪽을 같은 규칙으로 정규화한 뒤 비교해야, 수량에 이미 단위가 붙어
            # 있는 경우("10kg" + 단위 "kg")의 중복 판정이 정규화 때문에 어긋나지 않는다.
            # 수량에 숫자와 단위가 함께 있으면("10kg"·"30낱") 먼저 분리한다. 최종 단위는 아래
            # 우선순위로 하나만 정하므로, 수량에 박힌 단위와 단위 칸이 겹쳐도 중복되지 않는다.
            qty_raw = _norm_token(item.get("수량", ""))
            qty_num, embedded_unit = split_qty(qty_raw)
            unit_col = _norm_token(item.get("단위", ""))
            규격_raw = str(item.get("규격", "") or "")
            promoted_spec_unit = _promotable_spec_unit(규격_raw)
            # 최종 단위 우선순위: 전용 '단위' 칸 > '규격' 칸의 단위 승격 > 수량에 박힌 단위.
            # 규격 승격: 전용 단위 칸이 없고 규격이 '알려진 단위' 하나와 정확히 일치할 때만 단위로 올리고
            # 규격 원문은 비운다(중복 표시 방지). 크기·호수·등급 등 진짜 규격은 집합에 없어 그대로 남는다.
            unit = unit_col
            if not unit and promoted_spec_unit:
                unit = promoted_spec_unit
                규격_raw = ""
            if not unit:
                unit = embedded_unit
            # 수량에 박힌 단위와 선택 단위가 다르면 기존 수량 원문을 보존한 채 선택 단위를 덧붙인다.
            # 숫자가 아닌 값·분수·범위도 qty_num 에 원문 전체가 남으므로 명시 단위 때문에 손실되지 않는다.
            qty_base = qty_num
            append_unit = bool(unit)
            if _quantity_already_ends_with_unit(qty_raw, unit):
                qty_base = qty_raw
                append_unit = False
            elif embedded_unit and embedded_unit != unit:
                qty_base = qty_raw
            # 숫자와 단위 사이에 공백을 둔다 → "10k"처럼 숫자로 시작하는 단위도 재분리 시 보존된다.
            qty_combined = f"{qty_base} {unit}".strip() if append_unit else qty_base
            # 품명 텍스트에 원산지가 박혀 있으면(예: "…,중국산,브랜드") 뽑아서 원산지에 반영하고 품명에선 제거.
            # LLM 이 준 원산지는 상호·브랜드(태화 등)를 지어낼 수 있으니 나라 목록으로 검증한다.
            #
            # 우선순위: 품명에 박힌 원산지 > '원산지' 칸의 나라(국내산 제외) > '규격' 칸의 나라 > 국내산.
            #
            # 명세표의 원산지는 전용 칸·품명·규격 어디에도 올 수 있고, 모델은 회차마다 같은 '중국산'을
            # 다른 칸에 넣는다(원산지 칸에 브랜드를 넣고 규격에만 나라를 남기는 변형이 관측됐다).
            # 규격을 보지 않으면 읽어낸 나라 표기를 버리고 조용히 '국내산'으로 단정하게 된다.
            #
            # '원산지' 칸의 국내산은 근거가 아니라 모델 기본값이므로 여기서 체인을 멈추지 않는다
            # (_foreign_origin). 반대로 품명·규격에 인쇄된 '국내산'은 문서 텍스트라 근거로 인정한다.
            # 규격 원문은 표시용으로 바꾸지 않는다(OCR 원문 충실도).
            원산지 = (
                origin_in_name
                or _foreign_origin(item.get("원산지", ""))
                or _origin_from_spec(item.get("규격", ""))
                or "국내산"
            )
            rows.append(
                MealInvoiceRow(
                    품명=cleaned_item_name,
                    규격=규격_raw,
                    수량=qty_combined,
                    단가=str(item.get("단가", "") or ""),
                    금액=str(item.get("금액", "") or ""),
                    원산지=원산지,
                    신선도="O",
                    불량여부="-",
                    반품여부="-",
                    비고="",
                    사전후보=str(item.get("_rescan_name_candidate", "") or ""),
                    # 이후 사전·카탈로그·과거 교정이 이 값들을 덮어쓸 수 있다. 학습은 보정된 값이
                    # 아니라 여기 남은 OCR 원문을 키로 삼아야 오염된 교정 쌍이 쌓이지 않는다.
                    # 품명은 정제(브랜드·규격·단위 제거) 전 원문을 둔다. 정제는 학습 데이터가 없을 때의
                    # 폴백 표시 규칙일 뿐이고, 학습은 문서에 인쇄된 문자열 자체를 키로 삼아야 한다.
                    원문=MealInvoiceRowSource(
                        품명=raw_ocr_name,
                        수량=qty_combined,
                        원산지=원산지,
                    ),
                )
            )
    doc = MealInvoiceDocument(
        원본파일=filename,
        페이지=page_no,
        거래처=str(payload.get("거래처", "") or ""),
        거래일=str(payload.get("거래일", "") or ""),
        합계금액=str(payload.get("합계금액", "") or ""),
        공급가액=str(payload.get("공급가액", "") or ""),
        페이지이미지=page_image,
        품목=rows,
    )
    return annotate_document(doc)


# 확정 교정 별칭. 거래처 + 원본 품명이 과거 교정과 '정확히' 일치할 때만 품명·원산지·단위를 자동
# 적용한다(사용자 요청: 반복 거래처는 첫 1회 교정 후 자동 채움). 정확 일치가 아닌 유사 매칭은 엉뚱한
# 품목을 덮어쓸 위험이 있어 단위 후보로만 제시한다. 특정 품목 하드코딩 없이 사용자 소유 교정 데이터에서
# 만드는 범용 매핑이다.


def display_item_name(name: object) -> str:
    """OCR 원문 품명 → 화면 표시 품명(원산지 분리 + 브랜드·규격·단위 정제).

    행 조립과 별칭 키가 쓰는 정제 규칙의 단일 진입점. 학습 키는 원문이고 표시 값은 이 정제 결과라,
    두 공간을 오가는 지점(별칭 비교, few-shot 예시)이 각자 정제를 재구현하면 키 공간이 어긋난다.
    """
    return _clean_item_name(_extract_origin(str(name or ""))[1])


def _alias_key(name: object) -> str:
    """별칭 매칭 키. 최종 품명 생성과 같은 정제를 거친 뒤 한글/영숫자만 남겨 표기 흔들림을 흡수한다."""
    return re.sub(r"[^가-힣A-Za-z0-9]", "", display_item_name(name).lower())


def _raw_source_key(name: object) -> str:
    """학습 저장·조회 키. OCR 원문을 정제하지 않고 표기 흔들림(공백·기호·대소문자)만 흡수한다.

    ``_alias_key`` 와 달리 브랜드·규격·단위·괄호를 지우지 않는다. 정제는 학습 데이터가 없을 때의
    폴백 표시 규칙이므로, 학습 키가 정제를 거치면 '문서에 인쇄된 문자열'이 아니라 '그때의 정제
    규칙 결과'를 학습하게 되고 규칙이 바뀌면 축적된 교정이 매칭되지 않는다.

    이미 정제된 이름만 저장돼 있던 기존 교정 데이터는 정제가 멱등이라 같은 키가 나오므로, 아래
    조회에서 정제 품명 키로도 찾으면 그대로 매칭된다(하위 호환).
    """
    return re.sub(r"[^가-힣A-Za-z0-9]", "", str(name or "").lower())


def _vendor_key(value: object) -> str:
    """거래처 비교용 키. 공백 흔들림은 흡수하되 상호 안의 ``kg`` 문자는 보존한다."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", normalized)


# 읽어낸 상호를 유사한 기존 거래처로 치환하지 않는다. 손글씨 상호가 흔들리는 것은 사실이지만
# ('성진유통'↔'상전유통' 0.82), 오독과 '이름이 비슷한 새 거래처'를 구분할 근거가 없다. 치환하면 신규
# 실제 거래처의 문서에 기존 거래처의 확정 교정이 자동 적용되어 공유 학습이 오염된다. 상호는 검수자가
# 거래처 칸에서 정본으로 고쳐 저장하는 것이 유일한 확정 경로이며, 그때부터 그 거래처 학습이 붙는다.


def build_vendor_aliases(
    corrections: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """실제로 바뀐 필드만 담은 거래처별 교정 별칭을 만든다.

    거래처별로 격리한다. 한 거래처의 확정 교정이 다른 거래처의 품명·원산지·단위를 덮어쓰면 공유
    학습이 오염된다(같은 오독 문자열을 거래처마다 다른 품목으로 교정할 수 있다).

    원본 품명 인덱스와 교정 품명 fallback을 분리한다. 동일 교정 품명으로 여러 원본이 모이면 provenance를
    결정할 수 없으므로 fallback을 만들지 않으며, 조회 시 원본 인덱스가 항상 우선한다.

    한 이름이 오독(원본)으로도 정답(교정)으로도 등장하면 학습 신호가 서로 모순이다
    ('깻잎→감자'와 '감자→깻잎', '쑥갓→파'와 '쭉파→쑥갓'). 이때 그 이름을 오독으로 단정하면 정상
    판독을 덮어쓰고, 양방향 쌍은 읽을 때마다 뒤집혀 영원히 수렴하지 않는다. 그런 항목은 자동적용
    인덱스에서 빼고 ``suggest``(검수 후보)로만 남긴다.
    """
    aliases: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for record in corrections:
        vendor = _vendor_key(record.get("거래처", ""))
        원본 = record.get("원본") or {}
        교정 = record.get("교정") or {}
        raw_name = str(원본.get("품명", "") or "").strip()
        # 학습 인덱스는 OCR 원문 키로 만든다(정제 결과가 아니라 문서에 인쇄된 문자열 기준).
        raw_key = _raw_source_key(raw_name)
        if not vendor or not raw_key:
            continue
        fixed_name = str(교정.get("품명", "") or "").strip()
        _raw_num, raw_unit = split_qty(원본.get("수량", ""))
        _fixed_num, fixed_unit = split_qty(교정.get("수량", ""))
        raw_origin = str(원본.get("원산지", "") or "").strip()
        fixed_origin = str(교정.get("원산지", "") or "").strip()
        changes: dict[str, Any] = {}
        # '품명이 바뀌었는가'는 표시 품명끼리(정제 키) 비교한다. 저장 키는 OCR 원문이지만, 사용자가
        # 화면에서 확인/수정하는 값은 정제된 품명이다. 원문 키와 교정 품명을 직접 비교하면 사용자가
        # 품명을 손대지 않고 원산지만 고쳐도('냉동새우살(대),5kg' vs '냉동새우살') 이름 교정 엔트리가
        # 허위로 생겨, 아래 '변경 없음' 자기치유와 모순 학습 분류가 모두 어긋난다.
        if "품명" in 교정 and fixed_name and _alias_key(fixed_name) != _alias_key(raw_name):
            changes["name"] = {"raw": raw_name, "fixed": fixed_name}
        if "수량" in 원본 and "수량" in 교정 and _norm_token(raw_unit) != _norm_token(fixed_unit):
            changes["unit"] = {"raw": raw_unit, "fixed": fixed_unit}
        # 원산지 교정도 학습한다(사용자 요청: 거래처+품목 정확 일치 시 원산지 자동 적용).
        if "원산지" in 교정 and fixed_origin and fixed_origin != raw_origin:
            changes["origin"] = {"raw": raw_origin, "fixed": fixed_origin}
        if not changes:
            # 최신 확인에서 품명·단위가 그대로면 같은 키의 오래된 오교정 제안도 폐기한다.
            bucket = aliases.get(vendor)
            if bucket:
                bucket["raw"].pop(raw_key, None)
                if not bucket["raw"]:
                    aliases.pop(vendor, None)
            continue
        bucket = aliases.setdefault(vendor, {"raw": {}, "fallback": {}, "suggest": {}})
        # display_key: 원문 키를 표시 품명 공간으로 옮긴 값. 정제 품명 기준으로 비교해야 하는 판단
        # (모순 학습 차단 등)이 원문 키 공간과 섞이지 않도록 함께 들고 다닌다.
        bucket["raw"][raw_key] = {
            "source_key": raw_key,
            "display_key": _alias_key(raw_name),
            **changes,
        }

    for bucket in aliases.values():
        # 정답(교정 품명)으로 확정된 적 있는 이름은 오독 키로 쓰지 않는다. 실재하는 품목이라는 뜻이므로
        # 다음에 그 이름을 읽었을 때 잘못 읽은 것이라고 단정할 수 없다.
        confirmed: set[str] = set()
        for entry in bucket["raw"].values():
            name_change = entry.get("name")
            if isinstance(name_change, dict):
                fixed_key = _alias_key(name_change.get("fixed", ""))
                if fixed_key:
                    confirmed.add(fixed_key)
        # confirmed 는 정제 품명 키 집합이므로 원문 키를 그대로 교집합하면 걸리지 않는다
        # ('깻잎(국내산)' 원문 키 vs '깻잎' 확정 키). 표시 품명 키로 비교한다.
        contradicting = sorted(
            raw_key
            for raw_key, entry in bucket["raw"].items()
            if str(entry.get("display_key") or raw_key) in confirmed
        )
        for raw_key in contradicting:
            bucket["suggest"][raw_key] = bucket["raw"].pop(raw_key)

        candidates: dict[str, list[dict[str, Any]]] = {}
        for entry in bucket["raw"].values():
            name_change = entry.get("name")
            if not isinstance(name_change, dict):
                continue
            # 교정 품명으로 색인(단위 변경 유무와 무관). OCR 이 교정한 이름을 그대로 읽었을 때 원산지·단위를
            # 재적용하기 위함. 동일 교정 품명이 여러 원본에서 나오면(모호) 아래에서 제외한다.
            fixed_key = _alias_key(name_change.get("fixed", ""))
            if fixed_key:
                candidates.setdefault(fixed_key, []).append(entry)
        bucket["fallback"] = {
            key: entries[0] for key, entries in candidates.items() if len(entries) == 1
        }
    return aliases


def _apply_vendor_aliases(
    doc: MealInvoiceDocument,
    aliases: dict[str, dict[str, dict[str, dict[str, Any]]]],
    *,
    vocab: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> None:
    """과거 확정 교정을 적용한다(거래처별 격리).

    조회 키는 OCR 원문(``row.원문.품명``)이 1순위, 정제 품명이 2순위다. 학습된 원문이 있으면 그
    교정 결과를 출력하고, 없으면 정제된 품명이 그대로 표시 값으로 남는다.

    거래처 + 원본 품명이 과거 교정과 '정확히' 일치하면(raw 인덱스) 확정 학습으로 보고 품명·원산지·단위를
    바로 자동 적용하고, 겹칠 수 있는 사전·카탈로그 후보는 지운다(사용자 요청: 반복 거래처는 첫 1회 교정
    후 자동). 다른 거래처의 학습은 이 문서에 적용하지 않으며, 상호가 정확히 일치하지 않으면 아무것도
    적용하지 않는다.

    정확 일치가 아닌 유사 매칭은 '같은 글씨를 달리 읽은 오독'일 때만 의미가 있다. 읽은 품명이 이미
    사전/카탈로그에 있는 실재 품목이면 오독이 아니라 정상 판독으로 보고 자동 적용하지 않는다. 초성 열이
    다른 이름도 다른 품목으로 보고 배제한다('부추' ㅂㅊ ↔ '후추' ㅎㅊ 는 자모 유사도 0.75 로 임계값을
    넘지만 서로 다른 품목이다). 교정 품명 색인(fallback)은 품명을 바꾸지 않고 원산지·단위만 보강한다.
    """
    from open_alm_api.domains.meal_invoice_ocr.vocab import _score as _name_score, initials

    bucket = aliases.get(_vendor_key(doc.거래처))
    if not bucket:
        return
    raw_bucket = bucket["raw"]
    suggest_bucket = bucket.get("suggest") or {}
    # 실재 품목 이름 집합. 여기 있으면 '잘못 읽은 이름'으로 단정하지 않는다.
    known_names = {_alias_key(name) for name in (vocab or [])}
    known_names |= {_alias_key(key) for key in (catalog or {})}
    known_names.discard("")
    for row in doc.품목:
        current_name_key = _alias_key(row.품명)
        # 학습 조회는 OCR 원문 키가 1순위다. 원문에 학습이 있으면 정제 규칙과 무관하게 확정 교정을
        # 그대로 출력하고, 학습이 없을 때만 정제 품명(폴백 표시 값)으로 조회한다. 정제 품명 조회는
        # 원문 없이 저장된 기존 교정 데이터의 하위 호환 경로이기도 하다.
        source_name_key = _raw_source_key(row.원문.품명)
        lookup_keys = [key for key in dict.fromkeys((source_name_key, current_name_key)) if key]
        if not lookup_keys:
            continue
        # 1) 원본 품명 정확 일치. 2) 없으면 학습한 원본 품명 중 자모 유사도가 임계값 이상으로 가장 가까운
        #    것(OCR 오독 변형 보정: '고칫갸루'로 학습→다음에 '고찻가루'로 읽혀도 매칭). 둘 다 확정 적용.
        #
        # 단 두 경로 모두 '읽은 이름이 실재 품목'이면 적용하지 않는다. 오독 교정은 '읽은 이름이 실재하지
        # 않는 글자'일 때만 성립한다. 실재 품목으로 읽혔다면 정상 판독일 개연성이 훨씬 높다.
        # (실측: '냉동새우살'→'무청시래기' 학습이 쌓여, 다음 문서에서 OCR 이 '냉동새우살'을 정확히
        #  읽었는데도 품명이 '무청시래기'로 덮이고 그 행의 원산지까지 함께 바뀌었다. '부추'·'딸기'·
        #  '진라면'·'청경채'처럼 실재 품목을 키로 가진 학습이 다수 있어 같은 사고가 반복된다.)
        # 이 규칙은 이미 유사 매칭 경로에만 걸려 있었다 — 정확 일치 경로가 같은 계약을 지키지 않아
        # 정상 판독을 덮어쓰는 통로가 됐다. 대신 아래에서 원클릭 후보 칩으로 제시한다.
        # 막는 것은 '이름을 다른 품목으로 바꾸라'는 학습뿐이다. 그 학습에는 다른 품목의 원산지·단위가
        # 함께 붙어 있으므로 entry 전체를 적용하지 않고 후보 칩으로만 제시한다. 반대로 이름을 바꾸지
        # 않는 학습(같은 품목의 원산지·단위만 교정)은 이 행에 대한 것이므로 그대로 자동 적용한다 —
        # 그것까지 막으면 '반복 거래처는 첫 1회 교정 후 자동 채움' 계약이 실재 품목 전체에서 깨진다
        # (known_names 는 기준 카탈로그 키를 모두 포함하므로 사실상 대부분의 행이 해당된다).
        is_known_item = current_name_key in known_names
        matched_key = next((key for key in lookup_keys if key in raw_bucket), "")
        entry = raw_bucket.get(matched_key) if matched_key else None
        # 원문 키로 정확히 맞았다는 사실은 이 가드를 면제할 근거가 되지 못한다. 학습이 만들어진 그 행도
        # 같은 원문(브랜드·규격·단위까지)으로 읽혔을 수 있으므로, 원문 일치는 '이번엔 제대로 읽었다'와
        # '이번에도 같은 오독이다'를 구분하지 못한다. 읽은 품명이 실재 품목이면 이름 교체는 언제나 후보
        # 칩으로만 제시한다(위 '냉동새우살(대),5kg'→'무청시래기' 사고 방지).
        blocked_entry: dict[str, Any] | None = None
        if is_known_item and isinstance((entry or {}).get("name"), dict):
            blocked_entry, entry = entry, None
        allow_name_change = entry is not None
        if entry is None and not is_known_item:
            # 임계값 이상이고 초성 열이 같은 후보를 모으고, 교정 결과(품명·원산지·단위)가 하나로 일치할
            # 때만 적용한다. 서로 다른 결과의 raw 들이 비슷하게 걸리면(모호) 임의로 고르지 않고 건너뛴다.
            # raw_bucket 의 키는 OCR 원문에서 소문자·기호만 제거한 값이다. 유사도·초성 비교도 같은
            # 공간의 키(원문 키)로 해야 '고칫갸루(1kg)'로 학습한 것이 '고찻가루(1kg)'에 걸린다. 정제
            # 품명 키로 비교하면 규격·브랜드가 붙은 학습 키와 길이·초성이 어긋나 전부 탈락한다.
            # 정제 품명 키(2순위)는 원문 없이 저장된 기존 교정 데이터용 하위 호환 경로다.
            lookup_initials = {key: initials(key) for key in lookup_keys}
            candidates = [
                e
                for raw_key, e in raw_bucket.items()
                if any(
                    _name_score(key, raw_key) >= _LEARN_FUZZY_MIN
                    and initials(raw_key) == lookup_initials[key]
                    for key in lookup_keys
                )
            ]
            if candidates:
                outcomes = {
                    (
                        (e.get("name") or {}).get("fixed", ""),
                        (e.get("origin") or {}).get("fixed", ""),
                        (e.get("unit") or {}).get("fixed", ""),
                    )
                    for e in candidates
                }
                if len(outcomes) == 1:
                    entry = candidates[0]
                    allow_name_change = True
        # 3) OCR 이 '교정한 이름(정답)'을 그대로 읽은 경우 = 교정 품명 정확 일치. 모호성 없는 색인만
        #    두므로 같은 품목으로 확신하고 원산지·단위만 보강한다(품명은 이미 정답이라 바꾸지 않는다).
        if entry is None:
            entry = bucket["fallback"].get(current_name_key)
        # 4) 모순 학습이거나(suggest) 실재 품목으로 읽혀 자동적용에서 뺀(blocked_entry) 항목은 검수자가
        #    원클릭으로 뒤집도록 후보 칩으로만 제시한다. 아래에서 실제 품명 교정이 일어나면 칩은 지운다.
        #    blocked_entry 는 사람이 확정한 교정이라 사전·카탈로그의 유사 추정보다 신뢰도가 높으므로,
        #    앞선 annotate_vocab/annotate_catalog 가 이미 채운 후보를 덮어쓴다. 그러지 않으면 학습이
        #    적용도 되지 않고 노출도 되지 않아 검수자가 볼 방법이 없다.
        suggested = blocked_entry or next(
            (suggest_bucket[key] for key in lookup_keys if key in suggest_bucket), None
        )
        if suggested and (blocked_entry is not None or not row.사전후보):
            suggested_name = str((suggested.get("name") or {}).get("fixed", ""))
            if suggested_name:
                row.사전후보 = suggested_name
                row.사전점수 = 1.0
        if not entry:
            continue
        name_change = entry.get("name")
        if isinstance(name_change, dict) and allow_name_change:
            fixed_name = str(name_change.get("fixed", ""))
            # 교정 결과가 지금 읽은 이름과 같으면(예: 오독 변형으로 학습한 정답을 그대로 읽음) 바꿀 것이
            # 없다. 이때 후보 칩까지 지우면 검수자가 대안을 볼 기회를 잃으므로 아무것도 하지 않는다.
            if fixed_name and _alias_key(fixed_name) != current_name_key:
                # 정확/유사 일치 → 확정 학습이므로 자동 적용(사전·카탈로그 후보보다 우선).
                row.품명 = fixed_name
                row.사전후보 = ""
                row.사전점수 = 0.0
        origin_change = entry.get("origin")
        if isinstance(origin_change, dict):
            fixed_origin = str(origin_change.get("fixed", ""))
            if fixed_origin:
                # 학습한 원산지 자동 적용(OCR 이 마커를 놓쳐도 반복 품목은 자동 채움).
                row.원산지 = fixed_origin
        unit_change = entry.get("unit")
        if isinstance(unit_change, dict):
            fixed_unit = str(unit_change.get("fixed", ""))
            if fixed_unit:
                # 매칭된 학습 단위를 자동 적용(수량 문자열의 단위를 교체). 단위 전용 필드가 없어 수량에 합쳐 둔다.
                # 수량 숫자가 없으면 단위만 남는 무의미한 값('박스')을 만들지 않고 후보로만 남긴다.
                qty_num, _current_unit = split_qty(row.수량)
                if qty_num:
                    row.수량 = f"{qty_num} {fixed_unit}"
                    row.단위후보 = ""


def extract_documents(
    uploads: list[MealInvoiceUpload],
    *,
    workspace_id: str,
    actor_user_id: str | None = None,
    fewshot: str = "",
    vocab: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
    aliases: dict[str, dict[str, dict[str, dict[str, Any]]]] | None = None,
) -> MealInvoiceExtractResponse:
    """업로드 파일들을 비전 OCR 해 구조화 문서 목록으로 돌려준다(동기, 블로킹).

    workspace_id/actor_user_id: 플랫폼 LLM gateway 호출용(정책·토큰 예산·감사). 각 페이지는 자체 DB
    세션을 열지만 같은 요청 worker thread에서 순차 처리해 trace context와 공용 gateway 용량을 보존한다.
    fewshot: 과거 교정 예시 텍스트. OCR 프롬프트에 주입해 알려진 오독을 줄인다(학습 루프).
    vocab: 정규 품명 사전. 각 품명에 유력한 사전 품명을 사전후보로 제시한다.
    catalog: 기준 카탈로그(영양사 대장). 품목/단위/단가 제안 + 확대 재판독의 품명 후보 기준.
    aliases: 거래처별 확정 교정 별칭. 조립 맨 끝에 품명·단위 검수 후보로만 제시한다.

    페이지는 렌더 직후 처리하고 버린다. 요청별 별도 executor를 만들지 않아 여러 요청이 공용 LLM/DB를
    무제한 fan-out하지 않고, 렌더 PNG를 최대 페이지 수만큼 메모리에 누적하지 않는다. 페이지마다 vision
    gateway 호출은 최대 2회(pass-1, pass-2)이며 전체 호출 수는 ``MAX_VISION_CALLS_PER_REQUEST`` 이하이다.
    """
    from open_alm_api.core.db import get_session_factory

    from open_alm_api.domains.meal_invoice_ocr.catalog import build_item_hint

    documents: list[MealInvoiceDocument] = []
    warnings: list[str] = []
    processed_pages = 0
    vision_budget = _VisionCallBudget(limit=MAX_VISION_CALLS_PER_REQUEST)
    # 대장 품목을 후보로 제시해 실재하지 않는 품명이 생성되는 것을 줄인다(단위 목록과 같은 방식).
    # 상위 N종만 넣는 것은 정확도를 위한 의도된 설계이며(_MAX_HINT_ITEMS 주석의 실측 참조) 사용자가
    # 조치할 일이 아니다. 매 실행마다 경고로 띄우면 진짜 경고(행 누락·렌더 실패)가 묻힌다.
    item_hint, _dropped = build_item_hint(catalog or {})
    prompt_hint = fewshot + item_hint
    for upload in uploads:
        if processed_pages >= MAX_TOTAL_OCR_PAGES or not vision_budget.available:
            warnings.append(
                f"총 OCR 처리 상한(페이지 {MAX_TOTAL_OCR_PAGES}, 호출 "
                f"{MAX_VISION_CALLS_PER_REQUEST})에 도달해 이후 파일은 건너뜁니다."
            )
            break
        try:
            doc = _open_document(upload)
        except Exception as error:  # noqa: BLE001 - 파일 하나 실패가 전체를 막지 않게.
            warnings.append(f"{upload.filename}: 렌더 실패({type(error).__name__}).")
            continue
        try:
            page_count = min(doc.page_count, MAX_PAGES_PER_DOC)
            if page_count == 0:
                warnings.append(f"{upload.filename}: 페이지를 읽지 못했습니다.")
                continue
            for page_index in range(page_count):
                if processed_pages >= MAX_TOTAL_OCR_PAGES or not vision_budget.available:
                    warnings.append(
                        f"총 OCR 처리 상한(페이지 {MAX_TOTAL_OCR_PAGES}, 호출 "
                        f"{MAX_VISION_CALLS_PER_REQUEST})에 도달해 이후 페이지는 건너뜁니다."
                    )
                    break
                page = doc[page_index]
                try:
                    page_png = _render_page_png(page)
                except Exception as error:  # noqa: BLE001
                    warnings.append(
                        f"{upload.filename} p{page_index + 1}: 렌더 실패({type(error).__name__})."
                    )
                    continue
                processed_pages += 1
                try:
                    page_image = _render_page_display_data_url(page)
                except Exception:  # noqa: BLE001 - 표시 이미지 실패가 추출을 막지 않게.
                    page_image = ""
                try:
                    session = get_session_factory()()
                except Exception as error:  # noqa: BLE001 - 페이지 실패 격리.
                    warnings.append(
                        f"{upload.filename} p{page_index + 1}: DB 세션 실패({type(error).__name__})."
                    )
                    continue
                try:
                    try:
                        content = _invoke_vision(
                            page_png,
                            budget=vision_budget,
                            db=session,
                            workspace_id=workspace_id,
                            actor_user_id=actor_user_id,
                            fewshot=prompt_hint,
                        )
                    except Exception as error:  # noqa: BLE001 - 페이지 실패 격리.
                        warnings.append(
                            f"{upload.filename} p{page_index + 1}: OCR 호출 실패({type(error).__name__})."
                        )
                        continue
                    payload = _parse_json_object(content)
                    if payload is None:
                        warnings.append(f"{upload.filename} p{page_index + 1}: 결과 파싱 실패.")
                        continue
                    try:
                        if vision_budget.available:
                            row_counts: list[tuple[int, int]] = []
                            _rescan_band_into_payload(
                                page_png,
                                payload,
                                db=session,
                                workspace_id=workspace_id,
                                actor_user_id=actor_user_id,
                                catalog=catalog,
                                budget=vision_budget,
                                row_counts=row_counts,
                            )
                            # 재판독이 1차보다 '더 많은' 행을 읽었을 때만 경고한다. 결과 행은 1차에서
                            # 나오므로, 1차가 인접한 두 행을 하나로 합쳤을 때만 실제로 데이터가 사라진다.
                            #
                            # 반대 방향(재판독이 더 적게 읽음)은 경고하지 않는다. 손글씨 사진 명세표에서는
                            # 재판독이 중간에 끊기거나 행을 흘리는 일이 흔해(실측: 손글씨 14행 → 재판독
                            # 10행) 매번 경고가 떠 진짜 경고가 묻힌다. 이 경우 1차가 더 완전한 판독이라
                            # 결과에서 빠진 행은 없다.
                            # 문구는 어느 회차가 틀렸다고 단정하지 않는다. 1차가 두 행을 합쳤을 수도,
                            # 재판독이 줄바꿈된 한 행을 둘로 쪼갰을 수도 있고 둘을 구분할 근거가 없다.
                            # 검수자가 할 수 있는 유일한 판정은 '원본의 행 수를 세어 보는 것'이므로 그것만
                            # 요청한다.
                            for pass1_rows, pass2_rows in row_counts:
                                if pass2_rows > pass1_rows:
                                    warnings.append(
                                        f"{upload.filename} p{page_index + 1}: 표의 행 수 판독이 "
                                        f"엇갈립니다(추출 {pass1_rows}행, 재판독 {pass2_rows}행). "
                                        f"원본의 품목 줄 수가 {pass1_rows}개인지 확인하세요."
                                    )
                        elif _has_rescan_band(payload):
                            warnings.append(
                                f"{upload.filename} p{page_index + 1}: 재판독 생략"
                                f"(OCR 호출 상한 {MAX_VISION_CALLS_PER_REQUEST})."
                            )
                    except Exception as error:  # noqa: BLE001 - pass-1 결과는 유지.
                        warnings.append(
                            f"{upload.filename} p{page_index + 1}: 재판독 실패({type(error).__name__})."
                        )
                    try:
                        built = _document_from_payload(
                            payload,
                            filename=upload.filename,
                            page_no=page_index + 1,
                            page_image=page_image,
                        )
                        final_doc = annotate_catalog(annotate_vocab(built, vocab), catalog)
                        # 사전·카탈로그 뒤에 과거 확정 교정을 적용한다(정확 일치는 자동 적용, 유사는 후보).
                        # 사전/카탈로그를 함께 넘겨, 실재 품목으로 읽힌 이름을 오독으로 단정하지 않게 한다.
                        if aliases:
                            _apply_vendor_aliases(
                                final_doc, aliases, vocab=vocab, catalog=catalog
                            )
                        documents.append(final_doc)
                    except Exception as error:  # noqa: BLE001 - 페이지 실패 격리.
                        warnings.append(
                            f"{upload.filename} p{page_index + 1}: 결과 조립 실패({type(error).__name__})."
                        )
                finally:
                    try:
                        session.close()
                    except Exception as error:  # noqa: BLE001 - 페이지 실패 격리.
                        warnings.append(
                            f"{upload.filename} p{page_index + 1}: DB 세션 종료 실패"
                            f"({type(error).__name__})."
                        )
        finally:
            try:
                doc.close()
            except Exception as error:  # noqa: BLE001 - 파일 실패 격리.
                warnings.append(f"{upload.filename}: 문서 종료 실패({type(error).__name__}).")
    return MealInvoiceExtractResponse(documents=documents, warnings=warnings)
