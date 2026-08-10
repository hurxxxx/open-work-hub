# AI Write Policy

상태: 현재 정책과 구현 경계

Open ALM의 기본 AI 동작은 내부 원본을 읽고, 검색하고, 요약하는 보조 기능이다. 원본 시스템을 실제로 변경하는 write 동작은 기능 플래그, 사용자 승인, 원본 ACL, 감사 로그가 모두 충족될 때만 실행한다.

## 기본 원칙

- write tool은 기본적으로 노출하지 않는다.
- 첫 실행은 원본을 변경하지 않고 변경 대상과 payload를 보여 주는 approval preview를 만든다.
- 실제 write는 요청한 사용자 principal의 승인 전에는 실행하지 않는다. agent/service principal 단독 승인은 허용하지 않는다.
- 승인 후 실행할 때도 domain service의 원본 ACL과 비즈니스 규칙을 다시 검사한다.
- 승인 row, tool execution audit, 생성·변경된 resource ID를 연결한다.
- 외부 provider로 보내는 입력은 [AI Gateway 계약](./gateway.md)의 security enforcement와 transfer policy를 따른다.

## 현재 원본별 경계

| 원본 | 기본 허용 AI 동작 | 현재 AI write tool |
| --- | --- | --- |
| Mail | 검색, 요약, 번역, 업무 추출 | 미등록 |
| Meeting | 회의 조회, 요약, action item/decision/follow-up 추출 | 기본 OFF; 플래그 ON 시 승인 후 회의 생성 |
| PMS | 업무 조회, 요약, 업무 후보 추출 | 기본 OFF; 플래그 ON 시 승인 후 task 생성·수정·댓글·삭제 |
| Files | 파일 조회, 요약 후보 | 미등록 |
| Docs | 문서 검색, 요약, 초안 작성 | 미등록 |
| Planner | 일정 조회, 요약, 일정 후보 추출 | 기본 OFF; 플래그 ON 시 승인 후 일정 생성·수정·삭제 |
| PLM | 읽기 전용 조회 | 미등록 |

## 현재 구현 계약

- `OPEN_ALM_AI_WRITE_TOOLS_ENABLED`의 기본값은 `false`다. 비활성 상태에서는 write tool을 registry와 AI surface에 노출하지 않는다.
- 활성화 시 PMS의 task 생성·수정·댓글·삭제, Meeting의 회의 생성, Planner의 일정 생성·수정·삭제 tool을 등록한다.
- write tool은 `mode="write"`, `approval_required=True`, 유효한 `preview_builder_id`를 선언한다. Registry는 이 계약에서 descriptor의 `approval_policy="required"`를 파생한다.
- 첫 실행은 approval preview와 `approval_required` 이벤트를 만들고 실행을 중단한다.
- 승인·거절은 요청한 사용자 principal만 수행할 수 있다. 승인 후 resume은 실제 domain service와 권한 검사를 다시 거친다.
- 실행 결과와 tool audit에는 approval ID와 resource ID를 연결한다.

새 write capability를 추가할 때는 같은 flag/discoverability, preview, approval, ACL, audit 계약을 만족하고 도메인별 권한·실패·중복 실행 테스트를 추가해야 한다.
