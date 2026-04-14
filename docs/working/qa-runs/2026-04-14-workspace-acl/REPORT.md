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

---

## QA Run — Meeting Workspace PR2 E2E (2026-04-14)

실행자: `agent-browser` 실제 상호작용 + Codex
세션:
- organizer: `doowon-meeting-e2e`
- attendee: `doowon-meeting-attendee-e2e`
환경:
- web `127.0.0.1:4200`
- api `127.0.0.1:8000`
- 테스트 도중 `apps/api`에서 `uv run alembic upgrade head` 적용

### Result Summary

| ID | Scenario | Result | 메모 |
|----|----------|--------|------|
| M1 | Meeting create modal submit | PASS after fix | 최초엔 API 500. 원인은 DB 미마이그레이션(`meetings.notes_doc_id`, `notes_page_id` 없음). migration 적용 후 동일 UI submit으로 상세 route 진입 성공 |
| M2 | Dedicated meeting workspace route | PASS | 생성 직후 `/w/delivery-hub/meeting/9ae4de6a-9790-4d1d-a310-d62fbe86f3dd` 진입 |
| M3 | Notes editor bootstrap | PASS after fix | 최초엔 `회의 메모 페이지를 불러올 수 없습니다.`. raw `notes_page_id` vs `native_doc_page__...` mismatch 수정 후 정상 로드 |
| M4 | Legacy `?id=` normalization | PASS | `/w/delivery-hub/meeting?id=<id>` → `/w/delivery-hub/meeting/<id>` 즉시 redirect |
| M5 | Notes autosave + reload | PASS | 제목 `Meeting Workspace Notes 105008`, 본문 `Meeting notes body 105008` 저장 후 reload 유지 |
| M6 | `Open in Docs` with wrong last-workspace | PASS | `localStorage.aidoo:last-workspace-slug = hq`로 바꾼 뒤에도 `/w/delivery-hub/docs/07181f9c-e4cb-4e3e-9120-f843e441f77d` 진입 |
| M7 | Attached PMS/Docs deep-link | PASS | task → `/w/delivery-hub/pms?issue=75d040c1-7d6a-4d13-9571-d9b43dea20cd`, doc → `/w/delivery-hub/docs/d804d74d-1528-440b-8c71-07ec41559aa5` |
| M8 | File attachment round-trip | PASS | 다운로드 버튼으로 `/tmp/meeting-e2e-download.txt` 저장, 내용 `meeting e2e attachment` 확인 |
| M9 | Recording manual upload | PASS with degraded processing | `/tmp/doowon-meeting-e2e.wav` 업로드 후 recording row 생성. 백그라운드 큐 부재로 `failed` 상태 + `다시 시도` 노출 |
| M10 | Attendee meeting workspace access | PASS | `delivery-hub-member` 세션에서 same meeting route 진입 및 notes 편집 가능 |
| M11 | Attendee notes edit propagation | PASS | attendee가 `Attendee edit 105008` 입력 후 organizer reload 시 동일 내용 반영 |
| M12 | Attendee removal revoke | PASS | organizer가 attendee 제거 후 attendee 세션 reload 시 `You do not have access to this meeting.` |
| M13 | Notes doc revoke after attendee removal | PASS | attendee가 `/w/delivery-hub/docs/07181f9c-e4cb-4e3e-9120-f843e441f77d` 직접 진입 시 `Document not found` |
| M14 | Wrong workspace slug block | PASS | organizer가 `/w/hq/meeting/<id>` 직접 진입 시 shell gate `접근 권한 없음` |

### Findings

#### F6. [FIXED] Dev DB migration 누락으로 meeting create 전면 500
- **증상**: Meeting create modal submit과 direct API create 모두 `500 Internal Server Error`
- **원인**: dev DB의 `meetings` 테이블에 `notes_doc_id`, `notes_page_id` 컬럼이 아직 없음
- **재현 traceback**:
  - `psycopg.errors.UndefinedColumn: column "notes_doc_id" of relation "meetings" does not exist`
- **조치**: `apps/api`에서 `uv run alembic upgrade head` 실행
- **결과**: 동일 UI submit으로 meeting 생성 성공

#### F7. [FIXED] Meeting workspace가 notes page를 못 찾음
- **증상**: 생성 직후 상세 route에서 `회의 메모 페이지를 불러올 수 없습니다.`
- **원인**:
  - meeting API는 raw `notes_page_id = 24a1...` 저장
  - docs pages API는 `id = native_doc_page__24a1...`, `source_page_id = 24a1...` 반환
  - 프런트가 `item.id === notes_page_id`만 비교해서 매칭 실패
- **수정**: [MeetingWorkspaceView.tsx](/Users/edward/projects/doowon/apps/web/src/components/views/MeetingView/MeetingWorkspaceView.tsx)에서 `item.id === notesPageId || item.source_page_id === notesPageId`로 보강
- **결과**: notes editor 정상 부트스트랩, autosave/reload/Docs 진입 모두 통과

### Residual Notes

- recording row는 생성됐지만 worker queue가 없어서 `transcription_status = failed`, `failure_reason = "Background processing queue is unavailable. Raw audio was saved; retry later."`
- `재생`, `다시 시도` 버튼은 UI에 노출됐지만 agent-browser click만으로는 추가 시각 변화가 없었다. 다만 upload 자체와 failure fallback UI는 확인됨
- organizer 세션 기준 `agent-browser errors`는 비어 있었고, 콘솔에는 기존 PMS 차트 width warning과 Dialog description warning만 반복적으로 보였다

### Test Data

- Meeting: `9ae4de6a-9790-4d1d-a310-d62fbe86f3dd`
- Notes doc: `07181f9c-e4cb-4e3e-9120-f843e441f77d`
- Notes page(raw): `24a1a96f-4064-43bc-9c19-6cf5811f40be`
- Linked issue: `75d040c1-7d6a-4d13-9571-d9b43dea20cd` (`QASCEN-2`)
- Linked doc: `d804d74d-1528-440b-8c71-07ec41559aa5`
- Uploaded recording: `4b7dc764-c498-4b55-904e-1e501e6d9bef`
- Downloaded file: `/tmp/meeting-e2e-download.txt`
