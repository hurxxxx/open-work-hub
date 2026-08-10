# 에이전트 문서 소유권

문서 트리와 수명은 [`docs/README.md`](../README.md), 공통 에이전트
컨텍스트와 스킬 선택은 루트 [`agents.md`](../../agents.md)가 소유한다.
이 문서는 `docs/agents/` 안의 개발 지침만 라우팅한다.

| 판단 | 소유 문서 |
| --- | --- |
| 코드 구조·진입점·추상화 원칙 | [LLM 친화 개발](llm-friendly-development.md) |
| 변경 위험과 검증 깊이 | [바이브 코딩 하네스](vibe-coding-harness.md) |
| 공용 UI 재사용 | [UI 컴포넌트](ui-components.md) |
| 유사 기능의 공유 모델 여부 | [조합형 추상화](composable-abstractions.md) |
| Codex MR review 동작 | [로컬 Codex review](local-codex-review.md) |
| GitLab 이슈 상태 | [triage labels](triage-labels.md) |

작업마다 위 문서를 전부 읽지 않는다. 현재 코드와 테스트를 먼저 확인하고
실제로 필요한 판단의 소유 문서만 읽는다. 도메인·앱 계약은 각각
`docs/domains/<domain>/`, `docs/apps/<app-id>/`에서 시작한다.

`docs/final/`, `docs/archive/`, `learning/**/*.md`, 과거 계획과 원시 QA
산출물은 사용자가 명시한 경우에만 읽는다. ADR은 저장소 루트 `adr/`에
두며 `CONTEXT.md`, `CONTEXT-MAP.md`, `docs/adr/`는 만들지 않는다.
