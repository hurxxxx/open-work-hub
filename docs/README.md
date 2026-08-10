# AI-DO 문서 색인

## 작업별 진입점

모든 문서를 순서대로 읽지 않는다. 현재 코드와 테스트를 먼저 보고 작업에
직접 필요한 정본 하나에서 시작한다.

| 작업                             | 시작 문서                                                                                                                    |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 현재 제품/전략 상태 확인         | [현재 구현 상태](current/project-status.md), 필요할 때만 [AI HUB 전략 색인](current/ai-hub-transition-index.md)              |
| 개발 구조와 검증 깊이 결정       | [LLM 친화 개발 기준](agents/llm-friendly-development.md), [바이브 코딩 하네스](agents/vibe-coding-harness.md) 중 필요한 문서 |
| 앱 등록·권한·bootstrap 변경      | [앱 플랫폼 계약](domains/app-platform/README.md)                                                                             |
| 외부 REST API·플랫폼 API 키 연계 | [외부 REST 연계 계약](domains/api-integrations/README.md)                                                                    |
| mcloudoc 문서중앙화 연계         | [mcloudoc 연계 경계](domains/mcloudoc/README.md)                                                                             |
| 특정 도메인 또는 앱 변경         | 해당 `domains/<domain>/README.md` 또는 `apps/<app-id>/README.md`                                                             |
| UI 공용 계약 변경                | [UI 공용 컴포넌트](agents/ui-components.md)                                                                                  |
| 추상화 경계 결정                 | [조합형 추상화](agents/composable-abstractions.md)                                                                           |
| 환경 설정·서버 재시작            | [반복 참고 문서](reference/README.md) 또는 해당 운영 skill                                                                   |
| 인수·완료 보고 확인              | [최종 산출물 색인](final/README.md)                                                                                          |
| 문서 위치·수명 결정              | 이 문서와 [에이전트 문서 소유권](agents/domain.md)                                                                           |

`final/`은 완료 보고용이며 current truth가 아니다. `archive/`, 원시 QA
산출물, Git 이력의 과거 계획은 사용자가 요청한 경우에만 읽는다.

## 앱별 문서

- [Diagrams](apps/diagrams/README.md)
- [Legacy Issues](apps/legacy-issues/README.md)
- [Management Tasks](apps/management-tasks/README.md)
- [PMS](apps/pms/README.md)
- [PLM](apps/plm/README.md)

## 디렉터리 기준

| 경로         | 용도                                                                 |
| ------------ | -------------------------------------------------------------------- |
| `current/`   | 전사/제품/운영 current truth와 색인. 상세 계약은 링크만 둔다.        |
| `final/`     | 외부 공유나 완료 보고 목적의 최종 산출물. 현재 정본으로 읽지 않는다. |
| `domains/`   | 여러 앱/런타임을 가로지르는 도메인별 계약.                           |
| `apps/`      | 특정 앱이나 앱바 항목에 한정된 계약.                                 |
| `product/`   | 제품 UI와 데이터 기준처럼 구현에 직접 필요한 기준 자료.              |
| `reference/` | 개발 환경, 운영 절차, 반복 참고 문서.                                |
| `working/`   | 진행 중 임시 작업. 완료 후 소유 문서로 축약하거나 제거한다.          |
| `agents/`    | 에이전트의 개발·검증·문서 운영 기준.                                 |
| `archive/`   | 비정본 참고 자료. 명시적으로 요청된 경우에만 읽는다.                 |

## 유지 규칙

- 한 계약은 한 문서가 소유하고 다른 문서는 링크만 둔다.
- `current/`에는 전사 의사결정과 색인을, 상세 내용은 소유
  `domains/`, `apps/`, `product/`, `reference/` 문서에 둔다.
- 결론이 난 실험은 결론과 재현 경로만 소유 문서에 남긴다.
- 장문 계획, 임시 검증 메모, 대용량 스크린샷, 원시 JSON, 과거 테스트
  결과는 current truth로 유지하지 않는다.
- 루트 `learning/**/*.md`는 학습 앱 콘텐츠이며 프로젝트 지침이나 기본
  에이전트 컨텍스트가 아니다.
- ADR은 저장소 루트 `adr/`에 둔다. `CONTEXT.md`, `CONTEXT-MAP.md`,
  `docs/adr/`는 만들지 않는다.

## 서버 checkout

상세 계약은 루트 [README](../README.md)와
[운영 배포 경로](domains/release/production-deployment-layout.md)가 소유한다.

| 대상 | 경로                   | 브랜치 |
| ---- | ---------------------- | ------ |
| 운영 | `/projects/ai-do/prod` | `main` |
| 개발 | `/projects/ai-do/dev`  | `dev`  |
