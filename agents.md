# Agent Notes

- `legacy_ai_portal_prototype/` 는 신규 구축 전에 남겨두는 레거시 프로토타입 보관본입니다.
- 이 폴더는 Git 추적 대상이 아니며, 새 프로젝트의 기준 구조로 사용하지 않습니다.
- 필요할 때만 기능 흐름, 화면 구성, 프롬프트, 연동 방식, 샘플 데이터 확인용으로 참고합니다.
- 프로토타입 코드는 Windows/PowerShell/로컬 파일 저장 전제가 강하므로 그대로 재사용하지 말고 의도와 동작만 참고합니다.
- 특별히 요청받지 않은 한 `legacy_ai_portal_prototype/` 내부 파일은 수정하지 않습니다.
- 프로토타입 요약은 `legacy_ai_portal_prototype/CLAUDE.md`를 먼저 확인합니다.
- 사용자의 별도 지시가 없으면 `git commit` 과 `git push` 는 수행하지 않습니다.

## Shared Standards

- 이 저장소의 공통 규약 원본은 `docs/agents/agent-operating-standard.md` 입니다.
- 컨텍스트 최소화 원칙은 `docs/agents/context-loading-policy.md` 를 따릅니다.
- 모든 LLM 관련 작업은 먼저 `scenario_id` 로 매핑하고, 관련 있는 시나리오 문서만 선택적으로 읽습니다.
- `docs/harness/manifests/*` 와 `docs/agents/manifests/*` 의 구조화 자산을 문서 원본과 함께 읽습니다.
- 관련 없는 도메인 설명, 전체 디렉터리 구조, 다른 시나리오 문서는 기본 컨텍스트에 넣지 않습니다.
- `prompt`, `workflow`, `retrieval`, `guardrail`, `trace`, `export` 중 하나라도 바뀌면 관련 eval 과 release gate 영향을 같이 확인합니다.
- citation 없는 생성 응답은 성공으로 취급하지 않습니다.
- 익숙하지 않은 패턴은 바로 만들지 말고 공식 문서나 기존 구현을 먼저 탐색합니다.

## Root Document Policy

- 루트의 공통 규칙 진입점은 `agents.md` 다.
- `CLAUDE.md` 는 Claude Code 전용의 얇은 어댑터로만 유지한다.
- 사람용 문서는 루트에 쌓지 않고 `docs/` 아래로 분류한다.
- `docs/planning/` 는 킥오프, 과업범위, 제안/추진 계획 같은 사업/범위 문서를 둔다.
- `docs/product/` 는 제품 방향, 기능 메모, 아이디어 문서를 둔다.
- `docs/meetings/` 는 발표 스크립트, 회의 준비 자료, 회의록 문서를 둔다.
- `docs/architecture/`, `docs/agents/`, `docs/harness/`, `docs/ops/` 는 실행 기준 문서만 둔다.
- `docs/planning/`, `docs/product/`, `docs/meetings/` 문서는 요청이 직접 관련될 때만 읽고, 기본 컨텍스트에는 넣지 않는다.
