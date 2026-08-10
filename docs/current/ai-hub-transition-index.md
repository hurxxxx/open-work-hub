# AI HUB 전략 색인

## 결론

Open ALM는 자체 워크스페이스, 권한, 문서, PMS, 검색/RAG, AI 챗봇, 여러 후속 앱과
현업 소형 업무 앱 제작을 묶는 AI HUB 플랫폼이다. 현재 실행 계획은 별도 연구소
standalone 앱이 아니라, 동일 코드베이스를 계열사별 데이터베이스와 설정으로 분리해
제공하는 단일 플랫폼 구조를 우선한다.

각 계열사 또는 고객사 배포에서 회사가 최상위 tenant이며, 부서·팀의 workspace는 그 아래의
협업·접근·데이터 범위다. Workspace slug는 route locator이지 tenant 또는 권한 증거가 아니다.
상세 계약은 [ADR 0007](../../adr/0007-company-tenant-workspace-scope.md)을 따른다.

계열사 또는 고객사별 예외 기능은 코어 앱에 섞지 않는다. 기능 자체는 독립 app module 또는
feature module 로 등록하고, 노출 여부는 workspace/server 설정과 entitlement로 제어한다.
현재 대표 사례는 `legacy-issues` 확장 앱이며, OPEN_ALM 환경에서만 노출되는 운영 정책을 갖는다.
AI 앱 아래 붙는 Q&A, 웹 검색 같은 도구도 구현은 독립 feature module 로 유지하고, AI 앱은
route/launcher 조립만 맡는다.

앱 identity는 app-owned backend catalog와 frontend manifest가 선언하고 플랫폼 composition
root는 등록 객체만 명시적으로 조합한다. launcher category의 제목·순서·앱 배치는 DB 기반
관리자 설정이며, 고정 `ai`/`collaboration`/`business` section이나 별도 앱 ID allowlist를
플랫폼 코드에 두지 않는다. 상세 계약은
[앱 플랫폼 등록 계약](../domains/app-platform/README.md)을 정본으로 본다.

## 시스템 소유권

| 영역         | 현재 원장                          | Open ALM 역할                                                     |
| ------------ | ---------------------------------- | -------------------------------------------------------------- |
| 사용자/권한  | Open ALM tenant Auth + Workspace/RBAC | 회사 사용자·전역 관리자, workspace membership/ACL, 감사의 기준 |
| 메일         | 미완성 Open ALM Mail 코드             | 현재 미운영이며 개발 지속 여부 미정. RAG 운영 색인 대상도 아님 |
| 태스크/PMS   | Open ALM PMS                          | 보드/리스트/업무 추적과 AI 보조                                |
| 일정/Planner | Open ALM Planner/Calendar             | 일정 조회, 검색, 업무 연결                                     |
| 회의/녹음    | 미완성 Open ALM Meeting/Recording     | 현재 미운영. 향후 완성·인수 승인 전 업무 기능으로 안내하지 않음 |
| 문서/파일    | Open ALM Docs/Files                   | Docs native RAG와 Files partitioned retrieval 운영 활성 |
| 내부 앱 제작 | Open ALM                              | 현업 소형 업무 앱 템플릿, 가드레일, 배포면                     |
| AI 검색/챗봇 | Open ALM                              | 내부 원본을 근거 기반으로 검색하고 답변                        |

## 실행 상태

| 구분                   | 상태   | 다음 판단                                                                                                  |
| ---------------------- | ------ | ---------------------------------------------------------------------------------------------------------- |
| PMS                    | 구현됨 | 현재 코드 기준으로 유지. 과거 장문 확장 계획만 삭제/축약                                                   |
| Planner/Calendar       | 구현됨 | 자체 일정/업무 흐름의 현재 구현으로 유지                                                                   |
| Meeting/Recording      | 미완성·미운영 | 코드와 계약은 운영 승인으로 보지 않는다. 향후 완성 범위를 결정하며 RAG 운영 색인 대상도 아님                       |
| Mail                   | 미완성·미운영, 개발 지속 미정 | 재개·중단 결정 전 provider 연결과 업무 사용을 보류하며 RAG 운영 색인 대상도 아님                                |
| Docs/Files             | 구현됨 | Docs RAG와 Files partition-aware retrieval 운영 활성. Files full checker는 generation cutover에서만 수동 실행 |
| RAG/Search             | 주력   | Retrieval layer 기준으로 통합. Docs native는 active workspace RAG 대상, QNA는 company RAG 대상, PLM은 제외 |
| 현업 앱 제작           | 주력   | 템플릿, 권한/감사, 품질 하네스로 확장                                                                      |
| 확장 앱/feature module | 주력   | 코어 의존성을 역전하지 않고 shell/API composition root와 manifest contract에서 조립                        |

## 읽는 순서

1. `docs/current/ai-hub-transition-index.md` — 현재 전략 정본.
2. `docs/current/project-status.md` — 현재 구현물 중 유지/주력/운영 제외 영역.
3. `docs/agents/llm-friendly-development.md` — 개발 구조/추상화/진입점 판단 정본.
4. `docs/agents/vibe-coding-harness.md` — 바이브 코딩 작업의 계약과 검증 하네스 기준.
5. `docs/domains/app-platform/README.md` — 앱 identity/등록/조합과 launcher category 계약 정본.
6. `docs/domains/ai/gateway.md` — AI Gateway 계약, LLM 호출/감사/사용량/비용/스로틀링 로드맵 정본.
7. `docs/domains/retrieval/README.md` — 통합 retrieval service layer 기준.
8. `docs/domains/rag/README.md` — RAG source scope, parser/OCR, vector/rerank/query lifecycle 기준.
9. `docs/domains/ai/write-policy.md` — AI write/approval preview 정책 기준.

## 문서 운영 원칙

- 새 작업은 현재 코드와 실제 운영 후보를 기준으로 작성한다.
- 오래된 장문 계획, 과거 QA 결과, raw benchmark는 저장소 정본 문서로 유지하지 않는다.
- 과거 계획 원문이 필요하면 사용자가 요청한 경우에만 Git 이력에서 복원한다.
- 기술검토, 임시 검증 메모, 초기 계획 보조 산출물은 저장소 정본 문서로 유지하지 않는다.
- Open ALM가 직접 소유할 기능은 검색 품질, AI 챗봇, 자동화 보조, 현업 앱 제작 경험을
  중심으로 정리한다. LLM 호출 정책과 사용량/비용/스로틀링 계획은
  `docs/domains/ai/gateway.md`를 정본으로 본다. RAG 원본 범위는 확정 원본과 후보 원본을
  분리해 관리한다.
- 계열사별 예외 기능은 저장소 분리보다 app/feature module 경계, manifest contract, 설정 노출
  제어, 데이터베이스 분리로 먼저 해결한다. 별도 포트나 별도 앱으로 띄우는 연구소 standalone
  계획은 정본이 아니다.
