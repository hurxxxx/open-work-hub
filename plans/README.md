# Active Plans

이 디렉터리는 **현재 진행 중인 실행 플랜**을 담는다. 완료된 플랜은 여기서 제거하고 요약을 [`docs/planning-log.md`](../docs/planning-log.md)에 기록한다.

## 파일 명명 규칙

```
NN-<kebab-slug>.md
```

- `NN` — 2자리 순번 (00부터). 작성 순서대로.
- `<kebab-slug>` — 주제를 짧게 요약한 kebab-case.
- 예: `00-ai-platform-roadmap.md`, `01-phase1-llm-routing.md`

## 플랜 구조 표준

각 플랜 파일은 다음 섹션을 포함한다:

1. **Context** — 왜 하는가, 현 상태, 목표.
2. **Architecture/Principles** — 접근 방식, 제약.
3. **구현 단계** — 구체적 파일/diff 범위, 순서.
4. **Verification** — 단위 테스트 + 수동 검증 절차.
5. **결정 로그** — 완료된 결정 + 차후 결정.
6. **롤백 계획** (실행성 플랜 한정).

## 워크플로

### 플랜 작성 → 실행 → 완료

1. **Plan 모드로 작성** — Claude Code `/plan` 또는 plan 모드를 사용해 이 디렉터리에 새 파일 생성.
2. **승인 후 실행** — 승인된 플랜에 따라 구현. 실제 코드 변경은 일반 커밋/PR로 진행.
3. **완료 시 정리**:
   - PR 머지 후 해당 플랜 파일을 **이 디렉터리에서 제거**.
   - [`docs/planning-log.md`](../docs/planning-log.md)에 요약 엔트리 추가 (제목, 완료일, 관련 PR/커밋 링크, 짧은 요약).
   - 세부 내용은 GitHub PR 본문 + 커밋 이력이 진실의 원천. 로그는 인덱스 역할만.

### 상위 ↔ 하위 플랜 관계

- **로드맵 성격**(`00-ai-platform-roadmap.md`) — 여러 Phase에 걸친 방향. 각 Phase 완료 시 해당 Phase 섹션의 결정사항은 로드맵 "결정 완료" 표를 업데이트하되, 로드맵 자체는 모든 Phase 완료 전까지 이 디렉터리에 남는다.
- **실행 성격**(Phase 단위) — 한 Phase의 구체적 작업 계획. 해당 Phase 머지 완료 시 제거 + 로그 기록.

## 현재 활성 플랜

| 파일 | 유형 | 상태 |
|---|---|---|
| [`00-ai-platform-roadmap.md`](./00-ai-platform-roadmap.md) | 로드맵 | Phase 6 후속 우선순위를 Meeting Work Intelligence MVP로 전환 |
| [`02-evidence-first-agent-runtime.md`](./02-evidence-first-agent-runtime.md) | 실행 설계 | 장기 hybrid runtime 설계. 단기 실행은 local-first structured extraction + optional external review |
| [`03-phase6-evidence-runtime-implementation.md`](./03-phase6-evidence-runtime-implementation.md) | 실행 기록/보류 계획 | AI manager/runtime spike 완료, Meeting Work Intelligence로 후속 전환 |
| [`04-whiteboard-app-implementation.md`](./04-whiteboard-app-implementation.md) | 실행 계획 | Excalidraw 기반 Whiteboard 앱 (Docs 동등 first-class entity) 구현 계획 |
| [`05-meeting-work-intelligence.md`](./05-meeting-work-intelligence.md) | 실행 계획 | 회의록/채팅 원문을 업무 항목으로 전환하는 local-first vertical slice |

완료된 플랜은 [`docs/planning-log.md`](../docs/planning-log.md)에서 확인.

참고 연구 문서는 [`docs/planning/01-agentic-harness-engineering-report.md`](../docs/planning/01-agentic-harness-engineering-report.md)에 보관한다.
