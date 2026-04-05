# UI 컴포넌트 거버넌스

## 목적

이 문서는 엔터프라이즈 포털 UI에서 반복적으로 사용하는 컴포넌트의 단일 진실원본과 사용 규칙을 정의한다. 목표는 `스타일 일관성`, `접근성`, `중복 제거`, `에이전트 간 구현 편차 축소`다.

## 진실원본

- 공통 UI 소스 오브 트루스는 `packages/ui` 다.
- 앱과 도메인은 `packages/ui`의 export를 우선 사용한다.
- 새 UI가 필요하면 도메인에서 임시 구현하지 말고 먼저 `packages/ui`에 추가한다.

## 기본 규칙

- 새 화면을 만들기 전에 먼저 `packages/ui`에 필요한 컴포넌트가 있는지 확인한다.
- 버튼, 배지, 패널, 툴바, 필터 바, 데이터테이블, 드로어, 토스트, 차트는 앱 안에서 직접 재구현하지 않는다.
- 앱은 공통 컴포넌트를 `조합`만 한다.
- 앱은 공통 컴포넌트의 스타일 토큰을 재정의하지 않는다.
- 외부 UI 라이브러리는 앱에서 직접 import하지 않는다. `packages/ui` wrapper를 통해서만 사용한다.

## 기술 기준

- 스타일 체계는 `Tailwind CSS v4 + CSS variables`다.
- variant와 class 조합은 `class-variance-authority`, `tailwind-merge`, `clsx`를 사용한다.
- 접근성과 overlay primitive는 `Radix UI`를 사용한다.
- 데이터테이블은 `@tanstack/react-table` wrapper를 사용한다.
- 차트는 `recharts` wrapper를 사용한다.

## 필수 공통 컴포넌트

- Foundation: `Button`, `IconButton`, `Input`, `SearchField`, `Select`, `Tabs`, `Badge`, `StatusBadge`, `Panel`, `Toolbar`, `FilterBar`
- Layout: `AppShell`, `SidebarNav`, `Topbar`, `SplitPane`, `DetailDrawer`
- Data display: `DataTable`, `DataTableToolbar`, `EmptyState`, `Skeleton`, `MetricInline`, `ChartFrame`, `LineChartCard`, `BarChartCard`, `DonutChartCard`
- Feedback: `ToastProvider`, `ToastViewport`, `useToast`, `InlineNotice`

## 구현 우선순위

- 첫 소비처는 `documents-rag`다.
- 그 다음 `plm`, `drafts`, `wiki-pms` preview를 공통 컴포넌트 조합으로 옮긴다.
- 새 도메인 UI도 공통 컴포넌트가 먼저고, 예외가 필요하면 공통 패키지에 variant를 추가한다.

## 리뷰 기준

- 도메인에서 중복 버튼/배지/테이블/드로어/토스트/차트를 만들면 리뷰에서 수정 대상으로 본다.
- 공통화 가능한 컴포넌트를 로컬 CSS로 다시 만들면 실패로 본다.
- `apps/web` 코드에서 `@radix-ui/*`, `@tanstack/react-table`, `recharts`를 직접 import하면 실패로 본다.

## 에이전트 규칙

- 프론트엔드 작업 전 이 문서를 읽는다.
- 공통 UI가 필요한 변경이라면 먼저 `packages/ui`를 탐색한다.
- 없으면 `packages/ui`에 추가하고, 소비처는 그 다음에 바꾼다.
- 공통 컴포넌트를 추가하거나 바꾸면 관련 도메인 UI를 함께 정리한다.
