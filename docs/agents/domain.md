# 에이전트 문서 소유권

문서 트리와 수명은 [`docs/README.md`](../README.md), 모든 개발 도구가 공유하는 핵심 규칙은
루트 [`AGENTS.md`](../../AGENTS.md)가 소유한다. 이 문서는 `docs/agents/` 안의 상세 개발 지침을
판단 유형에 따라 라우팅한다.

| 판단 | 소유 문서 |
| --- | --- |
| 코드 구조·진입점·추상화 원칙 | [LLM 친화 개발](llm-friendly-development.md) |
| 변경 위험과 검증 깊이 | [구현 검증 하네스](vibe-coding-harness.md) |
| 공용 UI 재사용 | [UI 컴포넌트](ui-components.md) |
| 유사 기능의 공유 모델 여부 | [조합형 추상화](composable-abstractions.md) |
| 로컬 diff·commit·PR 코드 리뷰 | [로컬 Codex/LLM 리뷰](local-codex-review.md) |
| GitHub Issue 사용 | [Issue Tracker](issue-tracker.md) |
| GitHub Issue 라벨 판단 | [Triage Labels](triage-labels.md) |

작업마다 위 문서를 전부 읽지 않는다. 현재 코드와 테스트를 먼저 확인하고 실제 판단에 필요한
소유 문서만 읽는다. 도메인·앱 계약은 각각 `docs/domains/<domain>/`,
`docs/apps/<app-id>/`에서 시작한다. 제품 UI 기준은 `docs/product/`에서 시작한다.

제품 동작의 최종 근거는 코드와 테스트다. 임시 계획, 원시 로그, QA 산출물과 완료 보고서를
새 정본 디렉터리로 만들지 않는다. ADR은 저장소 루트 [`adr/`](../../adr)에 두며
context map, current snapshot 또는 docs-local ADR 같은 중복 정본을 만들지 않는다.
