"""Static configuration for the news aggregator.

Ported verbatim from the legacy Flask portal (``C:\\server\\config.py`` and
``routes/news.py``) so collection behaviour matches the original feature: the
same DWD-Auto core-tech / industry keyword sets, the same eight front-page
newspapers, and the same brand-expansion + source-mapping tables.
"""
from __future__ import annotations

# ── Keyword channel ──────────────────────────────────────────
SEARCH_KEYWORDS: list[str] = [
    # 두원공조 핵심 기술
    "자동차 공조", "차량 에어컨", "카컴프레서", "차량 열관리",
    "히트펌프 자동차", "HVAC 차량", "열교환기", "차량용 열교환기",
    # 자동차 산업
    "전기차", "현대차", "배터리", "자율주행",
    "하이브리드차", "기아자동차", "테슬라", "BYD",
]

EXCLUDE_KEYWORDS: list[str] = ["광고", "협찬", "이벤트", "PR"]

# ── Front-page channel ───────────────────────────────────────
FRONT_PAGE_PAPERS: list[dict[str, str]] = [
    {"name": "조선일보", "oid": "023"},
    {"name": "조선Biz", "oid": "366"},
    {"name": "매일경제", "oid": "009"},
    {"name": "한국경제", "oid": "015"},
    {"name": "MBC", "oid": "214"},
    {"name": "KBS", "oid": "056"},
    {"name": "YTN", "oid": "052"},
    {"name": "중앙일보", "oid": "025"},
]

# ── Car channel ──────────────────────────────────────────────
CAR_KEYWORDS: list[str] = [
    # 차량 유형
    "자동차", "車", "전기차", "EV", "하이브리드", "SUV", "친환경차",
    # 국내 브랜드
    "현대차", "기아", "제네시스",
    # 해외 브랜드
    "테슬라", "BYD", "샤오미", "토요타", "BMW", "벤츠",
    # 핵심 기술
    "배터리", "자율주행", "수소전기차",
    # 두원공조 관련
    "차량 공조", "카에어컨", "열관리시스템", "히트펌프",
]

# Seed search keywords for the car channel (legacy ``_collect_car``).
CAR_SEARCH_KEYWORDS: list[str] = ["전기차", "하이브리드", "수소전기차", "자율주행", "배터리"]

# Default UI filter chips for the keyword channel (legacy default).
DEFAULT_KEYWORD_UI_FILTERS: list[str] = [
    "공조시스템", "컴프레서", "냉각수 밸브", "차량 열관리", "차량용 열교환기",
]

MAX_IMAGES_PER_ARTICLE = 5
MIN_IMAGE_WIDTH = 300

# ── Front-page source strategy (legacy ``_crawl_newsstand_main``) ─
# Newspaper RSS feeds the publisher runs directly.
RSS_MAP: dict[str, str] = {
    "023": "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",  # 조선일보
    "009": "https://www.mk.co.kr/rss/30000001/",                            # 매일경제
    "015": "https://www.hankyung.com/feed/all-news",                        # 한국경제
}
# Newspaper homepages scraped directly (url, css selectors).
HOMEPAGE_MAP: dict[str, tuple[str, list[str]]] = {
    "366": ("https://biz.chosun.com", ["a[class*=headline]"]),  # 조선Biz
    "025": (
        "https://www.joongang.co.kr",
        ["strong.headline", ".card_title a", "h2.tit a"],
    ),  # 중앙일보
}
# JS-rendered publishers fetched through the Naver media press page.
NAVER_MEDIA_OIDS: set[str] = {"214", "056", "052"}  # MBC, KBS, YTN

