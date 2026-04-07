# 프론트엔드 디자인 기준

## 목적

이 문서는 새 화면이나 공통 UI를 만들 때 기존 제품과 다른 시각 언어가 생기지 않도록 하는 최소 기준이다.

## 대표 기준 소스

- 메인 화면: [apps/web/src/components/views/HomeView.tsx](/Users/edward/projects/doowon/apps/web/src/components/views/HomeView.tsx)
- 상단 프로필/유틸리티: [apps/web/src/components/layout/AppBar.tsx](/Users/edward/projects/doowon/apps/web/src/components/layout/AppBar.tsx)
- 보조 네비게이션: [apps/web/src/components/layout/SubSidebar.tsx](/Users/edward/projects/doowon/apps/web/src/components/layout/SubSidebar.tsx)
- 공통 레이아웃: [packages/ui/src/lib/layout/app-shell.tsx](/Users/edward/projects/doowon/packages/ui/src/lib/layout/app-shell.tsx), [packages/ui/src/lib/layout/sidebar-nav.tsx](/Users/edward/projects/doowon/packages/ui/src/lib/layout/sidebar-nav.tsx), [packages/ui/src/lib/layout/topbar.tsx](/Users/edward/projects/doowon/packages/ui/src/lib/layout/topbar.tsx)
- 공통 프리미티브: [packages/ui/src/lib/primitives](/Users/edward/projects/doowon/packages/ui/src/lib/primitives)

## 기본 규칙

- 구현 전에 대표 화면과 공통 컴포넌트를 먼저 확인한다.
- 새 화면은 기존 레이아웃, 간격, 타이포그래피, 색, 경계선, radius, 그림자, 상태 표현과 충돌하지 않게 맞춘다.
- 공통으로 반복되는 UI는 먼저 `packages/ui`에서 찾고, 없으면 거기에 추가한 뒤 사용한다.
- 페이지 로컬 스타일은 화면 조립과 예외 처리 위주로만 사용한다.
- 새로운 스타일 방향을 만들기보다 현재 제품의 일관성을 우선한다.

## 작업 원칙

- 메인 대시보드와 같은 대표 화면의 톤을 기준으로 잡는다.
- 같은 종류의 요소는 같은 모양과 같은 상호작용을 유지한다.
- 대표 화면과 공용 컴포넌트가 서로 다르면 공용 컴포넌트 동작을 우선하고, 필요한 경우 대표 화면을 그쪽으로 정리한다.

## 간단 체크리스트

- 대표 화면과 한 제품처럼 보이는가
- `packages/ui` 공통 컴포넌트를 우선 사용했는가
- 같은 역할의 요소가 다른 화면과 비슷한 모양과 동작을 가지는가
- 불필요한 새 스타일 규칙을 추가하지 않았는가
