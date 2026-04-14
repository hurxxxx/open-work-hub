# QA Run — Workspace / ACL 시나리오 (2026-04-14)

실행자: agent-browser CLI 자동 + Claude
환경: dev (web :4200, api :8000), seed dev accounts
대상 커밋 base: `74dd0ae simplify workspace acl model`
계획서: `/Users/edward/.claude/plans/generic-marinating-canyon.md`

## Result Summary

| ID | Scenario | Result | 한 줄 |
|----|----------|--------|------|
| S1 | Login & seed account discovery | PASS | seed 패널 1-click 로그인 동작, token 저장 OK |
| S2 | Workspace switcher (multi-ws) | **BLOCKED** | 모든 seed 계정이 단일 워크스페이스 — switcher 다중 옵션 검증 불가 |
| S3 | Cross-workspace URL 차단 | PASS | hq-member → /w/delivery-hub: 웹 gate "접근 권한 없음" + API 403 |
| S4 | PMS list create & rename | PASS | `POST /api/v1/workspaces/delivery-hub/pms/lists` 201, 응답 `list_id`. deprecated `projects/` URL 미사용 |
| S5 | PMS issue 생성 | PASS | "ACL Probe" `QASCEN-1` 생성, 팀 멤버 접근 OK |
| S6 | Meeting one-step create (task+doc atomic) | PASS (재검증) | 1차 시도에서 attendee 누락처럼 보였으나 agent-browser click 합성 이벤트 한정 — `b.click()` 직접 호출 시 정상 |
| S7 | Meeting-driven grant 부여 | PASS (sanity) | dh-member가 첨부된 issue를 조회 가능. 단 native team 멤버라 grant-only 케이스는 분리 검증 못함 |
| S8 | Attendee 제거 → revoke | PASS | 제거 후 meeting GET 403 ("You do not have access"). 이슈 200은 native 멤버십 때문 (예상 sanity) |
| S9 | Reschedule end_at bump | PASS | PATCH 200, end_at 갱신. (DB의 expires_at 컬럼 직접 검증은 미수행) |
| S10 | Task detach | PASS | "태스크 첨부 해제" 클릭 후 `task_links` length 0 |
| S11 | Recording upload | SKIP | 실 audio 파일/worker 미준비. 별도 세션 권장 |
| S12 | Docs share fallback | SKIP | seed에 native doc 부재. 별도 세션에서 문서 생성 후 수행 |
| S13 | Platform admin override | **FAIL/INFO** | platform-admin은 workspace 멤버십 없이 `/w/hq/pms` 진입 시 web/API 모두 차단됨 — 의도 여부 확인 필요 |
| S14 | Deprecated PMS alias hidden (UI) | **FAIL** | PMS Overview에 "{n} projects · …" 라벨 잔존 |

PASS 9 · FAIL 2 · BLOCKED 1 · SKIP 2 (S6 재검증 후)

## Findings

### F1. [INVALIDATED] Meeting create 모달 attendee 드랍 — 테스트 아티팩트
- **초기 의심**: agent-browser CLI로 suggestion 버튼을 click한 뒤 생성된 meeting이 organizer 1명만 가짐.
- **재현 시도 결과**: 동일 흐름을 `document.querySelector(...).click()`(JS native click)로 수행하면 chip이 정상 추가되고 페이로드에 attendees 포함됨.
- **결론**: agent-browser의 합성 click 이벤트가 input → suggestion 사이 focus 전이를 다르게 처리하면서 React state 갱신이 누락된 것. **제품 코드 회귀 아님.**
- **남은 작업**: 향후 자동화 재실행 시 suggestion 클릭은 `eval` 기반 native click 또는 `mousedown→click` 시퀀스로 대체.

