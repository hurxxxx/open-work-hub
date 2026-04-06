# Web App Rules

- `apps/web` 는 프론트엔드 조립 계층이다.
- 전역 레이아웃, 앱 부트스트랩, 공통 스타일만 여기서 직접 소유한다.
- 도메인별 UI 로직은 `src/domains/*` 아래에서만 확장한다.
- 공통 컴포넌트는 먼저 `packages/ui`에서 찾고, 없으면 거기서 먼저 구현한다.
- 공통화 가능한 UI를 앱 로컬 CSS로 다시 만들지 않는다.
- `apps/web`는 공통 컴포넌트를 조합하고, 레이아웃과 페이지별 예외만 직접 소유한다.
- 인증 후 화면은 `좌측 사이드바 메뉴 + 중앙 작업면 + 필요 시 우측 pane` 을 기본으로 한다.
- 홈은 카드 대시보드보다 검색 진입점, 최근 작업, 즐겨찾기, 할당 작업에 집중한다.
- 마케팅 hero, 과한 카드 구성, glassmorphism, neon glow, 보라 gradient 같은 AI스러운 기본값을 피한다.
- 디자인 상세 기준은 `docs/architecture/enterprise-portal-design-direction.md` 를 따른다.
- 공통 UI 기준은 `docs/architecture/ui-component-governance.md` 를 따른다.
- 관련 시나리오는 `documents-rag`, `plm-query`, `draft-generation`, `pms`다.
