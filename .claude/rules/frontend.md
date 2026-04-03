---
paths:
  - "apps/web/**/*"
  - "packages/web/**/*"
  - "packages/ui/**/*"
---

# Frontend Rules

- 홈은 카드형 포털이 아니라 검색 중심 랜딩으로 유지한다.
- 기본 화면 구조는 `좌측 조건`, `중앙 결과`, `우측 근거/액션` 3패널을 우선한다.
- 검색/근거 UX는 `Glean`, 작업 밀도와 상태 표시는 `Linear` 스타일을 참고한다.
- 도메인 내부 UI 로직은 해당 `packages/web/<domain>` 안에만 둔다.
- API contract 는 문서 또는 생성된 타입을 통해서만 연결한다.
