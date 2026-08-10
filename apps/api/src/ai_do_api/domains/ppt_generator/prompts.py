"""PPT 자동 생성 — LLM 프롬프트 구성 (양식별 layout 스키마 + 메시지 빌더).

Flask ``routes/pptgen2.py`` 의 프롬프트 로직을 그대로 이식했다. 각 family는 cover 1장 +
본문(doowon-v2는 N장, A4는 1장 고정) 구조의 슬라이드 JSON을 LLM이 생성하도록 안내한다.
"""

from __future__ import annotations

from pathlib import Path

from ai_do_api.domains.ppt_generator.families import (
    DEFAULT_FAMILY,
    SLIDE_RANGE_MAP,
    resolve_family,
)

# Brandlogy 디자인 시스템 전체 MD — Claude 레이아웃 설계 단계의 디자인 권위 텍스트.
# (요약본 _BRANDLOGY_SCHEMA 대신 전체를 주입해 claude.ai 수준의 설계 품질을 노린다.)
_DESIGN_MD_PATH = Path(__file__).parent / "design" / "brandlogy_design_system.md"


def _load_brandlogy_md() -> str:
    try:
        return _DESIGN_MD_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


_BRANDLOGY_MD = _load_brandlogy_md()

# ============================================================
# 각 layout의 data 스키마 — Doowon v2 명세, 4가지 본문 패턴 (16:9)
# ============================================================
_LAYOUT_SCHEMA = """\
사용 가능한 5개 layout과 각각의 data 필드:

1) "cover" — 표지 (반드시 첫 슬라이드, 1장만)
   data: { "TITLE": "발표 주제", "DATE": "YYYY.MM.DD" (선택, 빈값이면 오늘) }

2) "2col-comparison" — 좌 narrative + 우 옵션 비교 패널 (PTC vs Heat Pump 식)
   data: {
     "HEADER": "슬라이드 제목 (텍스트만, ▣ 기호 절대 넣지 말 것 — 빌더가 자동으로 붙임)",
     "SUBTITLE": "TREND 01 · 한 줄 요약" (선택),
     "WHY_NOW_LABEL": "WHY NOW",
     "LEAD_PARAGRAPH": "도입 단락 2~3줄",
     "LEFT_BULLETS": [{"TITLE": "...", "BODY": "..."}, x3],
     "PANEL1_LABEL": "BASELINE",
     "PANEL1_VALUE": "큰 값 (예: COP 1.0)",
     "PANEL1_NOTE": "보조 설명",
     "PANEL2_LABEL": "PROPOSED",
     "PANEL2_VALUE": "큰 값 (예: COP 3.2)",
     "PANEL2_NOTE": "보조 설명",
     "PANEL2_BADGE": "RECOMMENDED",
     "TAKEAWAY": "DOOWON 시사점 2줄"
   }

3) "benchmark-tiles" — 벤치마크 사례 + 4개 KPI 타일
   data: {
     "HEADER": "...", "SUBTITLE": "TREND 02 · ..." (선택),
     "INTRO": "도입 1~2줄",
     "BENCH_TITLE": "벤치마크 회사·사례",
     "BENCH_BODY": "벤치마크 설명",
     "TILES": [{"KPI": "70%", "LABEL": "...", "BODY": "..."}, x4],
     "TAKEAWAY": "DOOWON 시사점"
   }

4) "comparison-table" — 전체 폭 비교 표 + 듀얼 콜아웃
   data: {
     "HEADER": "...", "SUBTITLE": "TREND 03 · ..." (선택),
     "COLUMNS": ["항목", "옵션A", "옵션B", "옵션C", ...],
     "ROWS": [["행 라벨", "값", "값", "값"], ...],
     "RECOMMENDED_ROW": 2 (선택, 강조할 행의 0-based 인덱스),
     "INDUSTRY_SIGNAL": "좌측 콜아웃 본문 (산업 동향)",
     "SECURITY_NOTE": "우측 콜아웃 본문 (규제·보안 주의)",
     "TAKEAWAY": "DOOWON 시사점"
   }

5) "4step-framework" — 4단계 내러티브 + 결론 블록 (마지막 슬라이드 권장)
   data: {
     "HEADER": "전략 프레임워크",
     "SUBTITLE": "결론 · ..." (선택),
     "STEPS": [
       {"LABEL": "현황", "BODY": "..."},
       {"LABEL": "문제점", "BODY": "..."},
       {"LABEL": "AI 해결책", "BODY": "..."},
       {"LABEL": "기대 효과", "BODY": "..."}
     ],
     "CONCLUSION_TITLE": "결론 한 문장",
     "CONCLUSION_BODY": "결론 본문 2~3줄"
   }
"""

# ============================================================
# A4 패밀리 스키마 — 각 family는 cover 1장 + 본문 1장 (fixed)
# ============================================================
_A4_COVER_SCHEMA = """\
1) "a4-cover" — A4 표지 (반드시 첫 슬라이드, 1장)
   data: {
     "TITLE": "보고서 정식 제목 (예: 2026년 5월 경영회의 자료)",
     "DATE": "YYYY.MM.DD" (선택, 빈값이면 오늘),
     "AUTHOR": "작성 부서 (예: ㈜두원공조 기술연구소 AI TFT)",
     "VERSION": "Ver 1.x" (선택)
   }
"""

_A4_KPI_SCHEMA = (
    _A4_COVER_SCHEMA
    + """\

2) "a4-exec-kpi-dashboard" — A4 경영 KPI 대시보드 (본문 1장)
   data: {
     "HEADER": "본문 제목 (예: 2026년 5월 경영회의 보고서) — ▣ 절대 넣지 말 것",
     "DATE": "YYYY.MM.DD" (선택, 본문 우측 상단 표시),
     "KPIS": [
       {"label": "매출액", "value": "1,234", "unit": "억원",
        "up": true, "delta": "+12.4%", "vs": "전월 대비"},
       ... (총 4개, 순서: 매출/영업이익/매출원가율/품질이슈 같은 핵심 4개)
     ],
     "SUMMARY_TITLE": "핵심 요약" (선택),
     "SUMMARY_ITEMS": ["불릿 1", "불릿 2", "불릿 3", "불릿 4"] (4~6개),
     "CHART_TITLE": "월별 매출 추이 (억원)" (선택),
     "CHART_LABELS": ["1월", "2월", "3월", "4월", "5월"],
     "CHART_VALUES": [980, 1050, 1120, 1180, 1234],
     "ISSUES_TITLE": "주요 이슈" (선택),
     "ISSUES": [
       {"sev": "HIGH|MID|LOW", "title": "이슈 제목", "desc": "한 줄 설명"},
       ... (3~4개)
     ],
     "ACTIONS_TITLE": "차월 액션 아이템" (선택),
     "ACTIONS": [
       {"num": "01", "title": "액션 제목", "owner": "담당부서/담당자",
        "desc": "한 줄 설명"},
       ... (3~4개)
     ]
   }
"""
)

_A4_SCORECARD_SCHEMA = (
    _A4_COVER_SCHEMA
    + """\

2) "a4-division-scorecard" — A4 사업부 스코어카드 (본문 1장)
   data: {
     "HEADER": "본문 제목 (예: 사업부별 실적 스코어카드) — ▣ 절대 넣지 말 것",
     "DATE": "YYYY.MM.DD" (선택),
     "HEADLINE_EYEBROW": "EXECUTIVE HEADLINE" (선택, 영문 약어 OK),
     "HEADLINE_MAIN": "한 줄 결론 (예: HVAC·EV 사업부 호조, A/S 부진 만회 필요)",
     "HEADLINE_SUB": "부연 설명 1~2줄",
     "AGG_KPIS": [
       {"label": "전사 매출", "value": "3,520", "unit": "억원",
        "delta": "+8.2%", "up": true},
       ... (총 4개)
     ],
     "DIVISIONS": [
       {"name": "HVAC", "bold": false,
        "plan": 1200, "actual": 1284, "delta": "+7.0%", "delta_up": true,
        "status": "good"},
       {"name": "EV 컴프레서", "bold": false,
        "plan": 800, "actual": 760, "delta": "-5.0%", "delta_up": false,
        "status": "warn"},
       ... (5~6개; 마지막 행 "합계"는 bold=true)
       status는 "good"(양호) / "warn"(주의) / "bad"(부진) 중 하나
     ],
     "ISSUES_TITLE": "핵심 이슈 · 위험 신호" (선택),
     "ISSUES": [
       {"div": "사업부명 (짧게)", "title": "이슈 제목", "desc": "한 줄 설명"},
       ... (3개)
     ],
     "DECISIONS_TITLE": "차월 의사결정 사항" (선택),
     "DECISIONS": [
       {"q": "결정해야 할 질문", "owner": "결정권자 직책"},
       ... (3개)
     ]
   }
"""
)

_A4_MINUTES_SCHEMA = (
    _A4_COVER_SCHEMA
    + """\

2) "a4-meeting-minutes" — A4 경영회의 회의록 (본문 1장)
   data: {
     "HEADER": "본문 제목 (예: 2026년 5월 경영회의 회의록) — ▣ 절대 넣지 말 것",
     "DATE": "YYYY.MM.DD" (선택),
     "META_ITEMS": [
       {"label": "일시", "value": "2026.05.20 14:00~16:30"},
       {"label": "장소", "value": "본사 대회의실"},
       {"label": "참석", "value": "대표이사 외 8명"},
       {"label": "주관", "value": "기획실"}
     ],
     "AGENDAS": [
       {"num": "01", "title": "안건 제목",
        "discussion": "논의 내용 2~3줄",
        "decision": "결정 사항 1~2줄"},
       ... (정확히 3개)
     ],
     "ACTION_ITEMS": [
       {"no": "1", "task": "실행 항목", "owner": "담당",
        "due": "YYYY.MM.DD", "status": "planned"},
       ... (3~5개)
       status는 "in_progress"(진행 중) / "planned"(예정) / "done"(완료) 중 하나
     ],
     "NEXT_MEETING": "다음 회의 일정 (날짜 · 장소 · 주요 안건)",
     "SIGNOFF": "작성·검토자 (예: 작성 홍길동 / 검토 김부장)"
   }
"""
)

_A4_PROGRESS_SCHEMA = (
    _A4_COVER_SCHEMA
    + """\

2) "a4-progress" — A4 진행사항 보고 (본문 1장)
   data: {
     "HEADER": "본문 제목 (예: 스마트 팩토리 AI 도입 진행사항) — ▣ 절대 넣지 말 것",
     "DATE": "YYYY.MM.DD" (선택),
     "S1_LABEL": "한 줄 항목 라벨 (예: 목적)",
     "S1_TEXT": "한 줄 요약 문장 (~45자 이내)",
     "S2_LABEL": "4열 표 제목 (예: 개선 방법)",
     "S2_HEADERS": ["열1", "열2", "열3", "열4"],   (정확히 4개)
     "S2_COL0": ["행1", "행2"],   (1열 항목들 — 가운데 정렬, 짧게)
     "S2_COL1": ["행1", "행2"],   (2열 항목들 — 가운데 정렬, 짧게)
     "S2_COL2": ["불릿 1", "불릿 2"],   (3열 — 좌측 정렬)
     "S2_COL3": ["1. ...", "  - ...", "2. ..."],   (4열 다중 줄 — 좌측 정렬, 최대 7줄)
     "S3_LABEL": "다행 표 제목 (예: 주차별 적용 계획)",
     "S3_HEADERS": ["열1", "열2", "열3", "열4"],   (정확히 4개)
     "S3_ROWS": [
       ["값", "값", "긴 내용 (~28자)", "상태"],
       ...   (행 6개 내외 — 리스트 길이만큼 자동 증감)
     ],
     "S4_LABEL": "타임라인 제목 (예: 진행 현황)",
     "S4_NODES": [
       ["단계명 (~10자)", "(날짜)", "done"],
       ["단계명", "(날짜)", "now"],
       ["단계명", "(날짜)", "todo"],
       ...   (노드 6~9개 권장)
     ]
     S4_NODES 상태값: "done"(완료·검정 채움) / "now"(진행중·반원) / "todo"(예정·흰 원)
   }
"""
)

# ============================================================
# 자유 양식 — Brandlogy 디자인 시스템 (27 × 16.75 cm, 자유 배치)
# 슬라이드는 단일 layout "brandlogy" 하나. 헤드라인/부제는 잠금 존이고,
# 본문 박스(3.68~16.05cm) 안에만 ELEMENTS 를 cm 좌표로 자유 배치한다.
# ============================================================
_BRANDLOGY_SCHEMA = """\
[캔버스] 27 × 16.75 cm (가로). 모든 좌표 단위는 cm, 소수점 허용. 원점은 좌상단(0,0).

[잠금 존 — 좌표 자동, 손대지 말 것]
- 상단 여백 0 ~ 0.76 cm (비움)
- 헤드라인(대제목) 0.76 ~ 2.34 cm
- 부제(부제목) 2.34 ~ 3.30 cm
- 본문 박스 3.68 ~ 16.05 cm  ← ELEMENTS 는 반드시 이 안에만 배치
- 하단 여백 16.05 ~ 16.75 cm (비움)
헤드라인·부제는 data 의 HEADLINE / SUBTITLE 필드로만 주고, 좌표·폰트는 시스템이 자동 처리한다.
표지(첫 슬라이드)는 EYEBROW(윗줄 라벨) + 큰 HEADLINE + SUBTITLE + 본문 박스에 히어로 카드/목차.

[본문 박스 좌표 범위]
- 가로: x = 0.9 ~ 26.1 (폭 25.2). 요소 우측 끝(x+w) ≤ 26.1.
- 세로: y = 3.68 ~ 16.05 (높이 12.37). 요소 하단(y+h) ≤ 16.05.
- 본문 박스를 위에서 아래까지 꽉 채울 것(상·하단에 빈 띠 금지). 카드 간 간격 0.4~0.6cm.

[색상] 흰 캔버스(#ffffff) 기본. 브랜드 블루 #1456f0 / #3b82f6 / #60a5fa. 텍스트 #222222,
보조 텍스트 #45515e, 캡션 #8e8e93, 경계선 #e5e7eb / #f2f3f5. 분홍 #ea5ec1 은 장식 강조만.
히어로 그래디언트(linear 135° #1456f0→#3b82f6→#60a5fa)는 덱 전체 최대 3곳, 슬라이드당 1개,
표지 히어로 카드 / 강조 KPI 1개에만. 차트·본문 텍스트엔 절대 금지.

[타이포] 가중치로 위계: 700(숫자·강조) / 600(카드 제목) / 500(부제·라벨) / 400(본문).
본문 9.5~11pt, 카드 제목 14~16pt, KPI 숫자 26~38pt, 캡션 8.5~9pt.

[ELEMENTS — 본문 박스에 배치할 컴포넌트. 각 요소는 type + x,y,w,h(cm) + 타입별 필드]

1) "text" — 텍스트 블록(소제목/본문/콜아웃). 카드 배경 옵션 포함.
   { "type":"text", "x","y","w","h",
     "TEXT":"여러 줄은 \\n 로 구분",
     "SIZE":11, "WEIGHT":400, "COLOR":"#222222",
     "ALIGN":"left|center|right", "VALIGN":"top|middle",
     "LINE_HEIGHT":1.45,
     "FILL":"#f2f3f5"(선택, 카드 배경) , "RADIUS":13(px, FILL 있을 때),
     "SHADOW":"none|standard|glow"(선택), "BORDER":"#e5e7eb"(선택), "PAD":0.4(cm 내부여백) }

2) "kpi" — KPI 타일(숫자 강조). 내부 레이아웃 자동.
   { "type":"kpi", "x","y","w","h",
     "VALUE":"1,234", "UNIT":"억원", "LABEL":"매출액",
     "DELTA":"+12.4%"(선택), "UP":true(증가=파랑/감소=분홍),
     "FEATURED":false (true 면 히어로 그래디언트 배경+흰 글씨, 슬라이드당 최대 1개) }

3) "chart" — 차트. 내부 제목/축/캡션 자동.
   { "type":"chart", "x","y","w","h",
     "CHART":"bar|hbar|line|donut",
     "TITLE":"월별 매출 추이 (억원)",
     "LABELS":["1월","2월","3월","4월","5월"],
     "SERIES":[{"name":"매출","values":[980,1050,1120,1180,1234],"color":"#3b82f6"}],
     "SOURCE":"출처: 사내 집계"(선택) }
   막대/선은 평면 브랜드 블루만. 그래디언트 금지.

4) "table" — 표.
   { "type":"table", "x","y","w","h",
     "COLUMNS":["항목","1분기","2분기","3분기"],
     "ROWS":[["매출","980","1050","1120"], ...],
     "HIGHLIGHT_ROW":1 (선택, 강조할 0-based 행) }

5) "bullets" — 불릿 목록(선택적 카드 제목).
   { "type":"bullets", "x","y","w","h",
     "TITLE":"핵심 요약"(선택), "ITEMS":["불릿 1","불릿 2","불릿 3"],
     "SIZE":11, "FILL":"#ffffff"(선택 카드), "RADIUS":13, "SHADOW":"standard" }

6) "pill" — 알약형 라벨/태그.
   { "type":"pill", "x","y","w","h", "TEXT":"WHY NOW", "STYLE":"dark|nav|light" }

7) "steps" — 가로 단계 흐름(번호 원 + 라벨 + 한 줄).
   { "type":"steps", "x","y","w","h",
     "ITEMS":[{"LABEL":"현황","BODY":"한 줄 설명"}, ... (3~5개)] }

8) "divider" — 가로 구분선.
   { "type":"divider", "x","y","w", "COLOR":"#e5e7eb" }

[배치 가이드 — Brandlogy 본문 패턴]
A) KPI Strip + 상세: 상단에 kpi 3~4개(폭 ~5.9, 높이 ~2.6, y≈3.9), 하단에 chart + text 콜아웃.
B) 2단 비교: 좌(폭 ~12) text/bullets + 우(폭 ~12) chart, 하단 전폭 "So What" text 콜아웃.
C) 다이어그램 중심: 중앙 chart/steps 크게 + 주변 text 설명 + 하단 출처.
D) 프로세스: steps 가로 흐름 + 아래 결론 text.
E) 인용 + 근거: 좌 큰 text(인용) + 우 kpi/text 카드 2~3개.
F) 3단 적층(내용 적을 때): 상단 kpi 줄 / 중단 chart / 하단 text 카드 3개 — 빈 공간 제거.

데이터·비교·추세·구성·프로세스가 있으면 산문 대신 chart/table/steps 로 시각화할 것(시각화 우선).
"""

