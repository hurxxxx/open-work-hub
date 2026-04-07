# Web App Rules

- `apps/web` 는 프론트엔드 조립 계층이다.
- 전역 레이아웃, 앱 부트스트랩, 공통 스타일만 여기서 직접 소유한다.
- 도메인별 UI 로직은 `src/domains/*` 아래에서만 확장한다.
- 공통 컴포넌트는 먼저 `packages/ui`에서 찾고, 없으면 거기서 먼저 구현한다.
- 공통화 가능한 UI를 앱 로컬 CSS로 다시 만들지 않는다.
- `apps/web`는 공통 컴포넌트를 조합하고, 레이아웃과 페이지별 예외만 직접 소유한다.
- 새 화면이나 공통 UI를 만들기 전에 대표 화면과 공통 컴포넌트를 먼저 확인한다.
- 메인 화면, 앱 바, 서브 사이드바, 앱 셸과 충돌하지 않는 레이아웃과 시각 언어를 유지한다.
- 같은 역할의 요소는 기존 화면과 비슷한 모양과 상호작용을 유지한다.
- 새로운 스타일 방향을 만들기보다 현재 제품의 일관성을 우선한다.
- 디자인 상세 기준은 `docs/architecture/enterprise-portal-design-direction.md` 를 따른다.
- 공통 UI 기준은 `docs/architecture/ui-component-governance.md` 를 따른다.
- 관련 시나리오는 `documents-rag`, `plm-query`, `draft-generation`, `pms`다.
