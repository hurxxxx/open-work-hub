"""PPT 자동 생성 — 양식(Family) 카탈로그.

각 family는 캔버스 크기, 빌더, 본문 layout 후보, fixed body 수, 로고 자산을 보유한다.
빌더는 순수 python-pptx 모듈(``design/builders_169.py``, ``design/builders_a4.py``)이며
로고 자산은 패키지 상대 경로(``design/assets/``)로 해결한다.

(corporate-v2 16:9 / a4-progress / a4-exec-kpi / a4-scorecard / a4-minutes 양식은
 빌더·프롬프트는 남아 있으나 카탈로그에서 제외됨)
"""

from __future__ import annotations

from open_alm_api.domains.ppt_generator.design.builders_a4 import (
    LAYOUT_BUILDERS_A4,
    build_slide_a4,
)
from open_alm_api.domains.ppt_generator.design.builders_a4 import SLIDE_H as SLIDE_H_A4
from open_alm_api.domains.ppt_generator.design.builders_a4 import SLIDE_W as SLIDE_W_A4
from open_alm_api.domains.ppt_generator.design.builders_brandlogy import (
    LAYOUT_BUILDERS_BRANDLOGY,
    build_slide_brandlogy,
)
from open_alm_api.domains.ppt_generator.design.builders_house import (
    LAYOUT_BUILDERS_HOUSE,
    build_slide_house,
)
from open_alm_api.domains.ppt_generator.design.builders_house import SLIDE_H as SLIDE_H_HOUSE
from open_alm_api.domains.ppt_generator.design.builders_house import SLIDE_W as SLIDE_W_HOUSE

LOGO_PATH_A4: None = None

SLIDE_RANGE_MAP = {
    "1-5": (1, 5),
    "6-10": (6, 10),
    "11-15": (11, 15),
    "16-20": (16, 20),
}

FAMILIES: dict[str, dict] = {
    # Open ALM 사내 진행보고 "하우스 스타일"(SPEC_house_style.md) 데이터 드리븐 렌더러.
    # 28×19.43cm, 단일 layout(house-report) N장. 각 슬라이드 data = {no,title,tag,meta,blocks}.
    # 생성은 design=="house" 분기로 LLM 이 블록 JSON 을 뱉고, finalize 가 builders_house 로 렌더.
    "corporate-house": {
        "name": "Open ALM 진행보고 (하우스 스타일)",
        "aspect": "A4",
        "slide_w": SLIDE_W_HOUSE,
        "slide_h": SLIDE_H_HOUSE,
        "builders": LAYOUT_BUILDERS_HOUSE,
        "build_fn": build_slide_house,
        "cover_layout": "house-report",
        "body_layouts": ["house-report"],
        "multi_body": True,
        "logo_path": LOGO_PATH_A4,
        "design": "house",
    },
    # ("자유 양식 (Brandlogy)", "Open ALM 양식(자유 본문, corporate-free)", "사양 비교(corporate-qwen)"
    #  양식은 카탈로그에서 제거됨. 생성 분기·프롬프트·렌더러 코드는 세미나 등이 재사용하므로
    #  남겨둔다. 다시 노출하려면 아래 형태의 family 항목을 복원하면 된다.)
    # 세미나 참석 보고 — Open ALM 표지/본문 틀 + Qwen 자동채움. 본문 1장(정보헤더+주요내용표+소감).
    # 생성은 design=="corporate-seminar" 분기(단일 채움 콜).
    "corporate-seminar": {
        "name": "세미나 & 출장 보고서",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_BRANDLOGY,  # 미사용(HTML 경로)
        "build_fn": build_slide_brandlogy,  # 미사용(HTML 경로)
        "cover_layout": "brandlogy",
        "body_layouts": ["brandlogy"],
        "multi_body": False,
        "fixed_body_n": 2,
        "logo_path": LOGO_PATH_A4,
        "design": "corporate-seminar",
    },
    # 교육 참가 보고 — Open ALM 표지/본문 틀 + Qwen 자동채움. 본문 1장(구분/내용/비고 표).
    # 생성은 design=="corporate-education" 분기(단일 채움 콜).
    "corporate-education": {
        "name": "교육 참가 보고서",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_BRANDLOGY,  # 미사용(HTML 경로)
        "build_fn": build_slide_brandlogy,  # 미사용(HTML 경로)
        "cover_layout": "brandlogy",
        "body_layouts": ["brandlogy"],
        "multi_body": False,
        "fixed_body_n": 1,
        "logo_path": LOGO_PATH_A4,
        "design": "corporate-education",
    },
    # 회의록 — Open ALM 세로 A4 회의록 양식. 회의 메모·문서를 머리표와 회의내용으로 정리.
    # 생성은 design=="corporate-meeting" 분기(단일 채움 콜, 표지 없는 세로 1장 HTML).
    "corporate-meeting": {
        "name": "회의록",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_BRANDLOGY,  # 미사용(HTML 경로)
        "build_fn": build_slide_brandlogy,  # 미사용(HTML 경로)
        "cover_layout": "brandlogy",
        "body_layouts": ["brandlogy"],
        "multi_body": False,
        "fixed_body_n": 1,
        "logo_path": LOGO_PATH_A4,
        "design": "corporate-meeting",
    },
}

