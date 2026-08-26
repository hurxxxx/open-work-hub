# Open Work Hub 문서 색인

현재 변경과 직접 관련된 문서에서 시작합니다. 제품 동작의 최종 근거는 코드와 테스트이며,
각 도메인 문서는 장기적으로 유지할 계약과 운영 기준만 설명합니다.

## 주요 문서

| 영역                      | 시작 문서                                                              |
| ------------------------- | ---------------------------------------------------------------------- |
| 에이전트 개발·검증·MR 기준 | [에이전트 문서 라우팅](agents/domain.md)                               |
| 앱 등록·권한·bootstrap    | [앱 플랫폼 계약](domains/app-platform/README.md)                       |
| AI 모델과 실행 게이트웨이 | [AI Gateway](domains/ai/gateway.md)                                    |
| Retrieval과 RAG           | [Retrieval](domains/retrieval/README.md), [RAG](domains/rag/README.md) |
| 배포와 런타임             | [Release](domains/release/README.md)                                   |

## 앱별 문서

- [bento/slides](apps/bento/README.md)
- [Diagrams](apps/diagrams/README.md)
- [PMS](apps/pms/README.md)

## 디렉터리

| 경로       | 용도                                      |
| ---------- | ----------------------------------------- |
| `domains/` | 여러 앱과 런타임을 가로지르는 도메인 계약 |
| `apps/`    | 특정 범용 앱에 한정된 계약                |
| `agents/`  | AI 개발 도구의 구조·검증·작업 지침        |
| `product/` | 제품 UI와 데이터 기준                     |

GitLab `origin`이 이 사이트의 canonical 저장소이며 GitHub `upstream`은 원본 코드 수신용입니다.
Issue와 MR 운영 지침은 [Issue Tracker](agents/issue-tracker.md)와
[구현 검증 하네스](agents/vibe-coding-harness.md)를 따릅니다.

ADR은 저장소 루트 [`adr/`](../adr)에 둡니다. 임시 검증 결과, 원시 로그, 대용량 스크린샷과
완료 보고서는 문서 정본으로 보관하지 않습니다.