# 두원 사내 진행보고 "하우스 스타일"(SPEC_house_style.md §5) — 블록 데이터 모델 스키마.
# 각 슬라이드 = {"layout":"house-report","data":{no,title,tag,meta,blocks}}.
_HOUSE_SCHEMA = """\
[슬라이드 data 스키마]
{
  "no": <정수, 1부터>, "title": "<제목 ≤20자>", "tag": "<부제/태그 ≤24자>",
  "meta": { "date": "<YYYY. M. D>", "confidential": true, "total": <전체 슬라이드 수> },
  "blocks": [ <아래 블록들을 위에서 아래로 배치> ]
}

[블록 종류 — 내용에 맞는 것만 골라 쓴다. 표·차트를 억지로 만들지 말 것]
1) lead   — 슬라이드 목적 한 줄. {"type":"lead","label":"목적","text":"<한 줄 요약>"}
2) table  — 연파랑 헤더 + 전체 격자표. 비교·항목·역할·구성 등 **표로 정리할 데이터가 있을 때만**.
   {"type":"table","section":"<■섹션명>","colW":[열폭cm…],"align":["c"|"l"…],
    "header":["열제목"…],"rows":[[셀,셀,…],…]}
   - colW 합은 25.9 권장. align·header·각 row 의 길이는 열 개수와 정확히 일치.
   - **header 는 반드시 열 제목들의 배열** `["열1","열2"]` 입니다(문자열 하나로 쓰지 말 것 — 글자 단위로 쪼개집니다).
   - **각 row 는 셀 배열 `[셀, 셀, …]`(열 개수만큼)** 이어야 합니다. 한 행을 `{"lines":[...]}` 같은
     단일 셀로 감싸지 말고, **한 행의 값(예: 연도·판매·증가율·점유율)을 여러 행으로 쪼개지 마세요.**
     수치는 각자 자기 열에 한 셀씩 넣으세요(예: ["2025","20.7","+20%","25.5%"]).
   - align 은 "l"(왼쪽)/"c"(가운데)만. **"r"(오른쪽) 금지.** rowH 는 넣지 말 것(자동 계산).
   - **여러 대상을 같은 항목으로 비교하면 작은 2열 표를 여러 개로 쪼개지 말고, `구분 + 대상별 열`의
     "한 다열 표"로 합쳐 가로를 길게 쓰세요.** 예: 단일덕트 정풍량/재열/변풍량/이중덕트를 각각 작은
     2열 표로 만들지 말고 → header `["구분","CAV","재열","VAV","이중덕트"]`, rows `["특징",…]`,
     `["장점",…]`, `["단점",…]`, `["적용",…]` 처럼 **대상이 열, 비교 항목이 행**인 한 표로.
   - 열이 3~6개로 늘어도 좋습니다(가로 폭 가득 사용). 단 한 셀이 너무 길면 줄바꿈됨 — 핵심만.
   - **여러 안(案)·옵션을 비교**할 때(예: [1안]…/[2안]…/[3안]…)는 망설이지 말고 **슬라이드 한 장을
     통째로 채우는 큰 다열 표 하나**로 만드세요. 행은 비교 항목(구축형태/상세설명/장점/리스크/구성/
     예상금액 등), 열은 각 안. 표 하나가 본문 전체여도 좋습니다(다른 블록 억지로 추가 금지).
   - 단, **표 안에 도식·그림(상자+화살표)은 넣을 수 없습니다**(셀은 글자만). 도식이 필요한 항목은
     글로 설명하세요(예: 도식도 행 → "사내망 LLM·NAS·RAG ↔ 외부 Cloud GPU 대여").
   - 행이 7개를 넘거나 셀 내용이 길어 한 페이지를 넘길 것 같으면 항목을 추려 **한 장에 맞추세요**
     (한 표는 페이지 분할이 안 됨).  — **수치 데이터가 있을 때만**. PowerPoint 편집 가능한 네이티브 차트로 그려진다.
   {"type":"chart","section":"<■섹션명>","chart":"column|bar|line|pie|doughnut",
    "categories":["항목1","항목2",…],
    "series":[{"name":"계열명","values":[수,수,…]}, …]}
   - column=세로막대, bar=가로막대, line=꺾은선(추세), pie/doughnut=구성비. 막대/꺾은선은 다계열 가능.
   - pie/doughnut 는 series 1개만. values 길이는 categories 길이와 일치. 숫자만(단위·콤마 X).
4) text   — 표/차트로 만들 필요 없는 서술형 내용. {"type":"text","section":"<선택>","bullets":["항목1","항목2",…]}
   또는 {"type":"text","text":"<문단. 줄바꿈은 \\n>"}
   - **단, 하나의 주제 아래 '명칭: 설명' 형태 항목이 2개 이상**이면 text 불릿이 아니라
     **표(header ["구분","내용"])로 정리**하세요. 예: "히트펌프 통합: 폐열 회수 고도화" 같은
     항목 묶음은 각 명칭을 구분 열, 설명을 내용 열로 넣은 table 블록으로 만드세요.
5) timeline — 하단 마일스톤 화살표. {"type":"timeline","section":"진행 현황",
    "nodes":[{"label":"<단계명>","date":"<날짜>","state":"done|prog|todo"},…]}
   - state: 완료=done, 진행중=prog, 예정=todo. 노드 3~5개 권장.
   - **반드시 노드마다 구체적 날짜(예: '26.2/9, 7/31, 12/31)가 있는 실제 일정·진행 마일스톤일 때만**
     쓰세요. 날짜 없는 단순 단계·항목 나열에는 timeline 을 쓰지 말고 outline/table/text 로 하세요.
   - **남발 금지**: 한 보고서에서 timeline 은 날짜별 추진 일정이 진짜 있는 곳에만 1~2번. 장식용 금지.
6) (사용 금지) conclusion — 파란 한줄평. **만들지 마세요.** 결론·시사점은 text 나 표의 한 행으로 담으세요.
7) row — 두 블록을 **좌우 2단으로 나란히** 배치(가로 공백 제거용).
   {"type":"row","blocks":[<블록A>, <블록B>]}
   - blocks 에 위 1~6 블록 중 2개(최대 3개). **row 안에 row 를 다시 넣지 마세요**(중첩 금지) —
     세로로 쌓고 싶으면 블록을 같은 페이지 blocks 배열에 위아래로 따로 두세요.
   - **ratio 는 넣지 마세요** — 폭은 각 블록 내용에 맞춰
     자동 배분되어, 내용이 긴 표가 넓어지고 셀이 한 줄로 들어갑니다.
   - **원형/도넛 차트는 좁으니 반드시 row 로 옆에 표/text 를 둬** 좌우 여백을 없애세요.
   - **비교 표 2개를 row 로 좌우에 나란히 두지 마세요** — 같은 항목 비교면 위(2번)처럼 **한 다열 표로
     합치세요.** row 는 차트+표, text+표, 차트+timeline 처럼 **성격이 다른 블록**을 묶을 때만.
   - row 로 묶을 땐 **두 블록의 분량(높이)을 비슷하게** 맞추세요(한쪽이 짧으면 비어 보임).
8) compare — **큰 열 비교 그리드**(선택). 2~3개 대상을 여러 관점(행)으로 비교하면서 **각 열에 일정
   (타임라인)까지 한 판에** 담아야 할 때만 쓴다. 좌측은 행 라벨(구분), 각 열 셀은 텍스트 또는 타임라인.
   {"type":"compare","section":"<■섹션명>",
    "headers":["구분","(1) 대상A","(2) 대상B"],
    "rows":[
      {"label":"진행현황","cells":["<A 설명>","<B 설명>"]},
      {"label":"향후 계획","cells":["<A 계획>","<B 계획>"]},
      {"label":"일정","cells":[
        {"type":"timeline","nodes":[{"label":"단계","date":"날짜","state":"done|prog|todo"},…]},
        {"type":"timeline","nodes":[…]}]}
    ]}
   - headers 의 첫 항목은 라벨열 제목, 나머지는 비교 열 제목. 각 row 의 cells 길이는 비교 열 수와 일치.
   - 셀 텍스트는 문자열 또는 {"lines":["줄1","줄2"]}. **'일정' 행처럼 타임라인이 필요한 행에만** 셀에
     timeline 블록을 넣는다. **단순 비교 표면 table 을 쓰고, 열 비교 + 열별 일정이 함께일 때만 compare.**
9) outline — **번호가 붙는 계층 목록**. 대항목 아래 하위 항목이 여러 개 나열되는 내용일 때.
   {"type":"outline","section":"<■섹션명>",
    "items":[
      {"text":"<대항목>","level":1},
      {"text":"<하위 항목>","level":2},
      {"text":"<하위 항목>","level":2},
      {"text":"<다음 대항목>","level":1}]}
   - 렌더 계층: **■ 섹션명(대주제)** → **1) 2) …(소주제, level 1·굵게)** → **①②③(세부, level 2·상위마다 1부터 리셋)**.
   - **"주요 활동 내용 / 추진 현황 / 개발 내역 / 진행 항목"처럼 항목을 죽 나열하는 내용은 표나 불릿
     박스(text)로 만들지 말고 반드시 이 outline 으로 만드세요.** 작은 단순 나열을 테두리 박스 표로
     감싸지 않습니다. 표는 '여러 대상을 항목별로 비교'할 때만.
   - 예시(이 형태를 그대로 따르세요):
     {"type":"outline","section":"AI TFT팀 주요 활동 내용","items":[
       {"text":"고성능 PC 확보하여 반복 루틴 업무 개선 프로그램 두원 자체 개발중","level":1},
       {"text":"IMDS(국제재료데이터시스템) 핵심 광물 조사 프로그램 개발 완료","level":2},
       {"text":"과거차 문제점 AI 검색 기능 완료 (PLM DB 연결중)","level":2},
       {"text":"압축기 시험 DATA(성능/ES 시험결과) 자동 그래프 생성·가시화 완료","level":2},
       {"text":"회의록 자동 작성 전자기기(PLAUD) 구매하여 각 부서 업무에 활용중","level":1}]}
   - level 1 = 소주제(1) 2) … 자동 번호, 굵게), level 2 = 세부(①②③ 자동 번호, 상위마다 1부터 리셋).
   - 표로 만들 데이터가 아니라 **항목을 번호 매겨 위→아래로 나열**할 때 쓴다(서술 불릿 대신 구조가 보이게).

[강조 — 핵심 단어만 **굵게**(검정 유지)]
  - 강조는 **색·전체 볼드가 아니라, 핵심 단어를 `**...**` 로 감싸 그 단어만 굵게** 합니다.
    예: "전동 컴프레서 조립공정에서 **3대의 비전 카메라**를 이용하여 제품 **10개 기종**을 검출".
  - text/lead/표 셀/outline 어디서나 `**단어**` 가 인라인 볼드로 렌더됩니다(글자색은 검정 그대로).
  - 본문은 기본 검정·보통 글씨, **강조할 핵심어·수치만** `**...**`. 한 문장에 1~2군데로 절제.

[표 셀(Cell) 형태 — 4가지 허용]
  a) "문자열"  (강조는 셀 안에서 `**단어**`)
  b) {"lines":["1줄","2줄"],"al":"c"}                    # 여러 줄, 정렬 지정
  c) {"runs":[{"t":"1. ..."},{"t":"   - 상세"}]}        # 각 run=한 줄
  d) {"t":"완료","al":"c"}                                # 단일 셀
  - 본문 셀은 평범한 검정 글씨로 렌더됩니다(셀 단위 색·전체 볼드는 무시). **강조는 `**단어**`** 로만.
  - 셀 안 글머리: 번호 "1." / dash "- " / 소형 "▪".

[문체·어휘 — 두원 사내 보고서 톤(중요)]
- **개조식(명사·동사 어간 종결)**으로 짧고 압축적으로. 예: "…개발 완료", "…구축 진행중",
  "…적용 예정", "…반복업무 간소화". **"~합니다/~입니다/~한다" 같은 서술형 종결은 쓰지 마세요**
  (목적/리드 한 줄은 예외 허용).
- 주어·조사는 과감히 생략하고 **핵심 명사구 위주**로. 한 항목 = 한 줄, 군더더기 없이.
- 기술 용어·약어는 그대로 쓰되 **첫 등장 시 괄호로 풀이**. 예: "IMDS(국제재료데이타시스템)", "VAV(변풍량)".
- 인과·전후·개선은 **화살표 →** 로. 예: "S/W 자체 개발 → 개발비 절감", "4주 → 110분".
- 상태는 간결히: 완료 / 진행중 / 예정 / 검토. 기간·수치는 구체적으로 괄호 보충. 예: "(~8/21)", "(22개 문서)".
- 과장·홍보성 수식어 금지. 두원 실무 보고서처럼 **건조하고 사실 위주**로.
- **첨부·입력 자료에 기존 보고서 문장이 있으면, 그 어휘·말투·표현 방식을 최우선으로 따라 쓰세요**
  (자료의 용어·축약·문장 길이·어미를 그대로 흉내). 자료 톤이 곧 이 보고서 톤입니다.
- 표현 예시(말투만 참고, 내용은 복사하지 말 것):
  · "전동컴프 생산라인내 비전 AI 검사 공정 적용 (~8/21)"
  · "AI 비전 기술 내재화 (S/W 자체 개발 → 개발비 절감)"
  · "OEM 요청자료 반복업무 간소화 (22개 문서)"
  · "냉풍·온풍을 각각 전용 덕트로 보내 혼합상자에서 혼합 공급"
  · "개별 제어 가능, 냉난방 동시 처리, 환기량 일정"
  · "OA기기 고밀도 배치 사무실 등 현열부하가 큰 곳"

[작성 규칙]
- **내용에 맞는 블록만 사용**: 비교/항목이면 table, 수치/추세/구성비면 chart, 서술이면 text,
  단계/일정이면 timeline. **표나 차트를 만들 데이터가 없으면 굳이 만들지 말고** text/lead 로 구성.
- **셀·항목 내용을 한두 단어로 과하게 줄이지 마세요.** 개조식 톤은 유지하되, 핵심 근거·수치·조건·
  결과를 충분히 담아 **각 셀을 한두 구(句)로 실하게** 쓰세요(예: "설비비 큼" ❌ → "설비비 큼(혼합상자·
  이중덕트 공간), 냉온풍 혼합으로 에너지 손실 큼" ✅). 표가 너무 짧으면 빈약해 보입니다.
- **작은 표를 여러 개 나열하지 말고**, 같은 항목 비교는 다열 표 하나로 합쳐 **표 개수를 줄이고 폭을 길게**.
- 입력 자료에 없는 숫자/이름/날짜는 추측 금지 — 빈 문자열("") 또는 "추후 안내".
- **보안·기밀·AI 활용 관련 '유의사항/주의/경고/권고' 같은 메타 코멘트를 슬라이드에 넣지 마세요**
  (예: "외부 생성형 AI 에 기밀 입력 시 영업비밀 유출 위험", "온프레미스·데이터 마스킹 권고" 등).
  보고서 **주제 내용만** 담습니다.
- HEADER/제목에 ■ 기호를 넣지 말 것(섹션 ■ 는 렌더러가 자동으로 붙임)."""

