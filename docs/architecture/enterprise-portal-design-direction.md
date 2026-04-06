# 엔터프라이즈 포털 디자인 방향

## 목적

이 문서는 이 저장소에서 프론트엔드 화면, 레이아웃, 스타일 지시를 만들 때 따르는 기본 디자인 방향을 정의한다. 대상은 공개 마케팅 사이트가 아니라 `로그인 후 장시간 사용하는 엔터프라이즈 업무 포털` 이다.

## 기본 입장

- 기본 화면은 `랜딩 페이지`가 아니라 `앱 셸` 이다.
- 데스크톱 기본형은 `좌측 사이드바 메뉴 + 상단 유틸리티 바 + 중앙 작업면 + 필요 시 우측 컨텍스트 패널` 이다.
- 검색은 매우 중요하지만, 정보구조를 대체하지 않는다.
- 홈 화면도 마케팅형 hero가 아니라 `작업 시작점` 이어야 한다.
- 시각 스타일은 인위적으로 화려한 AI 스타트업 랜딩보다 `차분하고 명확한 enterprise tool` 쪽을 우선한다.

## 현재 1차 레퍼런스

- 현재 인증 후 업무 포털의 1차 화면 레퍼런스는 `ClickUp` 데스크톱 제품이다.
- 새 작업면을 설계할 때는 ClickUp의 `좌측 앱 바 + 서브 사이드바 + 상단 작업 헤더 + 중앙 작업면` 구조를 기본 골격으로 본다.
- 프로젝트/문서/작업 화면은 ClickUp처럼 `높은 정보 밀도`, `짧은 라벨`, `빠른 hover/selection 피드백`, `List / Board / Calendar / Gantt / Table` 같은 뷰 전환을 우선 참고한다.
- 특히 `PMS`, `Docs`, `Planner` 계열 화면은 카드형 랜딩보다 ClickUp식 workbench 구성을 우선한다.
- 단, 브랜드 자산, 로고, 제품명, 고유 카피를 그대로 복제하는 것은 이 문서의 범위에 포함하지 않는다. 이 문서는 구조, 밀도, 상호작용 패턴을 맞추기 위한 기준만 다룬다.

## 공식 레퍼런스에서 채택한 원칙

### GitHub Primer

- Primer의 `NavList` 는 부모 페이지 안에서 child view를 전환하는 `parent-detail` 패턴과 사이드바 사용을 전제로 한다.
- Primer `PageLayout` 은 `content + pane` 조합과 가변 pane 폭을 명시적으로 지원한다.
- 이 저장소는 `좌측 정보구조`, `중앙 주 작업면`, `우측 보조 pane` 패턴을 기본 작업면으로 본다.

### Microsoft Fluent 2

- Fluent는 navigation을 앱의 `high-level wayfinding` 으로 보고, 짧고 평이한 언어와 높은 scanability를 요구한다.
- Fluent는 사람들이 일반적으로 `navigation은 왼쪽`, `notification 패턴은 오른쪽` 을 기대한다고 명시한다.
- Drawer는 `보조 정보와 단순 액션` 에 쓰고, 길고 복잡한 작업을 억지로 넣지 않는다.

### GitLab Pajamas

- GitLab은 `persistent left sidebar` 를 앱의 주 wayfinding으로 사용하고, 2단계까지만 깊이를 허용한다.
- 네비게이션 라벨은 가능하면 `1-2단어` 의 짧고 기억하기 쉬운 이름을 사용한다.
- 큰 화면에서는 기본적으로 사이드바를 노출하고, 작은 화면에서는 overlay로 전환한다.
- 네비게이션은 학습된 행동과 직접 연결되므로 구조 변경은 드물고 신중해야 한다.

### IBM Carbon

- Carbon은 `UI shell left panel` 과 `data table` 을 엔터프라이즈 제품의 핵심 조합으로 다룬다.
- 데이터 표시는 카드보다 `효율적 조직화와 표시` 가 우선이다.
- 이 저장소는 표, 리스트, 필터, 상태 배지, 우측 상세 패널을 카드보다 우선한다.

### Anthropic / OpenAI 공식 프롬프트 지침

- Anthropic은 명확하고 직접적인 지시, 필요한 맥락 제공, 역할과 작업별 컨텍스트 분리를 권장한다.
- Anthropic은 frontend output 개선에서 `distributional convergence` 를 피하기 위해, 피해야 할 기본값과 선호하는 대안을 구체적으로 주는 방식을 제시한다.
- OpenAI와 Anthropic 모두 큰 전역 지시보다 `작업 맥락에 맞는 구체적 제약과 examples` 가 더 중요하다는 방향을 취한다.
- 따라서 디자인 지시는 루트 메모리에 상주시키지 않고, 프론트엔드 작업 때만 이 문서를 선택적으로 로드한다.

