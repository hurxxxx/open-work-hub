# Web Domain Rule: shared

- 앱 shell, 상단 검색, 레이아웃, 공통 배지/섹션 표현은 직접 재구현하지 않고 `packages/ui`를 우선 사용한다.
- 새 공통 UI가 필요하면 도메인 안이 아니라 `packages/ui`에 먼저 추가한다.
- 도메인별 상세 규칙은 각 도메인 폴더에서 관리한다.
- 앱 로컬 CSS는 layout composition과 page-specific exception만 소유한다.