_FAMILY_SCHEMAS = {
    "doowon-v2": _LAYOUT_SCHEMA,
    "doowon-house": _HOUSE_SCHEMA,
    "a4-exec-kpi": _A4_KPI_SCHEMA,
    "a4-scorecard": _A4_SCORECARD_SCHEMA,
    "a4-minutes": _A4_MINUTES_SCHEMA,
    "a4-progress": _A4_PROGRESS_SCHEMA,
    # 자유 양식 — Brandlogy 자유배치 스키마.
    "a4-free": _BRANDLOGY_SCHEMA,
}

_KO_RULES = """\
[언어 규칙] 모든 텍스트는 반드시 한글로만 작성. 한자(漢字)는 단 한 글자도 쓰지 말 것 — 한자어는 전부 한글로 적는다.
  예) 次世代→차세대, 强化/強化→강화, 投資→투자, 與否→여부, 戰略→전략, 確定→확정, 開發→개발, 等→등, 對備→대비, 卽시→즉시.
  일본 가나, 아랍 문자, 키릴 문자도 금지.
영어는 고유명사·약어(HVAC, IoT, EV, GWP)·단위(%, kg)에만 허용.

[간결성] 카드·이슈·의사결정 항목의 설명문/질문은 핵심만 담아 한 줄(약 35자 이내)로 짧게. 길게 풀어쓰지 말 것.

[사실 정확성] 입력 자료에 없는 전화번호·URL·날짜·금액·상품명은 추측하지 말고 생략하거나 "추후 안내"로 표기.

[중복 방지] 같은 슬라이드의 ▣ HEADER 와 SLIDE_TITLE 은 서로 다른 각도로 표현. 카드/번호 항목의 TITLE과 BODY 는 같은 내용 반복 금지.

[구성 규칙] 표지(cover) 1장 + 본문 슬라이드들 + (권장) 마지막에 conclusion. 같은 layout 연속 3회 이상 반복 금지.
"""


_BRANDLOGY_RULES = """\
[언어] 모든 텍스트 한글. 한자·일본 가나·키릴 금지. 영어는 고유명사·약어(HVAC, EV, AI)·단위(%, kg)만.
[사실] 입력 자료에 없는 숫자·날짜·금액·이름·URL 은 추측 금지. 생략하거나 "추후 안내".
[좌표] 모든 ELEMENTS 는 본문 박스(x 0.9~26.1, y 3.68~16.05) 안에. 겹침·박스 밖 배치 금지.
[밀도] 본문 박스를 위아래로 꽉 채울 것. 내용이 적으면 패턴 F(3단 적층)나 콜아웃·요약 띠로 채우되,
       장식용 빈 도형으로 가짜 밀도 만들지 말 것.
[시각화 우선] 비교·추세·구성·프로세스·관계는 산문 대신 chart/table/steps 로. 슬라이드당 차트 1~2개.
[그래디언트] 슬라이드당 히어로 그래디언트 1개 이하(표지 히어로 카드 또는 강조 KPI). 차트·텍스트엔 금지.
[중복 금지] HEADLINE 과 본문 카드 제목은 다른 각도로. 같은 문장 반복 금지.
"""


def _build_brandlogy_messages(
    *,
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
    include_title_slide: bool,
    schema: str,
) -> list[dict[str, str]]:
    """자유 양식(Brandlogy 27×16.75cm 자유배치) 슬라이드 생성 메시지."""
    n_slides = max(2, min(12, n_slides or 6))
    body_slides = n_slides - (1 if include_title_slide else 1)  # 표지 1장 고정

    sys_prompt = f"""당신은 Brandlogy 디자인 시스템을 따르는 프레젠테이션 자동 작성 어시스턴트입니다.
주어진 주제·자료를 27 × 16.75 cm 캔버스의 슬라이드 구조(JSON)로 만드세요.

응답은 **반드시 다음 JSON 객체** 만 출력(다른 텍스트·마크다운·코드블록 금지):
{{
  "slides": [
    {{ "layout": "brandlogy", "data": {{ "HEADLINE": "...", "SUBTITLE": "...", "EYEBROW": "...", "BG": "white", "ELEMENTS": [ ... ] }} }},
    ...
  ]
}}

모든 슬라이드의 layout 값은 "brandlogy" 하나입니다. data 필드:
- "HEADLINE": 대제목(잠금 존 자동 배치)
- "SUBTITLE": 한 줄 부제(잠금 존 자동 배치)
- "EYEBROW": 윗줄 작은 라벨(선택, 주로 표지)
- "BG": "white"(기본) | "dark"(섹션 구분/마무리) | "gradient"(표지 풀블리드, 덱 전체 1회)
- "ELEMENTS": 본문 박스에 자유 배치할 컴포넌트 배열(아래 스키마)

{schema}

요청 사항:
- 표지 1장 + 본문 {body_slides}장 = 총 {n_slides}장.
- 첫 슬라이드는 표지: EYEBROW + 큰 HEADLINE + SUBTITLE, 본문 박스엔 히어로 카드(FEATURED kpi 또는 그래디언트 text)와 목차/요약.
- 본문 슬라이드는 ELEMENTS 로 본문 박스를 꽉 채우고, 가능하면 chart/kpi/table 로 시각화.
- 언어: {language} / 톤: {tone}

{_BRANDLOGY_RULES if language == "Korean" else ""}
{instructions or ""}
"""

    user_prompt = f"""주제 / 입력 자료:
---
{content}
---

위 자료로 {n_slides}장짜리 Brandlogy 슬라이드 JSON 을 생성하세요. ELEMENTS 좌표는 cm 단위이며 본문 박스(x 0.9~26.1, y 3.68~16.05)를 벗어나지 마세요. JSON 객체 하나만 출력하고 다른 텍스트는 절대 넣지 마세요."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ============================================================
# 자유 양식 v2 — 3단계 파이프라인 (Qwen 브리프 → Claude 레이아웃 → Qwen 채우기)
#   1) Qwen: 입력 자료 → '구조 개요'(민감 수치 제외) 추출
#   2) Claude(Opus): 구조 개요 + Brandlogy 규칙 → 레이아웃 스켈레톤(기하+스타일+ROLE)
#   3) Qwen: 스켈레톤 ROLE + 실제 자료 → 내용 필드(인덱스별) 채움 → 서버가 병합
# ============================================================


# (1) Qwen — 구조 개요 추출
def build_brandlogy_brief_messages(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict[str, str]]:
    body_n = max(2, min(10, (n_slides or 6) - 1))
    sys_prompt = f"""당신은 발표 자료의 '구조 개요'를 추출하는 분석가입니다.
입력 자료를 읽고 발표의 구조만 JSON으로 출력하세요. 구체적인 수치·금액·날짜 같은 값은
개요에 넣지 말고(레이아웃 설계용이므로), 어떤 '근거의 종류'를 보여줄지만 기술하세요.

출력(JSON 객체 하나만, 코드블록·잡담 금지):
{{
  "title": "발표 제목(간결)",
  "audience": "발표 대상(예: 경영진, 팀장)",
  "goal": "발표 목적 한 줄",
  "sections": [
    {{"heading": "섹션 제목",
      "intent": "이 섹션이 전달할 핵심 한 줄",
      "evidence": ["근거 종류 태그", ...]}}
  ]
}}

evidence 태그(해당하는 것만 골라서, 그 섹션에서 시각화할 근거의 종류):
  "kpi"(핵심 수치 타일), "trend-chart"(추세 선/막대), "compare-chart"(비교 막대),
  "donut"(구성비), "table"(표), "bullets"(요점 목록), "steps"(단계 흐름),
  "quote"(인용·콜아웃), "text"(설명 문단)

규칙:
- 본문 섹션은 {body_n}개 내외. 표지·마무리 섹션은 만들지 말 것(시스템이 자동 추가).
- 각 섹션 evidence 는 1~3개.
- **중요**: 차트·수치 계열(kpi / trend-chart / compare-chart / donut / table)은
  입력 자료에 **실제 수치·데이터가 있는 섹션에만** 부여하세요. 수치가 없는 정성적 섹션은
  bullets / text / steps / quote 만 쓰세요. (없는 수치를 가정한 KPI/차트를 만들지 말 것.)
- 입력 자료 전반에 구체적 수치가 거의 없으면 차트/KPI 를 최소화하고 bullets/text/steps 중심으로.
- 언어: {language}.
{instructions or ""}
"""
    user_prompt = f"""입력 자료:
---
{content}
---
위 자료의 '구조 개요' JSON 하나만 출력하세요. 구체적 수치는 넣지 말고 구조와 근거 종류만."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


# (2) Claude — 레이아웃 스켈레톤 설계 (system, user) 튜플 반환
def build_brandlogy_layout_prompt(
    brief_json: str,
    n_slides: int,
    language: str,
) -> tuple[str, str]:
    design_authority = _BRANDLOGY_MD or _BRANDLOGY_SCHEMA
    sys_prompt = f"""당신은 Brandlogy 디자인 시스템 전문 프레젠테이션 디자이너입니다.
주어진 '구조 개요'를 바탕으로 27 × 16.75 cm 슬라이드 덱의 '레이아웃 스켈레톤'을 설계하세요.
당신의 역할은 레이아웃(슬라이드 구성, 각 요소의 종류·위치·스타일)입니다.
실제 문구·수치는 적지 말고, 각 요소에는 그 자리에 들어갈 내용을 설명하는 "ROLE" 만 적으세요.

═══════════════════════════════════════════════════════════
[디자인 시스템 — 아래 전체 사양을 권위 있는 기준으로 충실히 따르세요]
═══════════════════════════════════════════════════════════
{design_authority}

═══════════════════════════════════════════════════════════
[출력 계약 — 위 디자인을 아래 렌더러가 지원하는 형식으로만 표현]
═══════════════════════════════════════════════════════════
위 디자인 시스템의 미학·존·색·타이포·패턴을 최대한 반영하되, 최종 출력은 반드시
아래 element 스키마로만 표현하세요(렌더러가 지원하는 요소는 이게 전부입니다).
지원하지 않는 컴포넌트(프로스티드 글래스, 커스텀 도형 등)는 가장 가까운 element 로 매핑하세요.

{_BRANDLOGY_SCHEMA}

[출력 — JSON 객체 하나만, 코드블록·잡담 금지]
{{
 "slides": [
   {{"layout": "brandlogy", "data": {{
      "BG": "white|dark|gradient",
      "HEADLINE_ROLE": "이 슬라이드 대제목에 들어갈 내용 설명",
      "SUBTITLE_ROLE": "부제에 들어갈 내용 설명",
      "ELEMENTS": [
        {{"type":"kpi","x":0.9,"y":3.9,"w":5.9,"h":2.6,"FEATURED":false,"ROLE":"핵심 매출 지표(값·단위·라벨·증감)"}},
        {{"type":"chart","x":0.9,"y":7.0,"w":12.0,"h":8.5,"CHART":"bar","SERIES_N":1,"ROLE":"월별 추세, 시점 5개"}},
        {{"type":"table","x":13.5,"y":7.0,"w":12.0,"h":6.0,"COLS":3,"ROWS_N":4,"ROLE":"리스크 항목별 영향/대응"}}
      ]
   }}}}
 ]
}}

설계 규칙:
- 총 {n_slides}장. 첫 장은 표지(BG "gradient", FEATURED kpi 또는 큰 text + 목차/요약 카드),
  마지막 장은 마무리(BG "dark") 권장. 본문은 구조 개요의 각 섹션을 한 장씩 매핑.
- 각 본문 슬라이드는 해당 섹션의 evidence 를 알맞은 element type 으로 시각화하고
  좌표를 정확한 cm 로 지정. 모든 ELEMENTS 는 본문 박스(x 0.9~26.1, y 3.68~16.05) 안에,
  서로 겹치지 않게, 박스를 위아래로 꽉 채우도록 배치.
- 텍스트·숫자는 넣지 말 것. 내용 필드(VALUE/LABEL/TEXT/ITEMS/LABELS/SERIES/COLUMNS/ROWS 등)는
  비우고 ROLE 로만 설명. chart 엔 CHART(bar|hbar|line|donut)+SERIES_N, table 엔 COLS+ROWS_N 지정.
- 슬라이드당 차트 1~2개, 히어로 그래디언트는 표지/강조 KPI 1개에만(차트·텍스트엔 금지).
- 언어 라벨은 {language} 기준."""
    user_prompt = f"""구조 개요:
{brief_json}

위 구조 개요로 {n_slides}장짜리 Brandlogy 레이아웃 스켈레톤 JSON 하나만 설계해 출력하세요."""
    return sys_prompt, user_prompt


