---
paths:
  - "apps/web/**/*"
  - "packages/ui/**/*"
---

# Frontend Rules

- 프론트엔드 디자인 작업 전에는 `docs/architecture/enterprise-portal-design-direction.md` 를 먼저 읽는다.
- 공통 컴포넌트 작업 전에는 `docs/architecture/ui-component-governance.md` 와 `packages/ui` 를 먼저 읽는다.
- 인증 후 제품 화면은 마케팅 랜딩이 아니라 `좌측 사이드바 메뉴 + 상단 유틸리티 바 + 중앙 작업면 + 필요 시 우측 컨텍스트 pane` 을 기본 셸로 사용한다.
- 홈은 hero-first 랜딩보다 검색, 최근 작업, 즐겨찾기, 할당 작업을 담는 포털 시작면으로 유지한다.
- 기본 작업 화면은 `좌측 조건`, `중앙 결과`, `우측 근거/액션` 또는 `중앙 작업면 + 우측 상세 pane` 구조를 우선한다.
- 검색은 정보구조를 대체하지 않는다.
- 카드형 대시보드, bento grid, glassmorphism, neon glow, purple gradient on white 같은 AI스러운 표현을 피한다.
- 표, 리스트, 필터 바, 드로어, 슬라이드오버, 상태 배지, breadcrumb 를 카드보다 우선한다.
- 시각 언어는 중립 배경, 선명한 위계, 얇은 경계선, 절제된 radius, 최소 shadow를 기본값으로 둔다.
- 공통화 가능한 버튼, 배지, 패널, 테이블, 드로어, 토스트, 차트는 도메인에서 직접 재구현하지 않는다.
- `@radix-ui/*`, `@tanstack/react-table`, `recharts`는 앱 코드에서 직접 import하지 않고 `packages/ui` wrapper만 사용한다.
- 도메인 내부 UI 로직은 해당 `apps/web/src/domains/<domain>` 안에만 둔다.
- API contract 는 문서 또는 생성된 타입을 통해서만 연결한다.
