# 현재 구현 상태

## 한 줄 요약

Open ALM는 독립적인 AI HUB 플랫폼이다. PMS, Planner, Docs, Files 등은 현재 코드 기준으로
유지하되 Meeting과 Recording은 미완성·미운영이며, Mail도 미완성·미운영이고 추가 개발 여부가
아직 정해지지 않았다. 범용 Knowledge 제품 기능과 domain runtime/model은 퇴역했다.
문서중앙화 연계는 Files를 정본으로 하는 source-specific mcloudoc 수용 경계만 구현했으며,
대상 adapter와 운영 연계는 아직 활성화하지 않았다. 앞으로의 주력은 확정된 내부 원본 기반
검색/RAG, AI 챗봇, 현업 소형 업무 앱 제작 플랫폼, 그리고 코어와 분리 가능한 app/feature
module 구조이다.

전략 정본은 `docs/current/ai-hub-transition-index.md`를 먼저 본다.

## 운영/개발 체크아웃

운영 서버에서는 `/projects/open-alm/prod`가 `main` 브랜치 운영 checkout이고,
`/projects/open-alm/dev`가 `dev` 브랜치 개발 checkout이다. 개발 변경은 `dev`에서
검증한 뒤 GitLab MR로 `main`에 병합한다. 구 경로 호환 symlink는 두지 않는다.

## 구현 상태 표

| 영역                   | 현재 상태                                               | 다음 판단                                                                                                                                                                                                |
| ---------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workspace/Auth/RBAC    | 구현됨                                                  | AI HUB 접근 제어의 기반으로 유지                                                                                                                                                                         |
| 앱 셸                  | 구현됨                                                  | app-owned catalog/manifest를 명시적 composition root에서 조합하고 registry projection을 bootstrap·gate에서 사용                                                                                          |
| 앱 런처/App Bar        | 구현됨                                                  | 고정 section 없이 DB 기반 관리자 category와 사용자 pin을 사용하며 앱 등록 계약은 `docs/domains/app-platform/README.md`를 따름                                                                            |
| Mail                   | 미완성·미운영, 개발 지속 미정                           | 운영 기능으로 안내하지 않는다. 재개 여부를 제품 책임자가 결정하기 전 provider 연결·동기화 활성화를 보류하고 RAG 운영 색인 대상으로도 사용하지 않음                                                       |
| PMS                    | 구현됨                                                  | 자체 업무 추적 화면으로 유지. 오래된 확장 PRD만 삭제/축약                                                                                                                                                |
| Planner/Calendar       | 구현됨                                                  | 일정/업무 보조 흐름으로 유지                                                                                                                                                                             |
| Meeting                | 미완성·미운영                                           | route·API·worker 코드가 있어도 운영 기능으로 간주하지 않으며 완성·인수 기준을 별도 결정                                                                                                                  |
| Recording              | 미완성·미운영                                           | 전사/요약/문서 연결 코드는 운영 사용 대상이 아니며 완성·인수 기준을 별도 결정                                                                                                                            |
| Docs/Collab            | 구현됨                                                  | BlockNote/Yjs 기반 문서 협업과 native Docs RAG 유지                                                                                                                                                      |
| Files                  | 구현됨, 운영 empty generation gate 활성                 | production은 검증된 empty pair 기반 가용성 bootstrap만 완료했으며 실데이터 품질은 `deferred_until_nonempty`이다. source-managed explicit grants는 아직 비활성인 mcloudoc 수용 capability다.              |
| mcloudoc               | Open ALM 수용 기반 구현, 외부 adapter 미구현               | 대상중립 source/document/run, Files binding, typed metadata·ACL, 증분/snapshot 계약은 구현. 대상 transport·인증·필드/identity 매핑과 공동 E2E 확정 전 운영 source·worker는 만들거나 켜지 않음            |
| Knowledge              | 제품 기능·domain runtime/model 제거 완료(Release N)     | app/API/domain model과 PMS·Meeting 이중쓰기는 제거했다. Release N/N+1은 비우회 임시 cutover gate와 legacy 4개 table/Alembic-only metadata를 보존하며 registry는 N+1, 물리 table·gate는 N+2에서 제거한다. |
| Whiteboard             | 구현됨                                                  | 필요 사례가 명확할 때 RAG/export 보조 기능 검토                                                                                                                                                          |
| Open ALM Desktop          | 별도 repo로 분리                                        | 앱 소스와 패키징은 `/projects/open-alm/open-alm-desktop`, 포털은 update feed/session link 유지                                                                                                                 |
| Keyword Search         | 구현됨, 주력                                            | OpenSearch 기반 workspace 검색. Retrieval layer와 함께 통합 검색 진입점으로 유지                                                                                                                         |
| RAG runtime            | 로컬 provider 반영, 주력                                | Snowflake-ko/Qdrant/Docling 기반. Docs native가 active workspace 대상이고 QNA는 company 대상                                                                                                             |
| AI Gateway             | 정책/audit 기반 구현, adoption 부분 완료                | Core gateway와 provider SDK/HTTP envelope가 동작한다. 비용 계산·quota/throttling은 미구현이며 현재 계약은 `docs/domains/ai/gateway.md`를 따른다.                                                         |
| OCR/문서 추출          | 메인 provider 적용, 주력                                | 내부 문서 ingestion 품질 검증으로 전환                                                                                                                                                                   |
| PLM                    | Oracle 원천 조회 UI/API 구현, template search는 fixture | workspace admin API로 객체 목록·행 페이지 조회·SELECT 실행을 제공한다. `/search/plm`은 고정 preview이며 PLM RAG adapter는 등록하지 않는다.                                                               |
| 문서 작성 지원         | 앱별 구현됨                                             | Writing Assistant, PPT Assistant, Spec Compare, 특허·과거차 앱이 용도별 생성·검토·다운로드를 소유. mcloudoc/PLM 실데이터 근거 조립 E2E는 외부 계약 확정 후 별도 검수                                     |
| 현업 앱 제작           | 주력                                                    | 템플릿, 권한/감사, 품질 하네스로 확장                                                                                                                                                                    |
| 확장 앱/feature module | 주력                                                    | 코어 앱과 경계 계약을 분리하고 manifest/workspace/server 설정으로 노출 제어                                                                                                                              |

## 검증 기준

- 문서 구조 변경 후 `rg --files docs adr apps interfaces packages`로 current/domain/app/archive 분리가 유지되는지 확인한다.
- 과거 계획은 저장소 정본 문서로 유지하지 않고, 필요 시 Git 이력에서만 복원한다.
- 기술검토, 임시 검증 메모, 초기 계획 보조 산출물은 저장소 정본 문서로 유지하지 않는다.
- 실험 결과는 raw JSON을 현재 문서 트리에 두지 않고, current 문서에는 결론과 재현 경로만 남긴다.
- 별도 연구소 standalone 앱이나 4210 포트 운영 계획은 현재 방향이 아니다. 같은 코드베이스에서
  독립 app/feature module 을 manifest contract 로 조립하고, 데이터베이스와 설정으로 계열사별
  경계를 만든다.