# (대안) Claude 단독 — 설계 + 내용을 한 번에 (Qwen 미사용)
def build_brandlogy_full_prompt(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
) -> tuple[str, str]:
    """Claude 가 레이아웃과 실제 내용까지 한 번에 작성하는 전체 생성 프롬프트 (system, user)."""
    design_authority = _BRANDLOGY_MD or _BRANDLOGY_SCHEMA
    sys_prompt = f"""당신은 Brandlogy 디자인 시스템 전문 프레젠테이션 디자이너이자 작성자입니다.
입력 자료를 바탕으로 27 × 16.75 cm 슬라이드 덱을 레이아웃과 실제 내용까지 완성해 JSON 으로 출력하세요.

═══════════════════════════════════════════════════════════
[디자인 시스템 — 아래 전체 사양을 권위 있는 기준으로 충실히 따르세요]
═══════════════════════════════════════════════════════════
{design_authority}

═══════════════════════════════════════════════════════════
[출력 계약 — 위 디자인을 아래 렌더러가 지원하는 형식으로만 표현]
═══════════════════════════════════════════════════════════
위 디자인 시스템의 미학·존·색·타이포·패턴을 최대한 반영하되, 최종 출력은 반드시
아래 element 스키마로만 표현하세요(렌더러가 지원하는 요소는 이게 전부입니다).
지원하지 않는 컴포넌트는 가장 가까운 element 로 매핑하세요.

{_BRANDLOGY_SCHEMA}

[출력 — JSON 객체 하나만, 코드블록·잡담 금지]
{{
 "slides": [
   {{"layout": "brandlogy", "data": {{
      "BG": "white|dark|gradient",
      "EYEBROW": "표지 윗줄 라벨(선택)",
      "HEADLINE": "실제 대제목",
      "SUBTITLE": "실제 부제 한 줄",
      "ELEMENTS": [ ... 실제 내용이 채워진 element 들 (ROLE 아님) ... ]
   }}}}
 ]
}}

작성 규칙:
- 총 {n_slides}장. 첫 장은 표지(BG "gradient"), 마지막 장은 마무리(BG "dark") 권장. 본문은 흰 배경.
- ELEMENTS 는 실제 내용 필드를 모두 채운다: text→TEXT, kpi→VALUE/UNIT/LABEL/DELTA/UP,
  bullets→TITLE/ITEMS, chart→CHART/LABELS/SERIES, table→COLUMNS/ROWS, steps→ITEMS, pill→TEXT.
- 모든 ELEMENTS 는 본문 박스(x 0.9~26.1, y 3.68~16.05) 안에, 겹치지 않게, 박스를 꽉 채우게 배치.
- **수치 날조 금지**: 입력 자료에 있는 수치만 사용. 없는 수치·증감률을 지어내지 말 것.
  수치가 없는 주제면 KPI/차트를 만들지 말고 bullets/text/steps/table(정성) 중심으로 구성.
- 슬라이드당 차트 1~2개, 히어로 그래디언트는 표지/강조 KPI 1개에만.
- 모든 텍스트 한글(한자·가나·키릴 금지, 영어는 약어·단위만). 톤: {tone}. 언어: {language}.
{instructions or ""}"""
    user_prompt = f"""입력 자료:
---
{content}
---
위 자료로 {n_slides}장짜리 Brandlogy 슬라이드 덱을 레이아웃과 실제 내용까지 완성해 JSON 객체 하나만 출력하세요."""
    return sys_prompt, user_prompt


# (대안 2) Claude 단독 — 슬라이드 덱을 HTML 문서로 직접 출력 (claude.ai 방식, 최고 품질)
# 슬라이드 픽셀: 1280 × 794 (27:16.75 ≈ 1.612 비율). 인쇄 시 1슬라이드=1페이지(PDF→pptx 변환용).
BRANDLOGY_HTML_SLIDE_W = 1280
BRANDLOGY_HTML_SLIDE_H = 794


def build_brandlogy_html_prompt(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
) -> tuple[str, str]:
    """Claude 가 슬라이드 덱을 자체 완결형 HTML 문서로 직접 출력하는 프롬프트 (system, user)."""
    design_authority = _BRANDLOGY_MD or _BRANDLOGY_SCHEMA
    w, h = BRANDLOGY_HTML_SLIDE_W, BRANDLOGY_HTML_SLIDE_H
    sys_prompt = f"""당신은 Brandlogy 디자인 시스템 전문 프레젠테이션 디자이너입니다.
아래 디자인 시스템을 충실히 따라, 입력 자료로 슬라이드 덱을 "하나의 자체 완결형 HTML 문서"로 만드세요.

═══════════════════════════════════════════════════════════
[디자인 시스템 — 권위 있는 기준]
═══════════════════════════════════════════════════════════
{design_authority}

═══════════════════════════════════════════════════════════
[출력 형식 — 자체 완결형 HTML]
═══════════════════════════════════════════════════════════
- 슬라이드 {n_slides}장. 각 슬라이드는 정확히 {w}px × {h}px 고정 크기(27 × 16.75cm, 약 1.612:1 비율)의
  ``<section class="slide">`` 한 개. 슬라이드는 세로로 나열.
- 반드시 다음 인쇄/페이지 규칙을 <style> 에 포함(나중에 PDF/PPTX 로 변환됨):
    @page {{ size: {w}px {h}px; margin: 0; }}
    html, body {{ margin: 0; padding: 0; background: #e9eef5; }}
    .slide {{ width: {w}px; height: {h}px; position: relative; overflow: hidden;
              background: #ffffff; box-sizing: border-box; }}
    .slide + .slide {{ margin-top: 24px; }}
    @media print {{ .slide {{ break-after: page; page-break-after: always; margin: 0; }} body {{ background:#fff; }} }}
- 폰트는 Pretendard. <head> 에 웹폰트 link 포함:
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.css">
  그리고 body font-family: 'Pretendard', -apple-system, system-ui, sans-serif.
- CSS 는 <style> 또는 인라인만. 외부 JS·외부 이미지 금지. 차트·다이어그램·아이콘은 인라인 SVG 또는 CSS 로 직접 그릴 것.
- 디자인 시스템의 존(헤드라인/부제/본문 박스)·색(#1456f0 등)·타이포·컴포넌트·히어로 그래디언트·
  본문 패턴(A~F)을 충실히 적용. 본문 박스를 위아래로 꽉 채울 것.
- **넘침(overflow) 금지 — 매우 중요**: 어떤 요소에도 `overflow:auto`·`overflow:scroll` 을 쓰지 말 것.
  스크롤바가 절대 생기면 안 된다. 모든 콘텐츠(특히 SVG 다이어그램·차트·표)는 슬라이드 {w}px × {h}px 안에
  100% 다 보이도록 크기를 맞춰라. 내용이 칸보다 크면 폰트·도형·여백을 줄이거나 요소를 둘로 나눠
  슬라이드 안에 들어오게 하라. SVG 는 `width:100%; height:100%`(또는 명시 px)로 부모 박스에 정확히 맞추고
  `viewBox` 로 비율을 잡아 잘리지 않게 할 것. 콘텐츠가 슬라이드를 벗어나는 일은 없어야 한다.
- **넘침(overflow) 금지 — 매우 중요**: 어떤 요소에도 `overflow:auto`·`overflow:scroll` 을 쓰지 말 것.
  스크롤바가 절대 생기면 안 된다. 모든 콘텐츠(특히 SVG 다이어그램·차트·표)는 슬라이드 {w}px × {h}px 안에
  100% 다 보이도록 크기를 맞춰라. 내용이 칸보다 크면 폰트·도형·여백을 줄이거나 요소를 둘로 나눠
  슬라이드 안에 들어오게 하라. SVG 는 `width:100%; height:100%`(또는 명시 px)로 부모 박스에 정확히 맞추고
  `viewBox` 로 비율을 잡아 잘리지 않게 할 것. 콘텐츠가 슬라이드를 벗어나는 일은 없어야 한다.

[시각화 규칙 — 가장 중요]
- 슬라이드를 "글상자(네모 칸)로만" 채우지 말 것. 각 내용을 가장 잘 전달하는 **시각 요소를 적극 그려라**:
  · 추세·실적 → 막대/선 차트(인라인 SVG)         · 구성·비중 → 도넛/파이 차트
  · 비교 → 좌우 비교 패널 또는 비교 표              · 절차·단계 → 번호 원 + 화살표 프로세스 흐름도
  · 관계·구조 → 노드·연결선 관계도/계층도/조직도    · 핵심 수치 → 큰 KPI 타일
  · 개념·분류 → SVG 아이콘이 들어간 카드 그리드(아이콘을 직접 그릴 것)
- **구체적 통계(금액·증감률 등)가 없어도, 개념을 설명하는 다이어그램·프로세스 흐름도·관계도·비교 시각화는 적극 만들어라.**
  이는 데이터 날조가 아니라 "구조의 시각화"다 — 칸으로만 나열하지 말고 시각적으로 풀어내라.
- 슬라이드마다 **최소 1개 이상의 의미 있는 시각 요소**(차트·다이어그램·KPI·아이콘 카드·타임라인 등)를 넣어
  단조로운 글상자 나열을 피할 것. 표지·마무리 슬라이드는 예외.

[내용 규칙]
- 구체적 "수치 데이터"(금액·증감률·날짜 등)는 입력 자료에 있는 값만 사용하고, 없는 값을 지어내지 말 것.
  (단, 수치가 없어도 위 시각화 규칙대로 개념 다이어그램·관계도·프로세스 흐름은 적극 그릴 것.)
  첫 장 표지, 마지막 장 마무리(어두운 배경) 권장.
- 모든 텍스트 한글(한자·가나·키릴 금지, 영어는 약어·단위만). 톤: {tone}. 언어: {language}.

[출력]
<!DOCTYPE html> 로 시작하는 **완전한 HTML 문서 전체만** 출력. 설명·마크다운·코드블록 금지.
{instructions or ""}"""
    user_prompt = f"""입력 자료:
---
{content}
---
위 자료로 {n_slides}장짜리 Brandlogy 슬라이드 덱을 HTML 문서 하나로 출력하세요."""
    return sys_prompt, user_prompt


# ============================================================
# 두원 양식(자유 본문) — 두원 표지/본문 틀 + Claude 본문 콘텐츠
#   Claude 는 "본문 칸(1244×754px)에 들어갈 콘텐츠"만 만든다. 표지·제목·날짜·로고·워터마크·
#   저작권 같은 틀은 절대 만들지 않는다(서버 doowon_frame 가 감쌈).
#   본문 디자인은 v3.9.1 §14 Information Design(Stripe+Bloomberg+Linear) 철학을 적용.
# ============================================================
from ai_do_api.domains.ppt_generator.design.doowon_frame import (  # noqa: E402
    BODY_H_PX as _BODY_H_PX,
)
from ai_do_api.domains.ppt_generator.design.doowon_frame import (  # noqa: E402
    BODY_W_PX as _BODY_W_PX,
)


def build_doowon_free_prompt(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
) -> tuple[str, str]:
    """두원 양식 본문 콘텐츠 생성 프롬프트 (system, user).

    Claude 는 본문 칸 전용 HTML 콘텐츠만 출력. 서버가 두원 표지/본문 틀로 감싼다.
    """
    bw, bh = _BODY_W_PX, _BODY_H_PX
    body_n = max(1, min(14, (n_slides or 6)))
    design_authority = _BRANDLOGY_MD or _BRANDLOGY_SCHEMA
    sys_prompt = f"""당신은 두원공조(DOOWON) 경영 보고서 본문을 디자인하는 프레젠테이션 디자이너입니다.
아래 디자인 시스템의 **시각 어휘(차트·다이어그램·KPI·카드·표·타이포·레이아웃 패턴)를 충실히 적용**해,
입력 자료를 본문 슬라이드들로 디자인하세요. **표지·제목 띠·날짜·로고·워터마크·배경 틀은 절대
만들지 마세요** — 그건 시스템이 자동으로 감쌉니다. 당신은 오직 **본문 칸 안의 콘텐츠만** 만듭니다.

═══════════════════════════════════════════════════════════
[디자인 시스템 — 시각 어휘·레이아웃 권위 기준 (충실히 따를 것)]
═══════════════════════════════════════════════════════════
{design_authority}

═══════════════════════════════════════════════════════════
[출력 형식 — 위 디자인을 "본문 칸"에 맞춰 출력]
═══════════════════════════════════════════════════════════
- <!DOCTYPE html> 로 시작하는 완전한 HTML 문서 하나. 설명·마크다운·코드블록 금지.
- <head> 에 <title>발표 전체 제목</title> + 본문 공통 CSS(<style>) 를 넣으세요.
- 본문 슬라이드 {body_n}장. 각 슬라이드는 정확히 다음 형태의 <section> 하나:
    <section class="doowon-body" data-title="슬라이드 제목" data-subtitle="(선택) 한 줄 부제">
      <div style="position:relative; width:{bw}px; height:{bh}px;"> ...본문 콘텐츠... </div>
    </section>
- 본문 콘텐츠 루트는 반드시 **{bw}px × {bh}px** 안에 100% 들어와야 합니다.
- CSS 는 <style> 또는 인라인만. 외부 JS·외부 이미지 금지. 차트·다이어그램·아이콘은 인라인 SVG/CSS 로.

═══════════════════════════════════════════════════════════
[두원 본문 규칙 — 위 디자인 시스템과 충돌 시 이쪽 우선]
═══════════════════════════════════════════════════════════
- **캔버스**: 디자인 시스템의 27×16.75 전체 캔버스·헤드라인/부제 잠금존·표지 규정은 **무시**.
  각 슬라이드 콘텐츠는 {bw}×{bh}px 본문 칸 하나에 자유 배치하고, **제목은 만들지 마세요**
  (data-title 로만 주면 틀의 제목 띠에 자동 표시). 콘텐츠 안에 제목을 다시 그리지 마세요.
- **색 오버라이드**: 브랜드 블루(#1456f0 등) 대신 **두원 네이비 #1B2C6B + 강조 레드 #D7261E**(강조 최대 2회)
  + 중립 회색/헤어라인(#E2E4E9). 배경 흰색. 히어로 그래디언트·그림자는 쓰지 말 것.
- **시각화 우선 — "칸만 채우지 말 것"**: 모든 슬라이드에 의미있는 시각요소를 최소 1개 그리세요.
  추세→막대/선 차트, 구성→도넛, 비교→비교패널/표, 절차→번호원+화살표 흐름도, 관계→노드·연결선
  다이어그램, 핵심수치→큰 KPI, 개념→아이콘 카드. 글자 목록만 나열하지 마세요. 구체 수치가 없어도
  개념 다이어그램·프로세스·관계도는 적극 그리세요(날조가 아니라 구조의 시각화).
- **위계·그리드**: 슬라이드마다 큰 히어로 1개 + 보조 요소들의 비대칭 구성(7+5/8+4/9+3/6+6). 균등 4칸 금지.
- **넘침 금지**: overflow:auto/scroll·스크롤바 금지. 내용이 칸보다 크면 폰트·여백을 줄이거나 둘로 나눠
  {bw}×{bh} 안에 100% 들어오게 하세요.
- **사실**: 구체 수치(금액·증감률·날짜)는 입력 자료에 있는 값만. 없는 값은 지어내지 마세요.
- 모든 텍스트 한글(한자·가나·키릴 금지, 영어는 약어·단위·라벨만). 톤: {tone}. 언어: {language}.
{instructions or ""}"""
    user_prompt = f"""입력 자료:
---
{content}
---
위 자료로 두원 양식 본문 {body_n}장을 위 형식의 HTML 문서 하나로 출력하세요.
표지·제목 띠·로고·워터마크·저작권은 만들지 말고, 각 <section class="doowon-body" data-title> 의
본문 콘텐츠({bw}×{bh}px)만 디자인하세요. <head> 에 <title> 로 발표 전체 제목을 넣으세요."""
    return sys_prompt, user_prompt


# ============================================================
# 두원 양식 (Qwen 자동) — 디자인은 서버 §14 템플릿, 내용만 Qwen JSON
# ============================================================
# Qwen 은 레이아웃을 직접 그리지 않는다. 슬라이드마다 (1) 패턴을 고르고 (2) 그 패턴이
# 요구하는 필드만 JSON 으로 채운다. 실제 §14 HTML 은 design/doowon_templates.py 가 만든다.

_QWEN_PATTERNS_GUIDE = """\
이 양식은 두원공조 **사양 비교 / 공용화 현황** 문서입니다. 슬라이드 패턴(pattern)을 내용에 맞게 고르세요:
- "spec_compare": 제품군별 사양 비교표. 그룹 컬럼(제품군→변형 모델) + 행라벨(라디에이터/콘덴서/중량 등) + 사양값.
  (예: SR vs BC4b 의 1.0FFV/1.0T/1.0TFFV 별 부품 사양·중량 비교)
- "commonization": 부품 공용화 현황표. 구분(라디에이터/콘덴서/점프튜브 등)별로 PART NAME 행을 묶고, 모델 컬럼마다 C/O·종 수 표기. (예: BC4b 쿨링모듈 공용화 현황)
- "component_grid": 구성 현황. 번호 달린 부품 카드(부품명 + 사양구성 표) + 가운데 조립 구성도. 모듈 구성 요소 나열에 사용.
- "schedule": 개발 일정 타임라인. 트랙(OEM 일정 / DCC 대응)별 마일스톤(날짜+이름).
- "issue_table": 문제점/개선 검토표. (선택)요약표 + 문제점·개선내용·반영내용 표.
- "bullets": 위에 안 맞는 설명/정리용 텍스트.
표에서 "←"=좌측과 동일, "-"=해당 없음, "N종"=종 수, "↓"=목표/감소 를 셀 값으로 그대로 쓰세요."""

