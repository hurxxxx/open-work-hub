# Project Agent Rules

이 파일은 이 저장소의 유일한 활성 에이전트 지시 진입점이다.

## Single Source

- 활성 규칙 원본은 루트 `agents.md` 하나만 사용한다.
- 새 `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/` 같은 도구별 지시 경로를 다시 활성 경로에 만들지 않는다.
- 과거 지시 파일은 작업 트리에 남기지 않는다. 필요하면 Git 히스토리에서 복원한다.
- 복원이 필요할 때는 `git log --all -- '**/AGENTS.md' 'CLAUDE.md' '.claude' '.codex'` 로 커밋을 찾고 `git restore --source <commit> -- <path>` 를 사용한다.
- 삭제한 문서도 같은 방식으로 복원한다. 예: `git log -- docs/architecture docs/harness docs/ops` 후 `git restore --source <commit> -- <path>`.

## Project Invariants

- 사용자의 별도 요청이 없으면 `git commit` 과 `git push` 를 하지 않는다.
- `legacy_ai_portal_prototype/` 는 레거시 보관본이다. 새 구현의 기준 구조나 재사용 소스로 삼지 않는다.
- 레거시 프로토타입은 기능 흐름, 화면 구성, 프롬프트, 샘플 데이터 확인이 필요할 때만 참고한다.
- 특별히 요청받지 않은 한 `legacy_ai_portal_prototype/` 내부 파일은 수정하지 않는다.
- 익숙하지 않은 패턴은 바로 만들지 말고 공식 문서나 기존 구현을 먼저 확인한다.

## UI Invariants

- 과도한 대시보드 통계 카드, BoxShadow 카드, 두꺼운 외곽선은 피한다.
- ClickUp, Jira 같은 글로벌 SaaS 스타일의 평면적 레이아웃, 넉넉한 여백, Dense Typography 를 우선한다.

## Context Policy

- 기본 컨텍스트는 코드와 현재 작업 파일만 사용한다.
- `/docs` 아래 문서는 모두 보관용 참고 자료로 취급한다.
- `docs/planning/`, `docs/product/`, `docs/meetings/` 는 사용자가 특정 문서를 보라고 지시할 때만 읽는다.
- 사용자가 명시하지 않으면 문서보다 현재 코드와 테스트를 우선한다.