## 우리 프로젝트의 시각적 원칙

### 레이아웃

- 데스크톱에서는 좌측 사이드바를 항상 기본 노출로 둔다.
- 사이드바는 `도메인 이동`, `즐겨찾기`, `최근 이동`, `관리자 진입`, `환경 전환` 을 맡는다.
- 중앙은 현재 작업의 주 화면이다.
- 우측 패널은 `근거`, `상세 정보`, `빠른 액션`, `보조 폼` 용도로만 쓴다.
- 모바일과 좁은 화면에서는 좌측 사이드바를 overlay drawer로 바꾸되 정보구조는 유지한다.

### 정보구조

- 최상위 메뉴는 짧고 명확한 명사 또는 작업명으로 유지한다.
- 최상위 메뉴 수는 억지로 많게 만들지 않는다.
- 카테고리는 깊게 중첩하지 않는다. 기본은 2단계 이내다.
- 검색은 메뉴를 대신하지 않고, `빠른 점프` 와 `근거형 조회` 역할을 맡는다.

### 시각 언어

- 밝은 중립 배경, 선명한 텍스트 대비, 얇은 경계선, 절제된 radius를 기본값으로 둔다.
- 배경은 과장된 그라데이션이나 glassmorphism보다 `단색 또는 매우 약한 surface variation` 을 우선한다.
- 그림자는 얕고 드물게만 사용한다.
- 색은 `주조색 1개 + 보조 중립색` 중심으로 간다.
- 강조는 색보다 `위계, 정렬, 선택 상태, border, weight 변화` 로 먼저 해결한다.
- 선택 상태, active rail, hover tint, tab underline 같은 상호작용 피드백은 ClickUp처럼 `작고 빠르고 반복 가능한 패턴` 으로 통일한다.

### 타이포그래피

- 광고성 hero typography보다 업무용 가독성과 계층을 우선한다.
- 기본 본문 폰트는 기술 문서와 업무 툴에 어울리는 계열을 우선한다.
- 이 프로젝트에서는 `IBM Plex Sans KR / IBM Plex Sans / Pretendard` 조합이 1차 후보이고, 코드/메타 정보에는 `IBM Plex Mono` 류를 우선한다.
- 흔한 AI 산출물처럼 `Inter + 보라 그라데이션 + 둥근 카드` 조합으로 수렴하지 않는다.

### 컴포넌트 우선순위

- 우선: sidebar nav, toolbar, filter bar, list, data table, segmented controls, drawer, detail pane, status badge, breadcrumb
- 후순위: hero block, marketing card mosaic, decorative metric tiles, oversized empty whitespace
- 우선: dense sidebar sections, work header, view switch tabs, editable row/list, kanban column, table toolbar, quick add modal

## 피해야 하는 AI스러운 안티패턴

- 로그인 후 포털 첫 화면에 큰 hero headline을 두는 것
- 의미 없이 큰 카드들을 여러 장 배열하는 `card soup`
- 보라색 또는 청록 계열의 과한 gradient
- glassmorphism, neon glow, 과장된 blur
- 너무 많은 pill/chip/button variation
- 과하게 둥근 radius와 장식성 shadow
- 근거 없는 대형 통계 카드와 bento 그리드
- 지나치게 감성적인 카피와 모호한 메시지
- 실제 업무 흐름 대신 “AI가 뭔가 대단해 보이는” 연출 중심 구성

## 권장하는 포털 패턴

- `좌측 메뉴 / 중앙 리스트 또는 작업면 / 우측 상세 또는 근거 pane`
- `테이블 + 필터 바 + 저장된 뷰`
- `목록 클릭 -> 우측 상세 drawer`
- `검색 결과 + citation panel + 다음 액션`
- `상단 유틸리티 바 + 현재 컨텍스트 제목 + 보조 상태`
- `설정/관리 화면` 은 카드 모음보다 `섹션 리스트 + 폼 + inline help`
- `앱 바 / 서브 사이드바 / 헤더 / 뷰 탭 / 본문 작업면` 의 5단 구조를 일관되게 유지
- `Quick Add`, `New Task`, `New Doc` 같은 빠른 생성 액션은 헤더나 사이드 하단의 고정 액션으로 배치

## 프론트엔드 지시 작성 원칙