# 패턴별 채움 JSON 스키마(Qwen 에게 그 슬라이드 패턴의 필드만 보여준다).
_QWEN_FILL_SCHEMAS = {
    "spec_compare": """\
{
  "title": "슬라이드 제목(▣ 기호 넣지 말 것)",
  "subtitle": "(선택) 한 줄 부제",
  "pattern": "spec_compare",
  "unit": "(선택) 단위 주석. 예: (단위 : mm)",
  "groups": [
    {"label": "제품군 이름(예: BC4b)", "cols": ["모델1","모델2"], "emphasis": true},
    {"label": "비교 제품군 이름(예: BR2)", "cols": ["모델1","모델2"]}
  ],
  "rows": {
    "라디에이터": ["값","값","...전체 모델 컬럼 순서대로..."],
    "콘덴서":     ["값","값","..."],
    "쿨링팬":     ["값","값","..."],
    "오일쿨러":   ["값","값","..."],
    "점프튜브":   ["값","값","..."],
    "기타":       ["여러 줄은 줄바꿈으로","...","..."]
  },
  "note": "(선택) ※ 로 시작하는 하단 주석"
}
각 행 cells 길이 = 모든 groups 의 cols 합(왼쪽 그룹부터 순서대로). emphasis:true 면 그 제품군이 파란 테두리 박스로 강조됨.
■ 행 주제는 **고정**(바꾸거나 추가·삭제 금지): 구 분 / 형 상 / 라디에이터 / 콘덴서 / 쿨링팬 / 오일쿨러 / 점프튜브 / 기타.
  "형 상" 은 사진 자리라 값 불필요(자동 ［형상］). 위 6개 행 이름을 rows 의 키로 그대로 쓰세요.
■ 유동(요청 자료로 채울 것): 제품군 이름(groups.label), 모델 컬럼(groups.cols), 각 고정 행의 셀 값.
  해당 없으면 "-", 좌측과 동일하면 "←", 종 수는 "N종". 자료에 없는 수치는 지어내지 말 것.""",
    "commonization": """\
{
  "title": "슬라이드 제목(예: BC4b 쿨링모듈 공용화 현황)",
  "subtitle": "(선택) 부제", "pattern": "commonization",
  "columns": ["KAPPA 1.0 FFV","KAPPA 1.0T FFV"],
  "merged_columns": [{"name":"KAPPA 1.0T","value":"←"}],
  "groups": [
    {"label":"라디에이터", "parts":[
        {"name":"CORE ASS`Y", "cells":["SX2 C/O","AY C/O"]},
        {"name":"TANK", "cells":["1종","1종"]},
        {"name":"SEAL PACK", "cells":["OS C/O","AY C/O"]} ]},
    {"label":"콘덴서", "parts":[
        {"name":"HEADER PIPE ASS`Y", "cells":["OS PE C/O","YDc C/O"]},
        {"name":"SIDE PLATE", "cells":["SX2 C/O","OS C/O"]} ]},
    {"label":"점프튜브", "parts":[
        {"name":"FLANGE ASS`Y", "cells":["1종","1종"]} ]}
  ],
  "footer": {"label":"공용화율", "cells":["42%(13종)","60%(23종)"]},
  "note": "(선택) 하단 주석"
}
구분(groups.label)별로 PART NAME 행을 rowspan 으로 묶음. columns = 셀별로 값을 채우는 모델 컬럼.
merged_columns = 전체 행이 동일한 모델 컬럼. 병합하지 않고 각 행마다 같은 value(예:"←")를 따로 표시. 없으면 [] 또는 생략.
각 part.cells 길이 = columns 길이. C/O(공용)·"1종"·"-" 등을 자료대로. footer(공용화율)는 선택. parts 는 구분당 2~15개.""",
    "component_grid": """\
{
  "title": "슬라이드 제목", "subtitle": "(선택) 부제", "pattern": "component_grid",
  "components": [
    {"no":"①", "name":"라디에이터", "variants":[{"spec":"610X409X12"},{"spec":"650X311.6X26"}]},
    {"no":"②", "name":"콘덴서", "variants":[{"spec":"630X385.6X12"},{"spec":"578X298X16"}]},
    {"no":"③", "name":"쿨링팬", "variants":[{"spec":"Ø420×140W"},{"spec":"Ø420×280W"}]}
  ],
  "note": "(선택) 하단 주석. 예: ※ 모터 : DY AUTO"
}
각 부품 카드는 "사양구성" 표(형상 사진 자리 + 사양 행)로 그려지고, variants 1~2개(변형별 사양 1열씩).
형상은 자동 ［형상］ 자리표시(사진 없음). no 는 ①②③… 권장. 4~8개. 가운데 조립 구성도 자리는 자동 생성.""",
    "schedule": """\
{
  "title": "슬라이드 제목", "subtitle": "(선택) 부제", "pattern": "schedule",
  "schedule_label": "개발 일정",
  "tracks": [
    {"name":"OEM 일정", "points":[
        {"date":"'24.10/31","label":"현시점","state":"current"},
        {"date":"'25.3/1","label":"PROTO(국내대응)","state":"future"},
        {"date":"'26.6/1","label":"M","state":"future"} ]},
    {"name":"DCC 대응", "points":[ {"date":"...","label":"...","state":"done|current|future"} ]}
  ],
  "table": {
    "row_label_header": "구 분",
    "columns": ["KAPPA 1.0 FFV","KAPPA 1.0T FFV","KAPPA 1.0T"],
    "rows": [
      {"label":"형상", "figure": true},
      {"label":"라디에이터", "cells":["610X409X12","650X311.6X26","←"]},
      {"label":"콘덴서", "cells":["...","...","..."]},
      {"label":"쿨링팬", "cells":["...","...","..."]},
      {"label":"오일쿨러", "cells":["-","495X33X20","-"]},
      {"label":"에어가이드", "cells":["1종","2종","←"]},
      {"label":"호스", "cells":["2종","5종","-"]}
    ]
  },
  "note": "(선택) 하단 주석"
}
상단 = 개발 일정 타임라인(트랙 1~2개, state: done/current=빨강·future=네이비), 하단 = 사양 비교표(선택).
표는 그룹 없이 단일 컬럼이며, 행(rows)은 자유롭게(이 페이지는 부품 구성이 1페이지와 다를 수 있음).
"형상" 행은 figure:true(사진 자리). cells 길이 = columns 길이. "←"=좌동, "-"=없음. table 없으면 타임라인만.""",
    "issue_table": """\
{
  "title": "슬라이드 제목", "subtitle": "(선택) 부제", "pattern": "issue_table",
  "summary": {"columns":["부품명","차종","점검 항목","무관","공정","검토 중","설계반영","비고"],
              "row":["COOLING MODULE","BC4b","98","30","7","1","60","-"], "highlight_col": 6},
  "issues": [
    {"no":"1","problem":"문제점 한 줄","improvement":"개선 내용","applied":"반영 내용","note":"전차종"}
  ],
  "note": "(선택) 하단 주석"
}
summary 는 없으면 생략 가능(highlight_col 은 강조할 컬럼 인덱스, 0부터). issues 3~6개 권장.""",
    "bullets": """\
{
  "title": "슬라이드 제목", "subtitle": "(선택) 부제", "pattern": "bullets",
  "groups": [ {"heading":"소제목", "items":["요점", ...]}, ... (1~4개) ]
}""",
}

_QWEN_SUPPORTED_PATTERNS = tuple(_QWEN_FILL_SCHEMAS.keys())