DEFAULT_FAMILY = "corporate-house"

# 카탈로그에서 제외됐지만 **이미 생성된 작업**이 여전히 참조할 수 있는 레거시 양식.
# 카탈로그(템플릿 목록)에는 노출하지 않되(FAMILIES 에는 없음), finalize/chat-edit/build 경로가
# 옛 job.family(예: 'a4-exec-kpi' + a4-*-dashboard 레이아웃)를 계속 해석·빌드할 수 있어야
# 배포 후 "PPT로 전환"이 house 빌더로 잘못 실행돼 깨지는 것을 막는다. (resolve_family 만 이 맵을 본다.)
_LEGACY_FAMILIES: dict[str, dict] = {
    "a4-exec-kpi": {
        "name": "경영진 보고 — KPI 대시보드 (A4)",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_A4,
        "build_fn": build_slide_a4,
        "cover_layout": "a4-cover",
        "body_layouts": ["a4-exec-kpi-dashboard"],
        "multi_body": False,
        "logo_path": LOGO_PATH_A4,
        "hidden": True,
    },
    "a4-scorecard": {
        "name": "경영진 보고 — 사업부 스코어카드 (A4)",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_A4,
        "build_fn": build_slide_a4,
        "cover_layout": "a4-cover",
        "body_layouts": ["a4-division-scorecard"],
        "multi_body": False,
        "logo_path": LOGO_PATH_A4,
        "hidden": True,
    },
    "a4-minutes": {
        "name": "경영회의 회의록 (A4)",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_A4,
        "build_fn": build_slide_a4,
        "cover_layout": "a4-cover",
        "body_layouts": ["a4-meeting-minutes"],
        "multi_body": False,
        "logo_path": LOGO_PATH_A4,
        "hidden": True,
    },
    "a4-progress": {
        "name": "A4 진행 보고",
        "aspect": "A4",
        "slide_w": SLIDE_W_A4,
        "slide_h": SLIDE_H_A4,
        "builders": LAYOUT_BUILDERS_A4,
        "build_fn": build_slide_a4,
        "cover_layout": "a4-cover",
        "body_layouts": ["a4-progress"],
        "multi_body": True,
        "logo_path": LOGO_PATH_A4,
        "hidden": True,
    },
}

# resolve/build/finalize 는 카탈로그(FAMILIES) + 레거시(_LEGACY_FAMILIES) 모두를 해석 대상으로 본다.
_ALL_FAMILIES: dict[str, dict] = {**FAMILIES, **_LEGACY_FAMILIES}


def resolve_family(family: str | None) -> tuple[str, dict]:
    """알 수 없는 값이면 기본 family로 보정. (family_key, family_dict) 반환.

    카탈로그에서 숨긴 레거시 양식도 해석 대상에 포함해(_ALL_FAMILIES), 이미 생성된 옛 작업의
    finalize/chat-edit/build 가 house 빌더로 잘못 처리돼 깨지지 않게 한다.
    """
    key = family if family in _ALL_FAMILIES else DEFAULT_FAMILY
    return key, _ALL_FAMILIES[key]