- 추상적인 “세련되게” 보다 구체적인 금지/선호 항목을 같이 준다.
- “무엇을 만들지” 뿐 아니라 “무엇을 만들지 말지” 를 같이 준다.
- 디자인 레퍼런스는 많아도 2-3개만 준다.
- 현재는 ClickUp을 1차 레퍼런스로 삼되, 문서와 구현 지시에서는 `상호작용 패턴, 화면 밀도, 정보구조, 레이아웃 규칙` 을 우선 명시한다.
- 참고 레퍼런스를 주더라도 `브랜드 자산 복제` 가 아니라 `상호작용 패턴과 밀도` 를 가져온다.
- 프롬프트에는 현재 화면의 사용자, 주요 작업, 밀도, 우선 컴포넌트, 제외 패턴을 같이 적는다.
- 도메인 화면에서 반복되는 UI는 먼저 `packages/ui` 공통 컴포넌트로 확인하고, 없으면 거기서 먼저 구현한다.
- 버튼, 배지, 패널, 테이블, 드로어, 토스트, 차트는 로컬 CSS로 다시 만들지 않는다.

## 재사용 가능한 디자인 지시 블록

```text
<enterprise_portal_design>
Design an authenticated enterprise portal workbench, not a marketing landing page.

Information architecture:
- Use a persistent left sidebar on desktop as the primary navigation surface.
- Keep top-level navigation short, scannable, and stable.
- Use search as a fast access tool, not as a substitute for navigation.
- Prefer a central work surface with an optional right-side contextual pane or drawer.

Visual direction:
- Use a calm enterprise product aesthetic: neutral surfaces, crisp borders, restrained radius, minimal shadows, strong hierarchy.
- Prioritize lists, tables, filters, split views, drawers, status badges, and breadcrumbs over decorative cards.
- Keep typography practical and distinctive enough to avoid generic AI-generated output; prefer technical or editorially disciplined font pairings over default Inter-style choices.
- Treat ClickUp as the primary interaction-density reference for authenticated work surfaces, especially for the app rail, sub-sidebar, work header, and view tabs.

Avoid:
- hero-first layouts
- bento dashboards and card soup
- purple gradients on white
- glassmorphism, neon glow, heavy blur
- oversized marketing copy
- random decorative motion
- vague “AI magic” styling

Interaction rules:
- Left is for navigation, center is for the main task, right is for details, evidence, and quick actions.
- Drawers are for supplemental information or short flows, not for long multi-step primary workflows.
- Keep labels plain and task-oriented.
- Prefer fast, compact, ClickUp-like workbench interactions over spacious dashboard styling.

If unsure, prefer the interaction discipline of GitHub, GitLab, Microsoft, or IBM enterprise products over flashy startup landing pages.
</enterprise_portal_design>
```

## 프론트엔드 리뷰 체크리스트

- 좌측 사이드바가 기본 네비게이션으로 살아 있는가
- 앱 바와 서브 사이드바가 ClickUp처럼 분리된 역할을 가지는가
- 검색이 정보구조를 대체하지 않고 보완하는가
- 홈이 마케팅 랜딩처럼 보이지 않는가
- 카드 대신 리스트/테이블/패널 중심으로 풀렸는가
- 헤더와 뷰 탭이 ClickUp식 dense workbench 흐름에 맞는가
- 우측 pane/drawer가 보조 역할만 하는가
- 라벨이 짧고 분명한가
- 색, radius, shadow가 절제되어 있는가
- 첫인상이 “AI 데모 사이트”가 아니라 “업무용 제품”에 가까운가

## 참고 소스

- GitHub Primer navigation: https://primer.style/product/ui-patterns/navigation/
- GitHub Primer PageLayout: https://primer.style/product/components/page-layout/
- Microsoft Fluent 2 Nav: https://fluent2.microsoft.design/components/web/react/core/nav/usage
- Microsoft Fluent 2 Drawer: https://fluent2.microsoft.design/components/web/react/core/drawer/usage
- GitLab Pajamas navigation sidebar: https://design.gitlab.com/patterns/navigation-sidebar/
- GitLab Pajamas tabs guidance: https://design.gitlab.com/components/tabs
- IBM Carbon UI shell left panel: https://v10.carbondesignsystem.com/components/UI-shell-left-panel/code/
- IBM Carbon data table: https://v10.carbondesignsystem.com/components/data-table/usage/
- Anthropic frontend design skill article: https://claude.com/blog/improving-frontend-design-through-skills
- Anthropic prompt clarity guidance: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct
- Anthropic prompt templates and variables: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- OpenAI prompting guide: https://developers.openai.com/api/docs/guides/prompting
- OpenAI prompt optimizer: https://platform.openai.com/docs/guides/prompt-optimizer/
- Reddit discussion on avoiding generic AI-looking UI: https://www.reddit.com/r/vibecoding/comments/1rr0dwy/all_ai_websites_and_designs_look_the_same_has/
- GitHub gist of Claude frontend aesthetics prompt: https://gist.github.com/hashimwarren/b544f89bdb50e4877d0e603ad547e18f

## 관련 규약

- 공통 UI 거버넌스: [docs/architecture/ui-component-governance.md](/Users/edward/projects/doowon/docs/architecture/ui-component-governance.md)