def build_doowon_qwen_outline_messages(
    content: str,
    n_body: int,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """두원(Qwen 자동) 1단계 — 덱 아웃라인(제목 + 슬라이드별 pattern/brief) JSON 메시지."""
    sys = f"""당신은 두원공조(DOOWON) 경영 보고서를 기획하는 컨설턴트입니다.
입력 자료를 본문 {n_body}장짜리 발표로 구성하기 위한 **아웃라인**만 JSON 으로 출력하세요.
디자인·HTML 은 절대 만들지 마세요(다른 단계가 처리). 표지는 세지 않습니다(본문 {n_body}장만).

{_QWEN_PATTERNS_GUIDE}

출력 JSON 형식(이것만, 설명·코드블록 금지):
{{
  "title": "발표 전체 제목(한 줄)",
  "slides": [
    {{"title": "슬라이드 제목(▣ 금지)", "pattern": "위 6개 중 하나", "brief": "이 슬라이드에서 다룰 핵심 내용 2~3줄(어떤 사양/부품/모델/일정을 넣을지)"}},
    ... 정확히 {n_body}개
  ]
}}
규칙: 첫 장은 제품군 사양 비교(spec_compare) 권장, 부품 공용화 리스트는 commonization,
모듈 구성은 component_grid, 개발 일정은 schedule, 문제점·개선은 issue_table, 그 외 설명은 bullets.
같은 패턴만 반복하지 말고 내용에 맞게 섞으세요. 사양 비교/공용화 표가 이 문서의 핵심이니 비중을 두세요.
모든 텍스트 한글({language}). 톤: {tone}. 수치·코드·모델명은 자료에 있는 것만, 없으면 지어내지 마세요."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = (
        f"입력 자료:\n---\n{content}\n---\n위 자료로 본문 {n_body}장 아웃라인 JSON 을 출력하세요."
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_doowon_qwen_fill_messages(
    deck_title: str,
    slide_index: int,
    slide_total: int,
    slide_title: str,
    pattern: str,
    brief: str,
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """두원(Qwen 자동) 2단계 — 한 슬라이드의 내용을 패턴 스키마에 맞춰 JSON 으로 채운다."""
    pattern = pattern if pattern in _QWEN_FILL_SCHEMAS else "bullets"
    schema = _QWEN_FILL_SCHEMAS[pattern]
    sys = f"""당신은 두원공조(DOOWON) 보고서의 한 슬라이드 **내용을 채우는** 작성자입니다.
디자인·HTML·좌표는 만들지 마세요 — 아래 JSON 스키마의 필드만 정확히 채웁니다(서버가 디자인함).

발표 전체 제목: {deck_title}
이 슬라이드: {slide_index}/{slide_total} · 패턴 "{pattern}"
슬라이드 제목: {slide_title}
이 슬라이드에서 다룰 내용(brief): {brief}

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{schema}

규칙:
- 모든 텍스트 한글({language}). 영어는 카테고리 라벨·단위·상태칩·약어만.
- 구체 수치(금액·증감률·날짜·비율)는 **입력 자료에 있는 값만** 사용. 없으면 지어내지 말고 정성적으로 쓰세요.
- 칸에 넘치지 않게 간결하게. 표는 행을 너무 많이 넣지 말 것(권장 범위 내).
- 톤: {tone}."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""참고 입력 자료(발췌):
---
{content}
---
위 자료에서 이 슬라이드("{slide_title}")에 해당하는 내용을 골라 JSON 으로 채우세요."""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


# ── 세미나 참석 보고 양식 (doowon-seminar) — 단일 본문 ───────────
_SEMINAR_FILL_SCHEMA = """\
{
  "title": "보고 제목 — 표지·본문 상단에 한 줄로 들어가므로 간결하게(공백 포함 28자 이내). 예: '2026 NexTech Week AI EXPO 참석 보고'",
  "pattern": "seminar_report",
  "meta": {
    "purpose": "참관/참석 목적 한 줄",
    "schedule": "일정 / 장소 (예: 2026. 5/27(수)~30(토) / 중국 상해)",
    "attendees": "참석자 명단(이름·직책 나열, 쉼표 구분)"
  },
  "sections": [
    {"no":"1", "topic":"항목명(예: 자동차 매장 방문)",
     "points":["주요 내용 한 줄","..."],
     "remark":{"items":[{"label":"차량","caption":"비고 보충 텍스트(선택)","photo":true}]}},
    {"no":"2", "topic":"세미나 및 전시회 참관",
     "points":["...","..."],
     "remark":{"items":[
        {"label":"세미나","caption":"참석 인원·소속 등 보충 텍스트","photo":true},
        {"label":"전시물","caption":"또 다른 보충 텍스트","photo":true}]}}
  ],
  "conclusion": ["참석 소감/결론 한 줄", "..."],
  "action": "→ 로 시작하는 후속 액션 한 줄(선택)"
}"""


def build_doowon_seminar_fill_messages(
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """세미나 참석 보고(doowon-seminar) — 단일 본문 페이지 내용을 JSON 으로 채운다."""
    sys = f"""당신은 두원공조(DOOWON) **세미나/출장 참석 보고서**의 본문을 작성하는 작성자입니다.
디자인·HTML·좌표는 만들지 마세요 — 아래 JSON 스키마의 필드만 정확히 채웁니다(서버가 디자인함).
이 문서는 표지 1장 + 본문 1장 구성이며, 본문 1장에 모든 내용을 담습니다.

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{_SEMINAR_FILL_SCHEMA}

규칙:
- 모든 텍스트 한글({language}). 영어는 고유명사·약어·단위만.
- title(보고 제목)은 표지·본문 상단에 한 줄로 들어가야 하므로 **공백 포함 28자 이내**(한글 기준 약 20자)로 간결하게. '구축', '도입 과제', '기술 타당성 검증' 같은 긴 부연은 빼고 핵심 행사/주제명 + '참석 보고'만 남길 것. (예: '2026 NexTech Week AI EXPO 참석 보고')
- meta(목적/일정·장소/참석자)는 자료에서 그대로 추출. 없는 항목은 빈 문자열(추정·창작 금지).
- sections 는 "주요 내용" 표의 행. 자료의 내용을 소주제별로 나눠 정리하되 **자료에서 실제로 확인되는 만큼만** 만든다(보통 2~6행). 한 항목에 내용이 많으면 소주제별로 행을 나누고, 각 행의 points 는 2~4개로.
- **분량을 채우려고 없는 내용을 늘리지 말 것.** 표가 짧아도 서버가 세로 공간을 자동으로 채우므로 억지 확장·중복·일반론으로 행을 부풀릴 필요가 없다 — 정확성이 분량보다 절대 우선이다.
- remark 는 비고칸 정보로 items 배열. 각 item 은 label(사진/구분 라벨), caption(설명 텍스트), photo(사진 자리표시 여부 true/false) 필드를 가짐. 한 행에 여러 item 을 넣으면 비고칸이 그만큼 행으로 나뉨(예: 세미나/전시물 2개). 비고가 없으면 items 를 빈 배열로 두거나 remark 생략.
- 행사 장면·현장 점검·설비·전시물처럼 **사진이 있을 법한 항목은 photo:true** 로 두세요. 첨부 자료에 맞는 사진이 있으면 서버가 그 자리에 자동으로 끼우고(없으면 라벨만 표시, 지어내지 않음).
- photo:true 인 item 의 caption 은 **사진 아래 한 줄로 아주 짧게**(공백 포함 12자 이내, 예: '착공식 첫삽', '신규 AIS 라인'). 길면 잘리고 사진과 공간이 겹치니 긴 설명은 points 로 옮길 것.
- conclusion 은 "참석 소감(결론)"의 ✓ 항목(3~5개, 자료 근거), action 은 후속 조치 한 줄(선택, → 로 표시됨).
- **입력 자료에 명시된 사실만 사용한다.** 이름·직책·날짜·장소·수치·발언·참석자 명단은 자료에 있는 것만 그대로 쓰고, 없으면 비우거나 그 항목을 생략한다(추정·일반 상식·창작 금지). 입력 자료가 유일한 출처이며 외부 지식으로 보완하지 말 것. 톤: {tone}."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""입력 자료:
---
{content}
---
위 자료로 세미나 참석 보고 본문 JSON 을 채우세요."""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


_MEETING_FILL_SCHEMA = """\
{
  "title": "회의 주제(짧게, 공백 포함 28자 이내)",
  "meeting_categories": ["정보전달"],
  "team": "주관팀(예: AI TFT)",
  "author": "작성자(예: 최무겸 대리)",
  "place": "장소(예: 두원공조 연구1동 201호)",
  "date": "26.06.18 (목)",
  "time": "15:00~16:00",
  "attendees": [
    {"org": "두원공조", "members": "이기정 상무, 남강우 이사, 류성훈 과장"},
    {"org": "두원전자", "members": "박창화 이사, 강신덕 책임"}
  ],
  "attendee_total": "총 10명",
  "body": [
    "■ 회의 목적",
    "- 핵심 배경/목적 한 줄",
    "■ 주요 논의 사항",
    "1. 첫 안건",
    "  1) 세부 논의",
    "→ 도출된 결론",
    "■ 결정 사항",
    "1. 결정 내용",
    "■ Action Item",
    "- 담당/기한 포함 후속 조치",
    "■ 다음 회의 / 일정",
    "- 일정"
  ]
}"""


def build_doowon_meeting_fill_messages(
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """회의록(doowon-meeting) — 회의 메모/문서를 두원 회의록 양식 JSON 으로 정리."""
    sys = f"""당신은 두원공조(DOOWON) **회의록**을 정리하는 작성자입니다.
입력으로 회의 메모/문서가 주어집니다. 그 내용을 아래 JSON 스키마의 회의록 양식으로
**정리·요약**하세요. 디자인·HTML·좌표는 만들지 마세요(서버가 표로 그림).

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{_MEETING_FILL_SCHEMA}

규칙:
- 모든 텍스트 한글({language}). 영어는 고유명사·약어·단위만. 한자 병기 금지.
- 머리표 필드(title/team/author/place/date/time)는 자료에 있는 값만 추출.
  없는 항목은 빈 문자열로 둘 것(지어내지 말 것). title 은 회의 주제를 28자 이내로 압축.
- meeting_categories 는 [정보전달, 이해조정, 의견교환, 문제해결, 기타] 중 해당하는 것만 골라
  문자열 배열로(예: ["정보전달","의견교환"]). 해당 없으면 [].
- attendees 는 참석자를 회사/소속별로 묶어 배열로 작성:
  각 원소 {{"org":"회사명","members":"이름 직책, …"}}.
  자료에 회사 구분이 없으면 org 를 빈 문자열로 두고 members 에 전체 명단을 넣을 것.
  attendee_total 은 파악되면 "총 N명" 형식, 아니면 빈 문자열.
- body 는 회의내용을 개조식 줄 배열로 정리. 줄 앞 마커로 계층을 표현:
  · "■" → 대주제 머리표(회의 목적 / 주요 논의 사항 / 결정 사항 / Action Item / 다음 일정 등)
  · "1." "2." → 안건 번호, "  1)" "  2)" → 세부 논의, "→" → 결론/결정, "-" → 부연
- 잡담·중복·인사말을 걷어내고 핵심 논의·결정·할 일 중심으로 압축.
  발언자별 나열이 아니라 주제별로 묶어 정리. 결정 사항과 Action Item(담당/기한)은 빠뜨리지 말 것.
- 분량은 A4 1장에 들어가도록 body 최대 20줄(머리표 포함)로 압축.
  각 줄은 40자 이내로 짧게. 비슷한 안건·내용은 하나로 통합하고 부연·중복·예시는 생략.
  톤: {tone}.
- 첨부 파일명 등은 본문에 넣지 말 것(예: "■ 첨부", 파일명 나열 금지). 회의 내용만 담는다."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""입력 자료(회의 메모/문서):
---
{content}
---
위 내용을 두원 회의록 양식 JSON 으로 정리하세요. 결정 사항과 Action Item 을 명확히 구분해 담으세요."""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


_TRIP_FILL_SCHEMA = """\
{
  "title": "출장 일정",
  "pattern": "trip_schedule",
  "days": [
    {"date": "5/27(수)", "rows": [
       {"group": "-", "content": ["-. 김포 공항 → 상하이 훙차오 공항"], "attendees": "-"},
       {"group": "A조", "content": ["-. 중국 자동차 동향 조사 (5개 전시장 방문)", "ㄴ 중국 전기차 기술 동향 조사"], "attendees": "○○○ 부장 외 8명"},
       {"group": "B조", "content": ["-. 컴프레서 업체 출장 (2개 협력사 방문)", "ㄴ 신규 부품업체 방문 조사"], "attendees": "○○○ 상무 외 1명"}
    ]},
    {"date": "5/28(목)", "rows": [
       {"group": "A조", "content": ["-. 세미나 및 전시회 참관"], "attendees": "○○○ 상무 외 8명"}
    ]}
  ],
  "note": "(선택) 하단 주석"
}"""


def build_doowon_seminar_trip_messages(
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """세미나 참석 보고 2번째 본문 — 출장 일정 표를 JSON 으로 채운다."""
    sys = f"""당신은 두원공조(DOOWON) **출장(세미나 참석) 일정표**를 작성하는 작성자입니다.
디자인·HTML 은 만들지 마세요 — 아래 JSON 스키마의 필드만 채웁니다(서버가 표로 그림).
이 페이지는 세미나 참석 보고의 2번째 본문(일자별 출장 일정 표)입니다.

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{_TRIP_FILL_SCHEMA}

규칙:
- 모든 텍스트 한글({language}). 영어는 고유명사·약어만.
- days = 일자별 묶음. 각 day 의 date(예: "5/27(수)"), rows = 그 날의 일정 행들.
- 각 row: group(구분: 조 이름이나 "-"), content(내용 줄들 — 주요 항목은 "-. " 로 시작, 하위 설명은 "ㄴ " 로 시작), attendees(참석 인원, 없으면 "-").
- 자료에 실제로 있는 일정만 일자 순서로 옮긴다(이동·조별 일정·식사 등). 날짜·장소·참석자·이동편은 자료에 명시된 것만 쓰고, 없으면 "-" 로 두거나 그 행을 생략한다 — **일정을 지어내지 말 것.** 입력 자료가 유일한 출처다. 톤: {tone}."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""입력 자료:
---
{content}
---
위 자료로 출장 일정 표 JSON 을 채우세요. **자료에 일정 정보가 없으면 days 를 빈 배열로 두세요 — 없는 일정을 추측해 만들지 마세요.**"""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


# ── 교육 보고서 양식 (doowon-education) — 단일 본문 표 ───────────
_EDUCATION_FILL_SCHEMA = """\
{
  "title": "보고 제목 — 표지·본문 상단에 한 줄로 들어가므로 간결하게(공백 포함 28자 이내). 예: '교육 보고서 – ZEISS 3차원 측정 장비'",
  "pattern": "education_report",
  "rows": [
    {"label": "교육일정", "content": "2025. 09. 10.(수) ~ 2025. 09. 12(금)", "remark": ""},
    {"label": "교육장소", "content": "자이스코리아 대구오피스", "remark": ""},
    {"label": "교육과정", "content": "ZEISS 3차원 측정 장비 교육", "remark": ""},
    {"label": "교육비", "content": "무료", "remark": ""},
    {"label": "목적", "content": "ZEISS 3차원 측정 장비의 이해와 측정 방법 기초 교육", "remark": ""},
    {"label": "교육내용",
     "content": ["1. 3차원 측정기 소개", "2. 스타일러스 교정", "3. 요소", "4. 특성", "5. 안전영역"],
     "remark": {"photo": true, "caption": "교육 결과 보고서"}},
    {"label": "활용방안",
     "content": "▶ 전동식 컴프레서 개발 실무적용 : 보고서 작성, 부품 검수",
     "remark": "", "grow": true}
  ]
}"""


def build_doowon_education_fill_messages(
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """교육 보고서(doowon-education) — 단일 본문 표(구분/내용/비고)를 JSON 으로 채운다."""
    sys = f"""당신은 두원공조(DOOWON) **교육 참가 보고서**의 본문을 작성하는 작성자입니다.
디자인·HTML·좌표는 만들지 마세요 — 아래 JSON 스키마의 필드만 정확히 채웁니다(서버가 표로 그림).
이 문서는 표지 1장 + 본문 1장 구성이며, 본문 1장에 모든 내용을 담습니다.

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{_EDUCATION_FILL_SCHEMA}

규칙:
- 모든 텍스트 한글({language}). 영어는 고유명사·약어·단위만.
- title(보고 제목)은 표지·본문 상단에 한 줄로 들어가야 하므로 **공백 포함 28자 이내**로 간결하게. 핵심 교육명 + '교육 보고서'만 남길 것. (예: '교육 보고서 – ZEISS 3차원 측정 장비')
- rows 는 표의 행 목록. 각 행은 label(구분 열), content(내용 열), remark(비고 열). label 은 보통 교육일정 / 교육장소 / 교육과정 / 교육비 / 목적 / 교육내용 / 활용방안 을 순서대로 쓰되, 자료에 맞춰 가감 가능.
- content 가 여러 줄이면 문자열 배열로(예: 교육내용은 "1. ...", "2. ..." 처럼 번호 매겨서). 한 줄이면 문자열.
- remark(비고)는 보통 빈 문자열. 사진 자리표시가 필요하면 {{"photo": true, "caption": "교육 결과 보고서"}} 형태로. 일반 텍스트면 그냥 문자열.
- 활용방안 행은 보통 가장 길고 본문 아래 공간을 채우므로 "grow": true 로 표시하고, 내용은 "▶ " 로 시작.
- 구체 수치·날짜·장소는 입력 자료에 있는 값만. 없으면 지어내지 말고 빈 문자열. 톤: {tone}."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""입력 자료:
---
{content}
---
위 자료로 교육 보고서 본문 JSON 을 채우세요."""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


# ── 교육 결과 보고서(똑딱이 내부 덱) 본문 — 항목별 상세 ───────────
_RESULT_BODY_SCHEMA = """\
{
  "sections": [
    {
      "topic": "교육내용 항목명(주어진 목차 항목 그대로)",
      "header": "본문 상단 ▶ 헤더(항목명 또는 짧은 주제어)",
      "subsections": [
        {"heading": "1. 적용 조건", "lines": ["1) 핵심 조건/정의 한 줄", "2) 또 다른 조건", "→ 위 조건의 결론/요약", "- 부연 설명 한 줄"], "image": false},
        {"heading": "2. 주요 내용", "lines": ["1) ...", "→ ...", "- ..."], "image": false},
        {"heading": "3. 참고/절차", "lines": ["..."], "image": false}
      ],
      "table": null,
      "flow": null
    }
  ]
}"""


def build_education_result_messages(
    topic: str,
    items: list[str],
    content: str,
    language: str,
    tone: str,
    instructions: str | None,
) -> list[dict]:
    """교육 결과 보고서(똑딱이 내부) 본문 — 목차 항목마다 상세 본문을 JSON 으로 채운다."""
    items_txt = "\n".join(f"{i + 1}. {it}" for i, it in enumerate(items)) or "(항목 없음)"
    sys = f"""당신은 두원공조(DOOWON) **교육 결과 보고서**의 본문을 작성하는 작성자입니다.
표지·목차·디자인은 만들지 마세요 — 아래 JSON 스키마의 본문 필드만 채웁니다(서버가 슬라이드로 그림).
주어진 '목차 항목' 각각에 대해 본문 슬라이드 1장씩 작성합니다. 입력 자료(최신 검색 결과 + 첨부 문서)를
근거로 양식만 지키면서 자유롭게 정리하세요.

목차 항목(이 순서·개수 그대로 sections 를 만들 것):
{items_txt}

출력은 아래 형식의 JSON 객체 하나만(설명·코드블록·다른 키 금지):
{_RESULT_BODY_SCHEMA}

규칙:
- sections 길이 = 목차 항목 수. 각 section.topic 은 위 항목명을 그대로 사용.
- 각 section 은 subsections 2~4개. subsection.heading 은 "1. ...", "2. ..." 처럼 번호로 시작.
- lines 는 해당 소항목의 설명(각 줄 한 문장 정도, 2~6줄). 두원 결과보고서 양식대로 **줄 앞 마커로 계층**을 표현하세요:
  · "1)", "2)", "①", "가)" → 번호 소항목(1단 들여쓰기)
  · "→" → 결론·요약 줄(2단 들여쓰기, 핵심 한 줄)
  · "-" → 세부 부연 설명(2단 들여쓰기)
  · 마커 없는 줄 → 서버가 "→"를 붙여 결론처럼 처리
  되도록 한 소항목에 1)/2) 나열 → 그 아래 →/- 로 결론·부연을 다는 식으로 입체적으로 구성(평평한 나열 지양).
- 모든 텍스트 한글({language}). 영어는 고유명사·약어·단위만. 한자 금지.
- **사실 정확성**: 입력 자료에 있는 내용만. 자료에 없는 수치·절차·기능을 지어내지 말 것. 자료가 부족한 항목은 일반적이고 보편적인 설명으로 간결히. 톤: {tone}.
- image 필드는 보통 false(서버가 실제 스크린샷을 넣지 못함). 도해가 꼭 필요한 소항목만 true.
- table 은 보통 null. 표로 정리하는 게 자연스러운 항목(사양·비교·수치 목록 등)에만 작성:
  {{"title": "표 제목(선택)", "columns": ["구분", "내용"], "rows": [["A", "..."], ["B", "..."]]}}
  열 2~4개, 행은 자료에 있는 사실만(지어내기 금지). 표가 어색하면 그냥 null.
- flow 는 보통 null. 내용이 **순차/흐름(A→B→C)** 구조(예: 전력·신호·물질의 흐름, 처리 단계, 구성요소 연결)일 때만 작성:
  {{"title": "흐름 제목(선택)", "nodes": [{{"label": "HV 배터리", "sub": "400/800V DC"}}, {{"label": "인버터", "sub": "DC→AC 변환"}}, {{"label": "모터", "sub": "..."}}], "edges": ["DC", "AC(가변)"]}}
  노드 2~5개(label 필수, sub 짧은 설명 선택), edges 는 노드 사이 화살표 라벨(노드 수보다 1 적게, 선택). 서버가 박스+화살표 도형으로 그린다. 흐름이 아니면 null.
  한 section 에 table 과 flow 를 둘 다 쓰지 말고 더 잘 맞는 하나만."""
    if instructions:
        sys += f"\n추가 지시: {instructions}"
    user = f"""입력 자료(최신 검색 + 첨부 문서):
---
{content}
---
위 자료로 교육 결과 보고서 본문 sections JSON 을 채우세요. 목차 항목 순서·개수를 정확히 맞추세요."""
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_brandlogy_html_edit_prompt(
    current_html: str,
    message: str,
    history: list[dict] | None = None,
) -> tuple[str, str]:
    """자유 양식 HTML 덱 수정 — 현재 HTML + 요청 → 수정된 HTML 전체 (system, user)."""
    sys_prompt = """당신은 Brandlogy 슬라이드 덱 HTML 을 수정하는 디자이너입니다.
아래 '현재 HTML' 과 사용자 수정 요청을 보고, 요청만 반영한 **완전한 HTML 문서 전체**를 다시 출력하세요.

규칙:
- 전체 레이아웃·슬라이드 크기·틀(헤더/푸터/로고/테두리)·@page/인쇄 규칙·전체 구조는 그대로 유지.
- 기존 폰트(폰트 패밀리 문자열)는 바꾸지 말 것. 색·굵기·텍스트 내용 등 요청한 부분만 변경.
- `__DATAURI_숫자__` 같은 placeholder 토큰은 그대로 보존(이미지 자리표시이므로 절대 수정·삭제 금지).
- 요청과 무관한 슬라이드·스타일은 건드리지 말 것. 수치·내용을 임의로 지어내지 말 것.
- 모든 텍스트 한글(한자·가나·키릴 금지, 영어는 약어·단위만).
- 출력은 <!DOCTYPE html> 로 시작하는 HTML 문서 전체만. 설명·마크다운·코드블록 금지."""
    hist_text = ""
    for h in (history or [])[-4:]:
        role = h.get("role")
        if role in ("user", "assistant") and h.get("content"):
            hist_text += f"[{role}] {h['content']}\n"
    user_prompt = f"""현재 HTML:
{current_html}