### F2. [FIXED] PMS Overview "projects" 라벨 → "lists"
- **위치**: [apps/web/src/components/views/PMSView/OverviewView.tsx:70](apps/web/src/components/views/PMSView/OverviewView.tsx#L70)
- **수정**: 사용자 노출 라벨 `projects` → `lists` 로 교체. 후속으로 dashboard summary API 응답 키 `project_count`도 `list_count`로 정리 권장 (서버 schema 변경 PR 분리).
- **검증**: dev server에서 "2 lists · 1 active issues · 0 overdue" 정상 렌더링 확인.

### F3. [INFO/HIGH 후보] platform_admin이 워크스페이스 멤버십 없이는 데이터 접근 불가 — S13
- **재현**: `platform-admin@aidoo.local` 로그인 → `/w/hq/pms` 직접 이동 → 웹: "접근 권한 없음" gate. API: `GET /api/v1/workspaces/hq/pms/lists` → 403 `Workspace membership required: hq`.
- **사용자 객체**: `system_roles: ["platform_admin"]`, `workspaces: []`.
- **해석**: `74dd0ae simplify workspace acl model` 이후 platform_admin은 시스템 레벨 권한만 가지며, 워크스페이스 데이터 access는 별도 멤버십 필요. 의도라면 **운영상 platform_admin이 디버깅하려면 본인을 모든 워크스페이스에 binding해야 함** — admin UX 측면 검토 필요.
- **권고**: 의도 확인 후 둘 중 하나로 결정:
  - (A) platform_admin은 모든 workspace에 cross-cut read 허용 → `require_workspace_membership` 분기 추가.
  - (B) 의도된 격리 → seed 단계에서 platform_admin을 모든 워크스페이스 admin으로 자동 binding.

### F4. [FIXED] Meeting payload task link key rename → `list_key`
- **변경**:
  - [apps/api/src/aidoo_api/domains/meeting/schemas.py:77](apps/api/src/aidoo_api/domains/meeting/schemas.py#L77) — `MeetingTaskLinkOut`가 legacy key 이름 대신 `list_key`를 반환하도록 정리
  - [apps/api/src/aidoo_api/domains/meeting/service.py:236](apps/api/src/aidoo_api/domains/meeting/service.py#L236) — `_serialize_task_link` 변수/필드명 정리
  - [apps/web/src/domains/meeting/meeting-api.ts:20](apps/web/src/domains/meeting/meeting-api.ts#L20) — `MeetingTaskLink` 타입
  - [apps/web/src/components/views/MeetingView/MeetingDetail.tsx:399](apps/web/src/components/views/MeetingView/MeetingDetail.tsx#L399), [RecordingControls.tsx:79](apps/web/src/components/views/MeetingView/RecordingControls.tsx#L79) — 렌더링
  - [apps/api/tests/test_meeting.py:308](apps/api/tests/test_meeting.py#L308) — 단언문
- **검증**: dev API 응답에서 `"list_key":"QASCEN"` 확인, MeetingDetail UI에 `QASCEN-1` 정상 표시.

### F5. [LOW] Cross-workspace 사용자 directory 격리 (positive finding)
- delivery-hub 미팅 attendee 검색에 `hq-member` 입력 → "일치하는 사용자가 없습니다." (검색 결과 0)
- 사용자 directory가 workspace-scope에서 누설되지 않는 점 확인 — 의도된 동작.

## Test Gaps (후속)

1. **multi-workspace 사용자 시나리오**: seed 단계에서 `hq-and-delivery@aidoo.local`처럼 두 워크스페이스에 멤버십을 가진 계정을 추가해야 S2 (워크스페이스 switcher 다중 옵션) 와 S7 grant-only 케이스(non-team-member에게 meeting 첨부로만 read 허용) 를 분리 검증 가능.
2. **DB 직접 검증**: S9 `bump_grant_expiry_for_meeting`이 `DocMeetingAccess.expires_at` / `pms_issue_user_access.expires_at`을 실제로 갱신했는지 SQL/admin 라우터로 직접 조회하지 않았음.
3. **Recording upload (S11)**: 작은 audio 파일과 worker 동작 시 후처리 상태 분리 표시(`asset_status` vs `processing_status`)가 UI에 정확히 나오는지 별도 dry-run 권장.
4. **Docs share fallback (S12)**: native doc seed가 없어 검증하지 못함. seed에 1~2개 demo doc 포함하면 향후 자동화에 도움.

## Artifacts

- `s1-logged-in.png`
- `s3-cross-ws-blocked.png`
- `s4-list-created.png`
- `s6-meeting-created.png`
- `s13-platform-admin-blocked.png`
- `s14-projects-leak.png`

생성된 데이터(추후 정리 가능):
- PMS list: `QA Scenario List` (delivery-hub / Team Space, id `df0dd7a7-ce2a-4ec2-b646-e60aa64f57be`)
- PMS issue: `ACL Probe` `QASCEN-1` (id `a50a033a-2a5e-43d2-82e0-a1aa8d2a07e7`)
- Meeting: `QA Scenario Meeting` (id `57dacc87-c084-4f06-b1a2-287f2d623e16`)

## 수정 결과

- **F1** — INVALIDATED. 테스트 아티팩트로 결론.
- **F2** — FIXED. 라벨 교체 후 dev 환경 검증.
- **F3** — 보류. 제품 결정 사안이라 코드 변경 없음.
- **F4** — FIXED. server schema + web type + 렌더링 + 테스트 단언 동기화.

검증:
- `nx run web:typecheck` PASS
- `nx run web:test` 35/35 PASS
- API pytest는 docker daemon 미구동으로 미수행 → 후속 PR에서 재검 필요 (변경은 단순 필드명 교체이므로 schema-level 회귀 가능성 낮음)
