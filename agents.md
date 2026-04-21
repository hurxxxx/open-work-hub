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
- 사용자가 `git commit` 또는 `git push` 를 명시적으로 요청하고 브랜치를 따로 지정하지 않으면 기본 대상은 `main` 으로 간주한다.
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

## Review Method

- 사용자가 리뷰를 요청하면 구현 성격에 따라 **가장 유효한 검토 방법을 먼저 선택**하고, 그 방법론에 맞춰 findings 를 정리한다.
- 기본 우선순위는 다음과 같다.
  - 상태 전이, 승인 게이트, 스트리밍, 워크플로, 재시도, 비동기 orchestration 은 **상태기계 / 불변식 기반 리뷰**를 우선한다.
  - API, 이벤트, 스키마, 직렬화, DB 모델, 외부 연동 계약 변경은 **계약 기반 리뷰**를 우선한다.
  - 트랜잭션, 락, 경쟁 조건, idempotency, 중복 실행 가능성이 있으면 **동시성 / 원자성 리뷰**를 우선한다.
  - 파서, 변환기, 정규화 로직, diff/merge 류는 **property / edge-case 리뷰**를 우선한다.
  - UI, 상호작용, 네비게이션, 권한 차단 화면은 **사용자 흐름 / E2E 리뷰**를 우선한다.
- 리뷰 응답에는 가능하면 선택한 방법을 짧게 밝히고, 그 방법의 핵심 불변식이나 실패 조건을 기준으로 findings 를 제시한다.
- 테스트를 볼 때는 happy path 개수보다 **선택한 방법론의 핵심 불변식을 실제로 검증하는지**를 우선 판단한다.

## AI Capability Platform

- AI capability / MCP bridge 규칙의 상세 정본은 [`adr/0002-mcp-capability-platform.md`](./adr/0002-mcp-capability-platform.md) 로 관리한다.
- 새 AI tool 또는 capability를 추가할 때는 ad-hoc router/agent 분기 대신 `register_ai_capabilities(registry)` + `AiCapabilityRegistry` 경로를 사용한다.
- AI capability는 인간용 REST request model을 재사용하지 않고 **AI 전용 DTO** 로 정의한다.
- AI tool handler는 router 로직을 복제하지 말고 **application service 경계** 를 호출한다.
- write capability는 승인 게이트를 우회하지 않는다. `approval_required=True` 인 경우 preview builder와 discoverability predicate를 함께 등록한다.
- capability 계약을 바꾸는 PR은 코드만 수정하지 말고 ADR/관련 테스트도 같은 PR에서 함께 갱신한다.

## UI E2E Testing

- 사용자가 실제 UI 검증이나 E2E 를 요청하면 로컬 서버 + `agent-browser` 로 **실제 상호작용 기반** 점검을 우선한다.
- `agent-browser` 사용 방식이 불명확하면 먼저 `agent-browser --help` 로 현재 CLI surface 를 확인한다.
- 가능하면 이미 떠 있는 로컬 서버를 재사용한다. 기본 포트는 web `127.0.0.1:4200`, api `127.0.0.1:8000` 이다.
- 서버가 안 떠 있으면 `pnpm nx dev web`, `pnpm nx dev api` 로 직접 기동한 뒤 테스트한다.
- `agent-browser` 는 named session 을 사용한다. 예: `--session doowon-e2e`, `--session doowon-admin-e2e`.
- ref (`@e1` 류) 는 `snapshot` 직후 체인에서 쓰는 것이 가장 안정적이다. 따라서 주요 상호작용은 **한 셸 호출 안에서** `open -> wait -> snapshot -> click/fill/upload -> wait -> snapshot` 순으로 묶는다.
- 테스트 중에는 최소한 다음을 함께 확인한다.
  - 최종 URL (`agent-browser get url`)
  - 접근성 스냅샷 (`agent-browser snapshot`)
  - 콘솔 로그 (`agent-browser console`)
  - 페이지 오류 (`agent-browser errors`)
- 파일 업로드/다운로드가 포함된 화면은 가능하면 실제로 한 번 왕복 확인한다. 임시 산출물은 기본적으로 `/tmp` 아래를 사용한다.
- 이 저장소의 로그인 화면에서 seed quick-login 카드 클릭은 자동화에서 불안정할 수 있다. 클릭이 먹지 않으면 로그인 폼에 이메일/비밀번호를 직접 채워서 진행한다.
- workspace shell 회귀를 볼 때는 다음 조합을 우선 점검한다.
  - legacy 최상위 경로 `/meeting`, `/docs`, `/pms`, `/planner`, `/ai` 는 PR1 `cfe4215` 에서 라우트 제거됨. 워크스페이스 진입은 항상 `/w/:workspaceSlug/<app>` 를 사용하고, 위 경로는 `NotFoundView` 로 떨어져야 정상이다 (과거처럼 자동 리다이렉트하지 않는다).
  - 접근 가능한 workspace/app 조합의 정상 진입
  - 접근 불가 workspace/app 조합의 `접근 권한 없음` 차단
  - `/w/:workspaceSlug/settings` 와 `/admin/workspaces` 의 workspace detail/member flows
- 브라우저 기반 점검을 수행한 턴에서는 결과를 루트 작업 기록 문서나 관련 작업 문서에 간단히 남겨 다음 세션이 바로 이어받을 수 있게 한다.