{("이전 대화:\n" + hist_text) if hist_text else ""}수정 요청: {message}

위 요청을 반영한 완전한 HTML 문서 전체를 출력하세요."""
    return sys_prompt, user_prompt


def _brandlogy_skeleton_plan(skeleton_slides: list[dict]) -> str:
    """스켈레톤에서 기하/스타일을 떼고 채우기에 필요한 (index, type, ROLE, hint) 만 추린 plan."""
    import json

    plan = []
    for si, s in enumerate(skeleton_slides):
        data = s.get("data") or {}
        els = data.get("ELEMENTS") or []
        e_plan = []
        for ei, el in enumerate(els):
            if not isinstance(el, dict):
                continue
            item = {"i": ei, "type": (el.get("type") or "").lower(), "ROLE": el.get("ROLE", "")}
            for hint in ("CHART", "SERIES_N", "COLS", "ROWS_N"):
                if el.get(hint) is not None:
                    item[hint] = el.get(hint)
            e_plan.append(item)
        plan.append(
            {
                "i": si,
                "HEADLINE_ROLE": data.get("HEADLINE_ROLE", ""),
                "SUBTITLE_ROLE": data.get("SUBTITLE_ROLE", ""),
                "BG": data.get("BG", "white"),
                "elements": e_plan,
            }
        )
    return json.dumps({"slides": plan}, ensure_ascii=False)


# (3) Qwen — 내용 채우기 (인덱스별)
def build_brandlogy_fill_messages(
    skeleton_slides: list[dict],
    content: str,
    language: str,
    tone: str,
) -> list[dict[str, str]]:
    plan_json = _brandlogy_skeleton_plan(skeleton_slides)
    sys_prompt = f"""당신은 정해진 슬라이드 레이아웃에 '내용'만 채우는 작성자입니다.
레이아웃(위치·종류)은 이미 확정됐습니다. 각 슬라이드/요소의 ROLE 과 입력 자료를 보고
요소 type 에 맞는 '내용 필드'만 채워서 인덱스별로 반환하세요. 위치는 절대 신경쓰지 마세요.

요소 type 별 반환 필드:
- text   : {{"TEXT": "여러 줄은 \\n"}}
- kpi    : {{"VALUE":"1,234","UNIT":"억원","LABEL":"매출","DELTA":"+12%","UP":true}}
- bullets: {{"TITLE":"제목(선택)","ITEMS":["요점1","요점2","요점3"]}}
- chart  : {{"LABELS":["1월","2월",...],"SERIES":[{{"name":"매출","values":[..]}}]}}  (SERIES_N 만큼)
- table  : {{"COLUMNS":["열1",..],"ROWS":[["값",..],..]}}  (COLS/ROWS_N 에 맞춰)
- steps  : {{"ITEMS":[{{"LABEL":"단계","BODY":"한 줄 설명"}}]}}
- pill   : {{"TEXT":"라벨"}}
- divider: {{}}

출력(JSON 객체 하나만, 코드블록·잡담 금지):
{{"slides":[
  {{"i":0,"HEADLINE":"대제목","SUBTITLE":"부제",
    "elements":[{{"i":0, ...내용 필드...}}, {{"i":1, ...}}]}},
  ...
]}}

규칙:
- 모든 텍스트는 한글. 한자·일본 가나·키릴 금지. 영어는 약어·단위만.
- 입력 자료에 없는 수치·금액·이름은 추측하지 말고 생략하거나 "추후 안내".
- 카드/항목 설명은 한 줄(약 35자 이내)로 간결하게. 톤: {tone}. 언어: {language}.
- 슬라이드/요소 개수와 인덱스(i)는 아래 레이아웃과 정확히 일치시킬 것."""
    user_prompt = f"""레이아웃(채울 자리):
{plan_json}

입력 자료:
---
{content}
---
위 레이아웃의 각 자리에 입력 자료 기반 내용을 채워 JSON 하나만 출력하세요."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


# (3-b) Qwen — 내용 채우기 (슬라이드 1장씩 — 작은 JSON 이라 파싱 안정적)
_BRANDLOGY_FILL_FIELD_GUIDE = """\
요소 type 별 반환 필드:
- text   : {"TEXT": "여러 줄은 \\n"}
- kpi    : {"VALUE":"1,234","UNIT":"억원","LABEL":"매출","DELTA":"+12%","UP":true}
- bullets: {"TITLE":"제목(선택)","ITEMS":["요점1","요점2","요점3"]}
- chart  : {"LABELS":["1월","2월",...],"SERIES":[{"name":"매출","values":[..]}]}  (SERIES_N 만큼)
- table  : {"COLUMNS":["열1",..],"ROWS":[["값",..],..]}  (COLS/ROWS_N 에 맞춰)
- steps  : {"ITEMS":[{"LABEL":"단계","BODY":"한 줄 설명"}]}
- pill   : {"TEXT":"라벨"}
- divider: {}"""


def build_brandlogy_fill_slide_messages(
    slide_skeleton: dict,
    content: str,
    language: str,
    tone: str,
    *,
    slide_no: int = 1,
    total: int = 1,
) -> list[dict[str, str]]:
    """단일 슬라이드 내용 채우기 메시지 (작은 JSON 한 장)."""
    import json

    data = slide_skeleton.get("data") or {}
    els = data.get("ELEMENTS") or []
    e_plan = []
    for ei, el in enumerate(els):
        if not isinstance(el, dict):
            continue
        item = {"i": ei, "type": (el.get("type") or "").lower(), "ROLE": el.get("ROLE", "")}
        for hint in ("CHART", "SERIES_N", "COLS", "ROWS_N"):
            if el.get(hint) is not None:
                item[hint] = el.get(hint)
        e_plan.append(item)
    plan = {
        "HEADLINE_ROLE": data.get("HEADLINE_ROLE", ""),
        "SUBTITLE_ROLE": data.get("SUBTITLE_ROLE", ""),
        "elements": e_plan,
    }
    plan_json = json.dumps(plan, ensure_ascii=False)

    sys_prompt = f"""당신은 정해진 슬라이드 레이아웃에 '내용'만 채우는 작성자입니다.
슬라이드 1장({slide_no}/{total})의 각 자리(ROLE)에 입력 자료 기반 내용을 채우세요.
위치·종류는 이미 확정됐으니 '내용 필드'만, 인덱스(i)에 맞춰 반환합니다.

{_BRANDLOGY_FILL_FIELD_GUIDE}

출력(JSON 객체 하나만, 코드블록·잡담 금지):
{{"HEADLINE":"대제목","SUBTITLE":"부제","elements":[{{"i":0, ...내용 필드...}}, ...]}}

규칙:
- 모든 텍스트 한글. 한자·일본 가나·키릴 금지. 영어는 약어·단위만.
- **수치 날조 절대 금지**: 입력 자료에 있는 수치만 사용. 없는 수치·금액·증감률(+12% 등)을 지어내지 말 것.
- **kpi**: 자료에 수치가 있을 때만 VALUE+UNIT+DELTA 를 채운다. 수치가 없으면 VALUE 에
  핵심을 나타내는 짧은 정성 표현(예: "채택 확대", "전환 가속")만 쓰고 UNIT·DELTA 는 키 자체를 빼라.
  "추후 안내" 같은 자리표시 문구나 임의 증감률(+15% 등)을 절대 넣지 말 것.
- DELTA(증감)는 자료에 명확한 근거가 있을 때만. 근거 없으면 키 생략.
- 카드/항목 설명은 한 줄(약 35자 이내). 톤: {tone}. 언어: {language}.
- elements 의 개수·인덱스(i)는 아래 레이아웃과 정확히 일치."""
    user_prompt = f"""채울 슬라이드 레이아웃:
{plan_json}

입력 자료:
---
{content}
---
위 슬라이드의 각 자리에 내용을 채워 JSON 객체 하나만 출력하세요."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_house_messages(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
    schema: str,
    exact_count: bool = False,
) -> list[dict[str, str]]:
    """두원 하우스 스타일(진행보고) 블록 JSON 생성 메시지.

    exact_count=True 면 사용자가 장수를 직접 지정한 것 → 정확히 n장(줄이지 말 것).
    False 면 '자유' → 긴 자료를 짧게 요약하도록 적은 장수를 유도.
    """
    n = max(1, int(n_slides or 1))
    if exact_count:
        count_rule = (
            f"- **본문 house-report 슬라이드를 정확히 {n}장** 만드세요(표지 제외). 내용을 {n}장에 "
            "고르게 나눠 담고, 페이지를 임의로 줄이거나 합치지 마세요.\n"
            f"- **각 페이지를 충분한 내용으로 가득 채우세요**(아래 여백 최소화). 페이지마다 표/차트/불릿 "
            "등 블록을 **2개 이상** 넣고, 한 페이지에 작은 표 하나만 달랑 넣어 아래를 비우지 마세요. "
            "자료가 적으면 주제에 관해 일반적으로 알려진 배경·구분·고려사항·향후 방향 등을 정성적으로 "
            "보강해 채우되, **구체 수치·고유명사·날짜는 자료에 있을 때만** 쓰고 지어내지 마세요."
        )
        count_tail = (
            f"위 자료로 \"house-report\" 슬라이드를 **정확히 {n}장**, 각 페이지를 알차게 채워 만드세요."
        )
    else:
        count_rule = (
            "- **이 PPT 는 긴 입력 자료(PDF 수십 장 등)를 '짧게 요약'하는 용도**입니다. 원문을 그대로 "
            f"옮기지 말고 **핵심만 추려** 압축하세요. 입력이 길어도 **가능한 한 적은 장수**(권장 2~3장, "
            f"최대 {n}장)로 만드세요.\n"
            "- **페이지 수 최소화가 최우선**: 주제를 잘게 쪼개지 말고 **넓게 묶어** 한 페이지에 여러 소제목(■)을 "
            "담으세요. 비슷한 주제는 같은 페이지로 합치고, **주제마다 페이지를 새로 만들지 마세요.** 한 페이지에 "
            "블록(표·차트·2단 row·소제목)을 **3~5개씩 빽빽이** 넣어 가득 채우세요.\n"
            "- **단, 만든 페이지는 모두 빈 공간 없이 꽉 채우세요** — 페이지 하단에 큰 공백을 남기지 마세요. "
            "내용이 페이지를 다 못 채우면 ① **장수를 더 줄이거나** ② 주제 관련 배경·구분·고려사항·시사점을 "
            "정성적으로 **보강해 채우세요**. 보강 시 **구체 수치·고유명사·날짜는 자료에 있을 때만** 쓰고 지어내지 마세요."
        )
        count_tail = (
            f"위 자료를 **핵심만 추려 적은 장수**(권장 3~5장, 최대 {n}장)로, 단 **각 페이지는 빈 공간 없이 "
            "가득 채워** \"house-report\" 슬라이드 JSON 으로 만드세요."
        )
    sys_prompt = f"""당신은 두원공조 AI TFT 의 사내 진행보고 PPT 자동 작성 어시스턴트입니다.
주어진 주제·자료를 바탕으로 "두원 사내 진행보고 하우스 스타일"(연파랑 헤더 전체격자표 + 파란 강조 +
■섹션 + 하단 마일스톤 화살표) 슬라이드 구조를 JSON 으로 만드세요.

응답은 **반드시 다음 JSON 객체** 만 출력 (다른 텍스트·마크다운·코드블록 금지):
{{
  "slides": [
    {{ "layout": "house-report", "data": {{ ... }} }}
  ]
}}

모든 슬라이드의 layout 은 정확히 "house-report" 입니다. data 는 아래 스키마를 따릅니다:

{schema}

요청 사항:
{count_rule}
- **컴팩트가 최우선(사내 정책)**: 한 페이지를 가능한 한 가득 채우되, 표는 정말 핵심 행만 담아
  너무 크게 만들지 마세요(큰 표는 다음 장으로 밀려 빈 공간을 만듭니다). 내용이 적으면 장수를
  억지로 늘리지 말고 **줄이세요**. (생성 후 시스템이 덜 찬 페이지를 자동으로 합칩니다.)
- **좌우 공백 제거**: 폭이 좁은 블록(특히 원형/도넛 차트)이나 작은 표 2개는 **row 로 묶어 좌우
  2단**으로 배치해 가로 여백을 없애세요. 한 줄에 한 블록만 두지 말고 가능한 한 옆을 채우세요.
- **내용에 맞는 블록만** 쓰세요(억지 금지): 비교·항목·역할은 table, 수치·추세·구성비는 chart
  (column/bar/line/pie), 서술형은 text, 항목 나열은 outline. **표·차트로 만들 데이터가 없으면
  만들지 말고** text/lead 로 자연스럽게 작성하세요.
- **timeline(화살표 진행도)은 노드마다 구체적 날짜가 있는 실제 추진 일정일 때만** 쓰세요. 날짜
  없는 단계 나열에는 쓰지 마세요(outline/table 로). 보고서 전체에서 꼭 필요한 곳 1~2번 — **남발 금지.**
- **장마다 구성을 다양화**하세요(같은 구성 반복 금지). 예: 어떤 장은 표 2~3개, 어떤 장은
  차트 + 표, 어떤 장은 표 + outline.
  첫 장은 보통 lead(목적 한 줄)로 시작합니다.
- **빈 섹션 금지**: ■ 섹션(소제목)을 만들면 **반드시 그 안에 본문 블록(표/차트/outline/timeline) 1개 이상**을
  넣으세요. **제목 + "목적:" 한 줄만 있고 본문이 없는 섹션은 만들지 마세요**(휑하게 보입니다). 넣을 본문이
  없으면 그 섹션 자체를 만들지 말고, 핵심을 다른 섹션의 표 행이나 항목으로 합치세요.
- **conclusion(파란 한줄평) 블록은 만들지 마세요.** 결론·시사점이 필요하면 text 나 표의 한 행으로 담으세요.
- 핵심 수치·상태값(완료/예정 등)·핵심 어구는 **그 단어만 `**...**` 로 감싸 굵게** 강조하세요(색 X, 전체 볼드 X).
- 표는 colW 합 25.9, align·header·각 row 길이를 열 수와 정확히 맞추고, **rowH 는 절대 넣지 마세요**.
- **align 은 "l"(왼쪽) 또는 "c"(가운데)만** 사용하세요. **"r"(오른쪽 정렬)은 쓰지 마세요.**
- 언어: {language} / 톤: {tone}
{_KO_RULES if language == "Korean" else ""}
{instructions or ""}
"""
    user_prompt = f"""주제 / 입력 자료:
---
{content}
---