# ── Car brand expansion (legacy ``CAR_BRAND_MAP``) ───────────
CAR_BRAND_MAP: dict[str, list[str]] = {
    "현대차": ["현대차", "현대자동차", "Hyundai"],
    "현대": ["현대차", "현대자동차", "Hyundai"],
    "기아": ["기아", "기아차", "KIA"],
    "기아차": ["기아", "기아차", "KIA"],
    "제네시스": ["제네시스", "Genesis"],
    "테슬라": ["테슬라", "Tesla", "TESLA"],
    "BMW": ["BMW"],
    "벤츠": ["벤츠", "Mercedes-Benz", "Mercedes"],
    "아우디": ["아우디", "Audi"],
    "폭스바겐": ["폭스바겐", "Volkswagen", "VW"],
    "도요타": ["도요타", "Toyota"],
    "혼다": ["혼다", "Honda"],
    "닛산": ["닛산", "Nissan"],
    "BYD": ["BYD", "비야디"],
    "비야디": ["BYD", "비야디"],
    "샤오미": ["샤오미", "Xiaomi"],
    "GM": ["GM", "제너럴모터스"],
    "포드": ["포드", "Ford"],
    "볼보": ["볼보", "Volvo"],
    "Geely": ["Geely", "지리"],
    "지리": ["Geely", "지리"],
    "토요타": ["토요타", "Toyota"],
    "스텔란티스": ["스텔란티스", "Stellantis"],
    "리비안": ["리비안", "Rivian"],
    "루시드": ["루시드", "Lucid"],
    "포르쉐": ["포르쉐", "Porsche"],
}

# Domain → newspaper display-name mapping (legacy ``_extract_source``).
SOURCE_DOMAIN_MAP: dict[str, str] = {
    "chosun.com": "조선일보",
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "joongang.co.kr": "중앙일보",
    "mbc.co.kr": "MBC",
    "kbs.co.kr": "KBS",
    "ytn.co.kr": "YTN",
}

# 수집/보관 기간(일) — 키워드·자동차·신문사 모두 오늘 포함 최근 N일 기준으로 통일.
RECENT_DAYS = 14

# Valid channel identifiers.
CHANNELS: tuple[str, ...] = ("keyword", "front", "car")

# ── AI 추천 뉴스 (큐레이션) ──────────────────────────────────
# AI가 수집된 기사 중 "우리 회사 아이템과 관련 있는 것"만 골라 저장할 때 쓰는
# 기준 프로필. 관리자가 화면에서 수정하면 NewsFilterSetting.ai_profile 에 저장되고,
# 비어 있으면 아래 기본값(두원공조)을 사용한다.
DEFAULT_AI_PROFILE = """\
회사: 두원공조 (DWD-Auto) — 자동차 공조/열관리 시스템 부품 전문 제조사.

주요 아이템·기술:
- 차량용 컴프레서(전동/사판식), 카에어컨, HVAC 모듈
- 열교환기(콘덴서/이배퍼레이터/라디에이터), 냉각수 밸브
- 전기차·수소차 통합 열관리 시스템, 히트펌프, 배터리 냉각

경쟁사: 한온시스템, Denso, Valeo, Mahle, Marelli, Sanden, BorgWarner.

관련 있다고 볼 기사(저장 대상):
1) 유사제품 — 위 아이템과 같은/유사한 부품·시스템(컴프레서·열교환기·열관리 모듈 등) 제품 소식
2) 기술내용 — 자동차 공조·열관리·전동화 관련 기술/연구/특허/표준 동향.
   완성차(현대차·기아·테슬라·BYD 등)의 전기차·전동화 전략, 전기차/배터리 열관리·냉각,
   히트펌프 등 두원공조가 부품을 공급하는 분야의 산업·기술 동향도 포함.
3) 경쟁사 — 위 경쟁사(한온시스템·Denso·Valeo 등)의 수주·신제품·투자·협력·인사 등 사업 동향

제외(저장하지 않음):
- 주가/시황/공시/증권 리포트 등 금융·투자 정보
- 단순 광고/홍보/이벤트
- 회사 아이템과 무관한 일반 뉴스
"""

# AI가 부여하는 관련성 사유 분류값.
AI_CURATE_REASONS: tuple[str, str, str] = ("유사제품", "기술내용", "경쟁사")

# 한 번의 큐레이션 실행에서 평가할 미평가 기사 최대 수(채널 합산). 14일치 전체를
# 한 번에 훑을 수 있도록 넉넉히 둔다. 한 번 평가한 기사는 ai_evaluated 로 건너뛴다.
AI_CURATE_MAX_ARTICLES = 400
# LLM 한 번 호출당 평가할 기사 수(로컬 모델 정확도/토큰 고려해 작게 배치).
AI_CURATE_BATCH_SIZE = 20

# AI 추천 뉴스 보관 기간(일). 매일 큐레이션이 누적되며 1년치를 유지하고,
# 발행일 기준 이 기간을 넘긴 AI 추천 기사는 자동 정리한다(수동 저장 뉴스는 영구 보관).
AI_SAVED_RETENTION_DAYS = 365
