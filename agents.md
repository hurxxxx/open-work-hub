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
- 관련 없는 도메인 설명, 전체 디렉터리 구조, 다른 시나리오 문서는 기본 컨텍스트에 넣지 않습니다.
- `prompt`, `workflow`, `retrieval`, `guardrail`, `trace`, `export` 중 하나라도 바뀌면 관련 eval 과 release gate 영향을 같이 확인합니다.
- citation 없는 생성 응답은 성공으로 취급하지 않습니다.
- 익숙하지 않은 패턴은 바로 만들지 말고 공식 문서나 기존 구현을 먼저 탐색합니다.