{count_tail}
JSON 객체 하나만 출력하고 다른 텍스트는 절대 넣지 마세요."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_house_section_keywords_messages(
    sections: list[str],
    topic: str = "",
) -> list[dict[str, str]]:
    """house 섹션 제목 → **외부에 내보내도 되는 일반화 웹검색어** 생성 메시지(내부 Qwen 전용).

    핵심: 섹션 제목에는 사내 차종/모델·코드명·고객사·내부 부품번호 등 **기밀 식별자**가 섞여 있다.
    이 호출의 출력(query)만 외부 검색으로 나가므로, query 에는 기밀 식별자를 **절대 넣지 않고**
    일반 산업·기술·시장 용어로만 바꿔 공개 자료(동향·수치·표준·배경)를 찾을 수 있게 한다.
    """
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sections))
    sys_prompt = (
        "당신은 사내 보고서 섹션 제목을 '외부 웹 검색용 일반화 질의'로 바꾸는 도우미입니다.\n"
        "각 섹션 제목마다 공개 웹에서 배경·동향·수치·표준을 찾기 좋은 **일반 검색어 1개**를 만드세요.\n\n"
        "절대 규칙(보안):\n"
        "- 검색어에는 **사내 식별자 금지** — 차종/모델명(예: SK3 EV19, OS HEV)·코드명·프로젝트명·"
        "고객사명·내부 부품번호·사내 약어를 넣지 마세요. 일반 기술/제품 카테고리·시장·표준 용어로만.\n"
        "- 기밀 사실(불량 내용·수치·내부 일정)을 검색어에 적지 마세요. **주제(테마)만** 일반화하세요.\n"
        "- 순수 사내 상태/관리용 섹션(예: '진행 현황', '결론', '요약', '범위')처럼 공개 자료로 보강할 "
        "테마가 없으면 query 를 빈 문자열(\"\")로 두세요.\n"
        "- 검색어는 섹션 제목과 같은 언어, 60자 이내, 군더더기 없이.\n\n"
        "응답은 **다음 JSON 객체 하나만**(코드블록·설명 금지):\n"
        '{ "queries": [ { "section": "<원래 섹션 제목 그대로>", "query": "<일반화 검색어 또는 \\"\\">" } ] }'
    )
    user_prompt = (
        (f"보고서 주제(비기밀): {topic}\n\n" if topic.strip() else "")
        + "다음 섹션 제목들 각각에 대해 일반화 검색어를 만드세요:\n"
        + numbered
        + "\n\nJSON 객체 하나만 출력하세요."
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_house_enrich_messages(
    slides: list[dict],
    research_notes: str,
    language: str,
    schema: str,
) -> list[dict[str, str]]:
    """기존 house 슬라이드 JSON 을 **외부 웹 검색 결과로 전 섹션 보강**하는 메시지(내부 Qwen 전용).

    첨부/원본 내용이 우선이고, 외부 검색 자료는 배경·시장 수치·동향·공개 벤치마크로 **보탤** 뿐
    내부 사실을 대체하지 않는다. 구조(슬라이드 수·블록·섹션)는 유지하고 내용만 알차게 채운다.
    """
    import json as _json

    slides_json = _json.dumps(slides, ensure_ascii=False)
    sys_prompt = f"""당신은 두원공조 사내 진행보고 "하우스 스타일" PPT 의 **내용 보강** 편집자입니다.
이미 만들어진 슬라이드 JSON 과, 섹션별로 수집한 '외부 웹 검색 참고 자료'가 주어집니다.
**모든 섹션의 내용을 외부 자료로 풍부하게 보강**해 같은 스키마의 슬라이드 JSON 으로 다시 출력하세요.

응답은 **반드시 다음 JSON 객체** 만 출력 (다른 텍스트·마크다운·코드블록 금지):
{{ "slides": [ {{ "layout": "house-report", "data": {{ ... }} }} ] }}

data 스키마(원본과 동일하게 유지):
{schema}

보강 규칙(매우 중요):
- **원본(첨부) 내용이 우선**입니다. 외부 자료는 배경·시장 수치·동향·공개 벤치마크·표준 등으로 **보탤** 뿐,
  원본의 내부 사실(불량 내용·내부 수치·일정)을 **삭제하거나 대체하지 마세요**.
- **슬라이드 수와 기존 블록·섹션(■) 구조를 그대로 유지**하세요(슬라이드를 늘리거나 합치지 말 것).
  각 섹션 '안에서' 표 행·불릿·짧은 비교·수치를 더해 내용을 채우세요. 비어 보이던 블록을 우선 채웁니다.
- 외부 자료에 표로 정리할 만한 비교·수치가 있으면 해당 text 블록을 table 로 바꿔도 좋습니다.
- **표 행 구조 보존**: 각 row 는 열 개수만큼의 셀 배열 `[셀, 셀, …]` 입니다. 한 행을 `{"lines":[...]}`
  단일 셀로 감싸거나, **한 행의 값(연도·판매·증가율·점유율 등)을 여러 행으로 쪼개지 마세요.**
- **추측 금지**: 원본 또는 제공된 외부 참고 자료에 실제로 있는 수치·고유명사만 쓰세요. 없으면 지어내지 마세요.
- **보안·AI 활용 유의사항/경고/권고 같은 메타 코멘트를 추가하지 마세요** — 보고서 주제 내용만 보강합니다.
- 컴팩트 유지: 표 colW 합 25.9, align 은 "l"/"c" 만(=右 금지), rowH 금지, 제목에 ■/▣ 금지.
- 언어: {language}.
"""
    user_prompt = f"""[기존 슬라이드 JSON]
{slides_json}

[섹션별 외부 웹 검색 참고 자료]
{research_notes}

위 외부 자료를 활용해 **모든 섹션의 내용을 보강**한 슬라이드 JSON 객체 하나만 출력하세요.
원본 내부 사실은 보존하고, 외부 자료는 보태기만 하세요. 다른 텍스트는 절대 넣지 마세요."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_house_fill_messages(
    slide_data: dict,
    content: str,
    used_pct: int,
    language: str,
    schema: str,
) -> list[dict[str, str]]:
    """채움률이 낮은 house 슬라이드를 **자료에 근거해 더 채우는** 메시지(내부 Qwen 전용).

    한 페이지를 넘기지 않으면서 본문이 ~90% 차도록 기존 섹션에 표 행·불릿·블록을 더한다.
    추측 금지(자료에 있는 사실만), 보안·AI 유의사항 같은 메타 코멘트 금지.
    """
    import json as _json

    blocks_json = _json.dumps(slide_data.get("blocks") or [], ensure_ascii=False)
    title = str(slide_data.get("title") or "")
    sys_prompt = f"""당신은 두원 사내 진행보고 "하우스 스타일" PPT 슬라이드의 **내용 채우기** 편집자입니다.
한 슬라이드가 본문 영역의 약 {used_pct}% 밖에 안 차서 아래에 큰 공백이 있습니다. 이 슬라이드 내용을
**아래 자료에 근거해 더 채워** 본문이 **약 90%** 차도록 만드세요(한 페이지를 넘기지 말 것).

응답은 **다음 JSON 객체 하나만** (다른 텍스트·코드블록 금지):
{{ "slides": [ {{ "layout": "house-report", "data": {{ "title": "{title}", "blocks": [ <보강된 블록 배열> ] }} }} ] }}

채우기 규칙:
- **기존 블록·섹션(■)을 유지**하고, 그 안에 표 행·불릿·짧은 항목을 더하거나, 자료에 근거한 블록
  (표/차트/소제목+표/2단 row)을 1~3개 **추가**해 빈 공간을 채우세요.
- **추측·창작 금지**: 아래 자료에 실제로 있는 수치·고유명사만 쓰세요. 자료에 없으면 주제에 관해
  일반적으로 알려진 배경·구분·고려사항·향후 방향을 정성적으로 보태되 **구체 수치·고유명사·날짜는 지어내지 마세요.**
- **한 페이지를 넘기지 마세요**(블록을 과하게 넣어 다음 장으로 넘어가지 않게). 목표 ~90%.
- 보안·기밀·AI 활용 관련 유의사항/경고/권고 같은 메타 코멘트는 넣지 마세요.

[블록 스키마]
{schema}

- 언어: {language}.
"""
    user_prompt = f"""[현재 슬라이드 블록 — 이 내용을 보존하고 더 채우세요]
{blocks_json}

[참고 자료(첨부·검색 결과)]
{content}

위 슬라이드를 자료에 근거해 ~90% 차도록 보강한 JSON 객체 하나만 출력하세요."""
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_messages(
    content: str,
    n_slides: int,
    language: str,
    tone: str,
    instructions: str | None,
    include_title_slide: bool,
    include_toc: bool,
    family: str = "doowon-v2",
    exact_count: bool = False,
) -> list[dict[str, str]]:
    """슬라이드 구조 생성용 chat 메시지 구성.

    exact_count=True 면 사용자가 장수를 직접 지정한 것(house 에서 정확히 n장 유도에 사용).
    """
    _, fam = resolve_family(family)
    schema = _FAMILY_SCHEMAS.get(family, _LAYOUT_SCHEMA)

    if fam.get("design") == "brandlogy":
        return _build_brandlogy_messages(
            content=content,
            n_slides=n_slides,
            language=language,
            tone=tone,
            instructions=instructions,
            include_title_slide=include_title_slide,
            schema=schema,
        )

    if fam.get("design") == "house":
        return _build_house_messages(
            content=content,
            n_slides=n_slides,
            language=language,
            tone=tone,
            instructions=instructions,
            schema=schema,
            exact_count=exact_count,
        )

    if family == "doowon-v2":
        layouts_list = ", ".join(f'"{k}"' for k in fam["builders"].keys())
        body_slides = n_slides - (1 if include_title_slide else 0)
        structure_hint = (
            f"표지(cover) 1장 + 본문 {body_slides}장 = 총 {n_slides}장. "
            '본문은 "2col-comparison" / "benchmark-tiles" / "comparison-table" / '
            '"4step-framework" 중에서 선택. 마지막 슬라이드는 "4step-framework" 권장. '
            "같은 layout 연속 2회 이상 반복 금지."
        )
        family_intro = "두원공조 표준 양식 v2 (16:9, doowon-blue/red, 현대하모니 M)"
        body_rule = (
            "- 모든 본문 슬라이드는 TAKEAWAY (DOOWON 시사점) 필드를 반드시 채우세요. "
            '단, "4step-framework"는 TAKEAWAY 대신 CONCLUSION_TITLE/CONCLUSION_BODY 사용.'
        )
    else:
        body_layout = fam["body_layouts"][0]
        layouts_list = f'"{fam["cover_layout"]}", "{body_layout}"'
        structure_hint = (
            f'표지("{fam["cover_layout"]}") 1장 + 본문("{body_layout}") 1장 = 총 2장. '
            "본문은 정확히 1개만 생성하고, layout은 위에 명시한 값을 그대로 사용."
        )
        family_intro = f"두원공조 {fam['name']} (A4 가로, doowon-blue/red, 현대하모니 M)"
        body_rule = (
            "- 본문 슬라이드는 위 스키마의 모든 필드를 가능한 한 채워주세요. "
            '입력 자료에 없는 숫자/이름은 추측하지 말고 빈 문자열("") 또는 자연스러운 placeholder 사용.'
        )
        n_slides = 2

    sys_prompt = f"""당신은 두원공조 AI TFT의 보고서 자동 작성 어시스턴트입니다.
주어진 주제와 자료를 바탕으로 {family_intro}에 맞는 슬라이드 구조를 JSON으로 만드세요.

응답은 **반드시 다음 JSON 객체** 만 출력 (다른 텍스트·마크다운·코드블록 금지):
{{
  "slides": [
    {{ "layout": "<{layouts_list} 중 하나>", "data": {{ ... }} }},
    ...
  ]
}}

{schema}

요청 사항:
- {structure_hint}
- 언어: {language}
- 톤: {tone}
{body_rule}
- **HEADER 필드에 ▣ 기호 절대 넣지 말 것** — 빌더 코드가 자동으로 ▣를 앞에 붙입니다.

{_KO_RULES if language == "Korean" else ""}
{instructions or ""}
"""

    user_prompt = f"""주제 / 입력 자료:
---
{content}
---

위 자료로 {n_slides}장 짜리 슬라이드 JSON 을 생성하세요. JSON 객체 하나만 출력하고 다른 텍스트는 절대 넣지 마세요."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_retry_messages(
    base_messages: list[dict[str, str]],
    raw_response: str,
    error: str,
) -> list[dict[str, str]]:
    """1차 JSON 파싱 실패 시 재시도용 메시지."""
    return base_messages + [
        {"role": "assistant", "content": raw_response},
        {
            "role": "user",
            "content": (
                f"이전 응답이 올바른 JSON이 아니었습니다 (오류: {error}). "
                "JSON 객체 하나만, 코드블록·주변 텍스트 없이 다시 출력하세요. "
                "슬라이드는 5장 이내로 짧게, 본문 단락은 200자 이내로 간결하게."
            ),
        },
    ]


def build_chat_edit_messages(
    slides: list[dict],
    message: str,
    history: list[dict] | None,
    family: str = "doowon-v2",
) -> list[dict[str, str]]:
    """챗봇 수정(단계 3)용 chat 메시지 구성."""
    import json

    _, fam = resolve_family(family)
    layouts_list = ", ".join(f'"{k}"' for k in fam["builders"].keys())
    current = {
        "slides": [
            {"index": i + 1, "layout": s["layout"], "data": s["data"]} for i, s in enumerate(slides)
        ]
    }
    current_json = json.dumps(current, ensure_ascii=False)

    sys_prompt = f"""당신은 PPT 슬라이드 수정 어시스턴트입니다. 사용자 메시지를 보고 의도를 파악해 JSON으로 응답하세요.

현재 슬라이드 상태:
{current_json}

응답은 반드시 다음 JSON 객체 하나만 출력 (코드블록·잡담 금지):
{{
  "intent": "edit" | "chat",
  "answer": "사용자에게 보여줄 한국어 응답",
  "slide_index": <intent=edit 일 때 1-based 슬라이드 번호>,
  "layout": "<intent=edit 일 때 {layouts_list} 중 하나>",
  "data": {{ ... intent=edit 일 때 해당 layout 의 data 필드들 (전체 채워야 함) ... }}
}}

규칙:
- 슬라이드 수정/내용 변경/색상·텍스트 조정 요청 → intent="edit"
- 단순 질문·잡담·도움말 요청 → intent="chat" (slide_index/layout/data 생략 가능)
- edit 일 때 slide_index, layout, data 모두 필수. data 는 해당 layout 의 **전체** 필드를 재생성 (기존 값 유지하고 싶은 부분도 포함)
- 모든 텍스트는 한글. 한자·일본 가나·키릴 등 비한글 금지.
"""
    msgs: list[dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    for h in (history or [])[-6:]:
        role = h.get("role")
        if role in ("user", "assistant") and h.get("content"):
            msgs.append({"role": role, "content": h["content"]})
    msgs.append({"role": "user", "content": message})
    return msgs


def compute_slide_count(
    content: str,
    slide_range: str | None,
    include_title_slide: bool,
    include_toc: bool,
    *,
    rng: object | None = None,
) -> int:
    """doowon-v2 본문 슬라이드 수 자동 산정 (콘텐츠 길이 기반).

    ``rng`` 는 ``random`` 모듈 호환 객체(테스트 주입용). 기본은 표준 random.
    """
    import random as _random

    # 사용자가 정확한 페이지 수를 고른 경우(예: "3") → 그 값을 그대로 사용(1~20 클램프).
    if slide_range and str(slide_range).strip().isdigit():
        return max(1, min(20, int(str(slide_range).strip())))

    rng = rng or _random
    lo, hi = SLIDE_RANGE_MAP.get(slide_range or "", (6, 10))
    cl = len(content)
    if cl < 100:
        n_body = lo
    elif cl > 1000:
        n_body = hi
    else:
        n_body = lo + round(((cl - 100) / 900) * (hi - lo))
        n_body = max(lo, min(hi, n_body))
    n_body = max(lo, min(hi, n_body + rng.choice([-1, 0, 0, 1])))
    return n_body + (1 if include_title_slide else 0) + (1 if include_toc else 0)


__all__ = [
    "DEFAULT_FAMILY",
    "build_messages",
    "build_retry_messages",
    "build_chat_edit_messages",
    "compute_slide_count",
    "build_brandlogy_brief_messages",
    "build_brandlogy_layout_prompt",
    "build_brandlogy_fill_messages",
    "build_brandlogy_fill_slide_messages",
    "build_brandlogy_full_prompt",
    "build_brandlogy_html_prompt",
    "build_brandlogy_html_edit_prompt",
    "build_doowon_free_prompt",
    "build_doowon_qwen_outline_messages",
    "build_doowon_qwen_fill_messages",
    "build_doowon_seminar_fill_messages",
    "build_doowon_seminar_trip_messages",
    "build_doowon_education_fill_messages",
    "build_education_result_messages",
]
