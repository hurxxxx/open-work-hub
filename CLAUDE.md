@agents.md
@docs/agents/context-loading-policy.md

## Claude Code

- 루트 메모리는 최소화한다. 공통 규약은 `agents.md` 와 `docs/agents/context-loading-policy.md` 만 기본 로드한다.
- 상세 규약은 작업에 맞는 문서만 선택적으로 읽는다. 기본적으로 관련 없는 시나리오 문서와 도메인 설명은 로드하지 않는다.
- 세부 경로별 규칙은 `.claude/rules/` 를 따른다.
- 반복 작업은 `.claude/commands/` 와 `.claude/agents/` 를 우선 사용한다.
- 훅 강제 규칙은 `.claude/settings.json` 에서 관리한다.
- 하네스 변경 작업은 관련 시나리오 문서와 eval spec 을 함께 갱신한다.
- 스프린트형 작업 흐름과 learn/checkpoint/retro/document-release 습관은 `docs/ops/*` 를 따른다.
