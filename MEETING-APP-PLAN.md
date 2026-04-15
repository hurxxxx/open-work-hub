<!-- /autoplan restore point: captured 2026-04-10, commit=5ecdd05 -->
<!-- Plan mode: restore point stored inline (external file write disallowed). Original plan state begins at "## Context" below. -->

# Meeting 앱 신규 도입 계획

## Context

포털 앱바에 새 "Meeting" 앱을 추가한다. 현재 이 레포는 Nx 모노레포(React 19 + Router v7 프런트, FastAPI `aidoo_api` 백엔드, `apps/worker` 잡 처리기)로 구성되어 있고, PMS/Docs는 정식 백엔드 도메인이 있는 반면 **Planner는 백엔드가 없는 프런트 프로토타입**이다. 또한 AI 앱 네비에 "회의록" 어시스턴트와 Docs 네비에 "Meeting Notes" 진입점만 자리가 잡혀 있을 뿐 실제 구현이 없다.

이번 작업의 목적은 (1) 미팅 개설/참석자 관리/회의실 예약 UX, (2) 참석자 가용성 조회 기반 충돌 경고, (3) PMS 태스크·Docs 링크 + 자동 읽기 전용 권한 부여, (4) 녹음 → Whisper 전사 → LLM 요약 → 태스크 회의록 자동 생성, (5) 포털 홈 상단 위젯·개인 플래너 자동 반영을 엔드투엔드로 갖추는 것이다. Planner 백엔드가 없으므로 **공용 `events` 테이블**을 함께 구축해 Planner와 Meeting이 동일 소스를 바라보게 만든다. AI 회의록 어시스턴트 항목은 Meeting 앱으로 딥링크되는 진입점으로 남긴다.

사용자 결정 사항 (2026-04-10 확인):
- **범위**: 공용 이벤트 백엔드를 함께 구축
- **전사**: OpenAI Whisper + GPT API 실연동
- **태스크 권한**: 명시적 `issue_user_access` 테이블 신설
- **AI 회의록 관계**: Meeting이 본체, AI 메뉴는 딥링크

## 백엔드: 신규 도메인 두 개

### 1) `apps/api/src/aidoo_api/domains/calendar/` (새 공용 이벤트 도메인)

**DB 모델 (`models.py`)**
- `Event`: `id, workspace_id, owner_id, title, description, start_at, end_at, all_day, location_text, source_type ('planner' | 'meeting' | 'pms' | 'external'), source_id, event_type ('event' | 'task' | 'focus' | 'ooo' | 'meeting'), rrule (nullable), cancelled_at, created_at, updated_at`
- `EventAttendee`: `id, event_id, user_id, role ('organizer' | 'required' | 'optional'), response ('pending' | 'accepted' | 'declined' | 'tentative'), notified_conflict_at`
- 인덱스: `(user_id, start_at)` on EventAttendee, `(workspace_id, start_at, end_at)` on Event

**Router (`router.py`)**
- `GET /api/v1/calendar/events?user_id=&from=&to=` — 단일 사용자 이벤트 조회 (Planner가 사용)
- `POST /api/v1/calendar/availability` — body: `{user_ids: [...], from, to}` → 각 사용자별 busy 블록 리스트 반환 (Meeting 참석자 가용성 뷰가 사용)
- `POST /api/v1/calendar/events` — Planner/Meeting 공용 쓰기 진입점 (source_type 지정)
- `PATCH /api/v1/calendar/events/{id}`, `DELETE /api/v1/calendar/events/{id}`

### 2) `apps/api/src/aidoo_api/domains/meeting/`

**DB 모델 (`models.py`)**
- `MeetingRoom`: `id, workspace_id, name, capacity, location, equipment, is_active, created_by_admin_id, created_at`. 관리자 생성이 기본이나 `created_by_user_id` + `ad_hoc=True` 플래그로 미팅 개설자가 임시 추가한 장소를 구분.
- `Meeting`: `id, workspace_id, organizer_id, title, agenda, room_id (nullable), start_at, end_at, status ('scheduled' | 'in_progress' | 'completed' | 'cancelled'), event_id (FK→Event, organizer의 미러 이벤트), allow_conflicts (default True), created_at, updated_at`
- `MeetingAttendee`: `id, meeting_id, user_id, role, response, event_id (참석자별 개인 플래너 미러 이벤트), conflict_detected (bool), seen_conflict_at`
- `MeetingTaskLink`: `id, meeting_id, issue_id, added_by_id, created_at`
- `MeetingDocLink`: `id, meeting_id, doc_item_id, added_by_id, created_at`
- `MeetingNote`: `id, meeting_id, author_id, body_blocks (JSON, BlockNote 포맷), updated_at`
- `MeetingRecording`: `id, meeting_id, storage_key, duration_sec, uploaded_by_id, source ('live' | 'upload'), transcription_status ('pending' | 'transcribing' | 'summarizing' | 'done' | 'failed'), transcript_text, summary_text, linked_doc_id (nullable, 자동 생성된 Docs item), created_at`

**Router (`router.py`)** — 핵심 엔드포인트
- `GET /api/v1/meeting/rooms` / `POST /api/v1/meeting/rooms` — 관리자/개설자 생성 구분은 요청 페이로드 `ad_hoc` 플래그 + 역할 검사
- `GET /api/v1/meeting/meetings?scope=mine|upcoming|room=&from=&to=` — 홈 위젯과 메인 리스트 공용
- `POST /api/v1/meeting/meetings` — 생성 시 트랜잭션:
  1) `Meeting` + `MeetingAttendee` 생성
  2) organizer용 `Event` 생성 (source_type='meeting', source_id=meeting_id)
  3) 참석자별 개인 `Event` 미러 생성 + `EventAttendee` 레코드
  4) `POST /calendar/availability` 로직 재사용해 각 참석자 충돌 계산 → `MeetingAttendee.conflict_detected` 저장
  5) `MeetingTaskLink`/`MeetingDocLink` upsert → 권한 부여(아래)
- `PATCH /api/v1/meeting/meetings/{id}` — 참석자 추가/제거, 시간 변경 시 mirror event 동기화 + 권한 재평가
- `POST /api/v1/meeting/meetings/{id}/tasks` / `DELETE .../tasks/{issue_id}`
- `POST /api/v1/meeting/meetings/{id}/docs` / `DELETE .../docs/{doc_item_id}`
- `GET /api/v1/meeting/meetings/{id}/notes` / `PUT .../notes` — 공동 편집 노트 (BlockNote 블록)
- `POST /api/v1/meeting/meetings/{id}/recordings` — multipart 업로드 (파일 업로드 또는 live 녹음 청크)
- `GET /api/v1/meeting/meetings/{id}/conflict-feed` — 포털 접속 시 충돌 알림 조회 (`seen_conflict_at` null인 것)
- `POST /api/v1/meeting/meetings/{id}/conflict-feed/ack`

### 3) PMS 태스크 ACL 신설

- 파일: [apps/api/src/aidoo_api/domains/pms/models.py](apps/api/src/aidoo_api/domains/pms/models.py)
- 신규 모델 `IssueUserAccess`: `id, issue_id, user_id, access_level ('read'), granted_by_meeting_id, granted_at`
- [apps/api/src/aidoo_api/domains/pms/router.py](apps/api/src/aidoo_api/domains/pms/router.py) `_ensure_project_access()` (line 950 부근)에 폴백 추가: 프로젝트 멤버가 아니면 `IssueUserAccess`를 조회해 `access_level='read'`이면 읽기 전용 허용, 쓰기 경로에서는 여전히 차단. 기존 함수 하나를 `_ensure_issue_readable(user, issue)` / `_ensure_issue_writable(user, issue)`로 분할하고, 이슈 상세·댓글 조회 엔드포인트만 readable을 쓰도록 바꾼다.
- 미팅 저장 플로우에서 참석자×링크된 태스크 조합으로 upsert, 참석자 제거 시 해당 행 삭제.

### 4) Docs 공유는 기존 메커니즘 재사용

- [apps/api/src/aidoo_api/domains/docs/router.py](apps/api/src/aidoo_api/domains/docs/router.py)의 `upsert_native_doc_user_share()`(line ~1620)를 재사용해 `access_level='read'`로 grant. SpaceDoc의 경우 팀 권한 기반이라 별도 `SpaceDocUserShare` (없으면 신설) 또는 단일 `DocItemUserShare` 추상화. 구현 시 기존 Native 경로 우선으로 범위 축소.

### 5) 녹음/전사 파이프라인 (실연동)

- **Worker**: [apps/worker](apps/worker)에 `meeting_transcription` 잡 추가. 큐 트리거는 `POST /meeting/recordings` 성공 시 enqueue.
- **의존성 추가**: `openai` Python SDK (api와 worker 양쪽). API 키는 `OPENAI_API_KEY` 환경변수, 기존 settings 로더에 등록.
- **잡 로직**:
  1) `MeetingRecording.transcription_status = 'transcribing'`
  2) OpenAI Whisper API (`audio.transcriptions.create(model="whisper-1")`)로 `transcript_text` 채움
  3) `transcription_status = 'summarizing'`
  4) OpenAI Chat API (`gpt-4o-mini` 또는 설정값)로 참석자/안건/결정사항/액션아이템 포맷의 회의록 요약 생성
  5) Meeting에 linked task가 있으면: NativeDoc 또는 SpaceDoc `createNativeDoc()` 재사용으로 "회의록: {meeting.title} ({date})" 문서 생성 → 본문은 BlockNote 블록으로 변환 → `MeetingDocLink` 자동 추가, `MeetingRecording.linked_doc_id` 저장
  6) `transcription_status = 'done'`, WebSocket 또는 기존 polling 채널로 프런트 갱신
- 실패 처리: `transcription_status='failed'` + `failure_reason` 기록, 재시도 엔드포인트 `POST /meeting/recordings/{id}/retry`.

## 프런트엔드: `apps/web/src`

### 앱 등록 (세 군데 수정)
- [apps/web/src/constants.ts:44,49,55](apps/web/src/constants.ts#L44) — `ShellAppId`/`AppBarItem` 유니온에 `'meeting'` 추가, `APP_BAR_ITEMS`에 `{ id: 'meeting', title: 'MEETING', icon: Users, path: '/meeting' }` (Planner 뒤에 삽입). `NAV_ITEMS`에 Meeting 카테고리(Upcoming / My Meetings / Rooms / Recordings) 추가.
- [apps/web/src/app-shell.ts:4,11](apps/web/src/app-shell.ts#L4) — `ShellAppId`, `FEATURE_BY_APP_ID`에 `meeting: 'nav.meeting'` 추가.
- [apps/web/src/App.tsx:199-242](apps/web/src/App.tsx#L199) — `<Route path="/meeting/*" element={<WorkspaceGate featureCode="nav.meeting"><MeetingView /></WorkspaceGate>} />` 추가. SubSidebar 헤더 "+" 드롭다운(최근 커밋에서 추가됨)에도 "New Meeting" 항목 등록.
- 기존 AI 네비의 `{ id: 'meeting-minutes' }` 항목은 경로를 `/meeting?tab=recordings`로 유지해 딥링크.

### 도메인 레이어
- `apps/web/src/domains/meeting/meeting-api.ts` — 위 엔드포인트 래퍼들. 타입: `MeetingRoom`, `Meeting`, `MeetingAttendeeWithConflict`, `MeetingTaskLink`, `MeetingDocLink`, `MeetingRecording`.
- `apps/web/src/domains/meeting/meeting-permissions.ts` — `canEditMeeting`, `isOrganizer`, `canManageRooms`.
- `apps/web/src/domains/calendar/calendar-api.ts` — `listEvents`, `fetchAvailability`, `createEvent` 등. Planner가 하드코딩 대신 이걸 쓰도록 동시에 교체.

### 메인 화면: `apps/web/src/components/views/MeetingView/`

기존 `PMSView/` 폴더 구조(파일 25개)를 모델로 삼는다.

- `MeetingView.tsx` — 라우터. 탭: `Calendar` | `List` | `Rooms` | `Recordings`.
- `MeetingCalendar.tsx` — **Planner의 주/일 뷰 컴포넌트를 재사용**. 현재 [apps/web/src/components/views/PlannerView.tsx](apps/web/src/components/views/PlannerView.tsx)에 인라인돼 있는 그리드를 `components/views/PlannerView/CalendarGrid.tsx`로 추출해 양쪽에서 import. 드래그 셀렉션 시 `MeetingCreateModal`을 연다.
- `MeetingCreateModal.tsx` — 제목, 시간, 회의실 선택(`RoomPicker`), 참석자 추가(`AttendeePicker`), 가용성 오버레이, PMS 태스크 첨부(`TaskPickerModal`), Docs 첨부(`DocPickerModal`), 저장. 저장 후 충돌 참석자는 경고 뱃지로 표시하되 기본적으로 저장을 허용 (사용자 요구사항 반영).
- `RoomPicker.tsx` — 등록된 회의실 목록 + "장소 직접 추가" CTA (ad_hoc 생성).
- `AttendeePicker.tsx` — 사용자 검색은 기존 `/apps/web/src/domains/pms/pms-api.ts`의 사용자 검색을 재사용. 선택 직후 `fetchAvailability`를 호출해 행별 busy 바를 렌더.
- `AvailabilityOverlay.tsx` — 선택한 시간 범위에 대한 참석자×시간 매트릭스, 충돌 셀 하이라이트.
- `TaskPickerModal.tsx` — **신규** 컴포넌트. `listProjectIssues()` 재사용 + 워크스페이스 전역 `q` 검색 엔드포인트 추가 필요 (백엔드 계획에 포함).
- `DocPickerModal.tsx` — **신규**. `listDocsHub()` 재사용 + 검색 입력.
- `MeetingDetail.tsx` — 패널 구성: 요약/참석자(충돌 뱃지)/링크된 태스크·Docs/노트/녹음/전사 상태. 진행 중 상태에서 **LiveNotes**(BlockNote 에디터, autosave)와 **RecordingControls**(녹음 시작/정지/파일 업로드). 전사/요약 완료 시 `linked_doc_id`가 생기면 "회의록 보기" 링크가 노출된다.
- `MeetingRoomsAdmin.tsx` — 관리자 전용 CRUD. `hasSystemRole(user, 'admin')` 가드.

### 홈 위젯
- [apps/web/src/components/views/HomeView.tsx](apps/web/src/components/views/HomeView.tsx) — `Assigned to me` 섹션 위에 **"Today's Meetings"** 섹션 추가. `SectionHeader` 재사용, `meeting-api`의 `listMeetings({ scope: 'mine', from: today, to: tomorrow })`로 채운다. 현재 `assignedTasks` 하드코딩 패턴을 따라가되 실제 API 연동 (동일 섹션의 Tasks는 별도 작업). 각 카드 클릭 시 `/meeting/:id`로 이동.

### 충돌 알림 (포털 접속 시)
- 전역 레이아웃에 사용 중인 auth 훅 근처에 `useMeetingConflictToast()` 훅 추가. 로그인 직후 `GET /meeting/meetings/mine/conflict-feed`를 호출, 미확인 충돌이 있으면 `@aidoo/ui` 토스트/알림 드롭다운으로 노출하고 사용자가 확인하면 `POST .../ack`.

### SubSidebar "+" 드롭다운
- 최근 커밋(`5ecdd05`)에서 생성된 헤더 드롭다운에 "New Meeting" 항목과 단축키 추가. window 이벤트 `meeting:create-event`를 디스패치하는 패턴을 Planner에서 그대로 차용.

## 수정/신규 파일 요약

백엔드 신규:
- `apps/api/src/aidoo_api/domains/calendar/{__init__.py,models.py,router.py,schemas.py,service.py}`
- `apps/api/src/aidoo_api/domains/meeting/{__init__.py,models.py,router.py,schemas.py,service.py,permissions.py}`
- Alembic 마이그레이션 1개 (events, meeting_* , issue_user_access 테이블)
- `apps/worker/jobs/meeting_transcription.py`

백엔드 수정:
- [apps/api/src/aidoo_api/domains/pms/models.py](apps/api/src/aidoo_api/domains/pms/models.py) — `IssueUserAccess` 추가
- [apps/api/src/aidoo_api/domains/pms/router.py](apps/api/src/aidoo_api/domains/pms/router.py) — `_ensure_project_access`를 readable/writable로 분리
- `apps/api/src/aidoo_api/main.py` (또는 app factory) — 두 신규 라우터 마운트
- 워크스페이스 feature flag 테이블/시드에 `nav.meeting` 추가

프런트 신규:
- `apps/web/src/domains/meeting/`, `apps/web/src/domains/calendar/`
- `apps/web/src/components/views/MeetingView/` (10+ 파일)
- 테스트용 Vitest 파일

프런트 수정:
- [apps/web/src/constants.ts](apps/web/src/constants.ts)
- [apps/web/src/app-shell.ts](apps/web/src/app-shell.ts)
- [apps/web/src/App.tsx](apps/web/src/App.tsx)
- [apps/web/src/components/views/HomeView.tsx](apps/web/src/components/views/HomeView.tsx)
- [apps/web/src/components/views/PlannerView.tsx](apps/web/src/components/views/PlannerView.tsx) — 그리드 컴포넌트 추출, `calendar-api` 사용으로 교체, 개인 일정에 미팅 이벤트 자동 표시 (공용 events 조회로 해결됨)
- [apps/web/src/components/layout/SubSidebar.tsx](apps/web/src/components/layout/SubSidebar.tsx) — "+" 드롭다운에 New Meeting 항목

## 재사용 대상 (탐색에서 확인)

- 사용자/권한: [apps/web/src/domains/auth/auth-api.ts](apps/web/src/domains/auth/auth-api.ts), `hasFeatureAccess`, `WorkspaceGate`
- 디자인 토큰: [packages/ui/styles.css](packages/ui/styles.css), [apps/web/src/index.css](apps/web/src/index.css)
- UI 프리미티브: `@aidoo/ui` Button/Modal/Toast, BlockNote 에디터 (`/packages/ui/src/lib/editor`)
- PMS 이슈 조회: `listProjectIssues()` in [apps/web/src/domains/pms/pms-api.ts](apps/web/src/domains/pms/pms-api.ts)
- Docs 허브 조회/공유: `listDocsHub()`, `upsertDocUserShare()`
- Planner 그리드: [apps/web/src/components/views/PlannerView.tsx](apps/web/src/components/views/PlannerView.tsx) (추출 후 공유)
- Planner Schedule 팝오버: [apps/web/src/components/views/SchedulePopover.tsx](apps/web/src/components/views/SchedulePopover.tsx) (Meeting 모달의 기반)

## 표준 기능 중 함께 포함해야 할 항목

1. **시간대**: Event `start_at/end_at`은 UTC, 사용자 타임존은 UI 변환. Asia/Seoul 기본.
2. **반복 미팅(RRULE)**: Event 모델에 `rrule` 칼럼을 두되 1차 릴리즈에서는 생성 UI를 "없음"/"매주" 두 가지로 제한.
3. **취소·리스케줄 알림**: Meeting 변경 시 전체 참석자에게 알림 (기존 notification 채널 있으면 재사용, 없으면 새 `/api/v1/notifications` 기본 스텁).
4. **ICS/캘린더 내보내기**: `GET /meeting/meetings/{id}.ics` — 외부 캘린더 구독 편의.
5. **감사 로그**: 생성/수정/삭제, 권한 부여 이벤트를 기존 audit 채널에 기록 (관리자 보안 요구사항).
6. **접근성**: 모달 포커스 트랩, 캘린더 키보드 네비, 스크린 리더 라벨.
7. **레이트 리밋**: 녹음 업로드 엔드포인트, OpenAI 호출 큐 동시성 상한.
8. **비밀 관리**: `OPENAI_API_KEY`는 `.env`/secret manager 경유, 레포에 하드코딩 금지.
9. **파일 스토리지**: 녹음 파일 저장소 — 기존 media 도메인의 저장 경로 재사용 (탐색 시 `domains/media` 존재 확인).

## 검증 방법

1. **단위/통합 테스트**
   - 백엔드: `pytest apps/api/tests/meeting/` — 충돌 계산, 태스크/Docs 권한 폴백 (`IssueUserAccess`), 녹음 업로드 → 잡 디스패치.
   - 프런트: `pnpm -w vitest run apps/web/src/domains/meeting` — API 래퍼, 권한 헬퍼.
2. **엔드투엔드 수동 시나리오** (gstack 또는 browse 스킬로 자동화 가능)
   - 관리자가 회의실 2곳 등록 → 일반 사용자 A가 Meeting 앱에서 회의실/시간/참석자 B,C 선택 → C는 기존 이벤트로 충돌 뱃지 → PMS 태스크 T 첨부 → 저장.
   - B,C의 Planner에 미팅 이벤트가 즉시 뜬다.
   - B가 포털 재접속 시 충돌 토스트 노출, 확인 시 사라진다.
   - T에 대한 프로젝트 권한 없는 D를 추가 → D는 T를 읽기 전용으로 열 수 있으나 편집 UI는 숨김.
   - 미팅 진행 중 노트 작성 + 녹음 파일 업로드 → 잡 완료 후 `linked_doc_id` 생성, T 하위에 "회의록" 자동 첨부 확인.
   - 포털 홈 상단에 "Today's Meetings" 카드가 뜨는지 확인.
3. **회귀**: Planner 기존 화면이 `calendar-api`로 교체된 뒤에도 동일하게 동작하는지 수동 QA.
4. **성능**: 참석자 20명×2주 범위 가용성 조회가 1회 쿼리로 커버되는지(인덱스 확인), OpenAI 잡 동시성 상한 확인.

## 릴리즈 순서 제안 (PR 단위)

1. **PR1**: `calendar` 도메인 + Planner를 백엔드에 연결 (기존 동작 유지)
2. **PR2**: `meeting` 도메인(rooms, meetings, attendees) + 기본 MeetingView(Calendar/List/Rooms) + 홈 위젯 + AppBar 등록
3. **PR3**: PMS `IssueUserAccess` + TaskPickerModal/DocPickerModal + 링크/권한 부여
4. **PR4**: 노트 + 녹음 업로드 + worker 전사/요약 + 자동 회의록 Docs 생성
5. **PR5**: 충돌 알림 토스트, ICS 내보내기, 감사 로그, 접근성 마감

---

# AUTOPLAN REVIEW — Phase 1: CEO

## CEO Dual Voices Summary

**Both voices strongly agree the plan needs to change direction.** This is a USER CHALLENGE under autoplan protocol: the premise itself is being challenged, so the user must decide at the gate.

### Claude CEO Subagent (independent review)
- **Critical 1**: Plan does not answer "are users already on Outlook / Google / KakaoWork / corporate groupware?" — determines whether the whole calendar layer is waste.
- **Critical 2**: Shared `events` table couples Meeting to Planner, which has zero real users (PlannerView.tsx:176 `events = []`).
- **High**: `_ensure_project_access` refactor hides 15 call sites (router.py:970–3740), each requiring readable/writable judgment. Plan scopes it as 2.
- **High**: Building calendar grid "reused from Planner" hides that Planner grid has no data layer, no overlap math, no timezone logic.
- **High**: Whisper+GPT state machine + retry + WebSocket push is packaged as 1 PR but is realistically a full sprint.
- **High**: SpaceDoc share abstraction hidden in a sub-bullet is actually a new table + migration + UI.
- **Medium**: No OpenAI cost ceiling or per-org budget; recursive failure could balloon bill.
- **Medium**: `allow_conflicts=True` default renders the conflict detection decorative — users will ignore the badge.
- **Medium**: Home widget claimed to follow `assignedTasks` pattern but that's hardcoded — this would be the first real API-backed home section, inventing loading/empty/error states the plan doesn't budget.
- **Medium**: 5-PR release train is really 8–10 weeks of work.

**Recommended MVP**: "Meeting Minutes" — `Meeting` + `MeetingAttendee` + `MeetingTaskLink` + `MeetingDocLink` + `MeetingRecording` tables, upload-only recording, Whisper → GPT → auto-Doc → PMS task link, `IssueUserAccess` scoped to 2 endpoints. 1 PR, ~5–7 days. No calendar grid, no rooms, no availability, no shared events, no conflict detection, no home widget, no Planner refactor.

### Codex CEO Voice (adversarial, with web search)
- **Critical 1**: Problem not proven — no evidence Korean industrial firm needs a first-party calendar.
- **Critical 2**: This reinvents Microsoft Graph (`findMeetingTimes`, room resources, free/busy), Microsoft Bookings, and Teams Intelligent Recap (recordings, transcripts, notes, follow-up tasks, AI notes) — all already mature and likely licensed.
- **Critical 3**: Real wedge is meeting minutes → PMS tasks + Docs triangle, NOT calendar ownership. Import a Teams/Outlook meeting, upload audio, generate Korean minutes, link to PMS.
- **High**: Portal identity ≠ calendar identity. If actual meetings live in Outlook/Teams, new `events` table is a shadow calendar. Conflict warnings become misleading. Room booking is wrong unless rooms are managed inside the portal.
- **High**: Task-level ACL is dangerous. Changes PMS security model. Needs expiry, audit, revocation semantics, admin visibility, tests across every PMS read path.
- **High**: 5 PRs hides 8–12 weeks (Korean transcription validation, migrations, security review).
- **Medium-High**: OpenAI cost AND data policy unbudgeted. Sending confidential factory/supplier/pricing/labor/quality discussions to external AI service with no explicit policy is the bigger risk.
- **Medium**: Planner enhancement dismissed without analysis. Strengthen Planner for plant ops (shifts, maintenance windows, due dates) BEFORE building Meeting.

**Codex recommended wedge**: "meeting-minutes ingestion linked to PMS/Docs," integrated with Outlook/Teams via Microsoft Graph before building any proprietary calendar. Require a discovery gate before any code is written.

## CEO CONSENSUS TABLE

```
═══════════════════════════════════════════════════════════════════════
  Dimension                              Claude       Codex     Consensus
  ────────────────────────────────────── ──────────── ────────── ────────
  1. Premises valid?                     NO           NO         CONFIRMED DISAGREE
  2. Right problem to solve?             NO (minutes) NO (minutes) CONFIRMED DISAGREE
  3. Scope calibration correct?          NO (2x over) NO (8-12wk) CONFIRMED DISAGREE
  4. Alternatives explored?              NO           NO         CONFIRMED
  5. Competitive risk covered?           NO (MS Bookings) NO (Graph/Teams) CONFIRMED
  6. 6-month trajectory sound?           NO (events coupling) NO (source of truth trap) CONFIRMED
═══════════════════════════════════════════════════════════════════════
CONFIRMED DISAGREE = both models flag the plan's choice as wrong
```

**Cross-phase theme**: Both models independently flag (a) the Outlook/Graph question as blocking, (b) Meeting Minutes as the real wedge, (c) task-level ACL as a serious undertaking not a side quest, and (d) the shared `events` table as a source-of-truth trap.

## 0B. Existing Code Leverage (verified by Claude subagent)

| Sub-problem | Plan claim | Verified state |
|---|---|---|
| Calendar grid | "extract from PlannerView, reuse" | PARTIAL. Grid exists but renders from `events = []`. No data layer, no overlap math, no timezone handling. Reuse hides a rewrite. |
| Home widget | "follow assignedTasks pattern" | MISLEADING. assignedTasks is hardcoded sample data. Meeting widget would be the first real API-backed home section. |
| PMS ACL split | "line 950, split into readable/writable" | CORRECT location but 15 call sites not 2. Each needs audit. |
| Docs share reuse | "upsert_native_doc_user_share ~1620" | CORRECT for NativeDoc. SpaceDoc has no equivalent — "or SpaceDocUserShare" hides a new table. |
| IssueUserAccess model | "add to pms/models.py" | CORRECT — mechanical add. |
| Planner/Meeting/Calendar backend | "none exist" | CORRECT — `domains/` has admin/auth/docs/documents/drafts/media/ocr/plm/pms/wiki_pms only. |

## 0C-bis. Implementation Alternatives (now on the table)

**APPROACH A: Full first-party Meeting app (PLAN AS WRITTEN)**
- Effort: XL (~8–12 weeks realistic)
- Risk: High
- Pros: One unified portal experience, no external dependencies, complete control
- Cons: Reinvents Microsoft/Google calendar primitives, 2-month build, shadow-calendar trap, unproven demand, cost/data policy gaps

**APPROACH B: Meeting Minutes MVP — "transcription + PMS/Docs linkage" only (RECOMMENDED by both voices)**
- Effort: M (~1 PR, 5–7 days)
- Risk: Low
- Pros: Ships the ONE differentiated piece (PMS task ↔ meeting ↔ auto-Docs triangle), no calendar/room/availability reinvention, low OpenAI exposure, deferable decisions stay deferable
- Cons: Not a "meeting scheduler" — must be named/marketed as Meeting Minutes or Transcription. No scheduling UX in v1.
- Scope: `Meeting` + `MeetingAttendee` + `MeetingTaskLink` + `MeetingDocLink` + `MeetingRecording` tables, upload-only recording, worker job (Whisper → GPT → NativeDoc → link to selected PMS tasks), `IssueUserAccess` scoped to 2 endpoints (detail + comments), minimal MeetingView (list + create modal with task/doc picker + file upload), AI sidebar deep-link rewired.

**APPROACH C: Microsoft Graph / Outlook integration shell**
- Effort: L (~3–4 weeks)
- Risk: Medium — auth, tenant consent, token refresh; worthless if Doowon is NOT on M365
- Pros: Zero calendar reinvention, availability is free from `findMeetingTimes`, matches where users actually work, rooms via Graph resources
- Cons: Requires M365 admin consent + tenant configuration, harder to demo without credentials, data still flows to Microsoft (policy question remains)

**APPROACH D: Planner enhancement + defer Meeting entirely**
- Effort: S–M
- Risk: Low
- Pros: Planner currently has 0 real users — build real backend for the workflows that matter (shift schedules, maintenance windows, due dates, production events). Meetings join later as calendar imports.
- Cons: Doesn't address meeting minutes at all; separate decision.

## Discovery Questions That Block Approach Selection

Both voices independently say these questions MUST be answered before any approach is chosen:

1. **Calendar stack**: What does Doowon actually use today — Outlook/M365, Google Workspace, Kakao Work, groupware (그룹웨어), ERP scheduling, nothing?
2. **Meeting pain**: Is the pain "we can't schedule meetings easily" OR "we can't turn meeting output into tracked work"?
3. **Data policy**: Can confidential meeting audio be sent to OpenAI? Or must transcription be on-prem / in-region?
4. **Room booking**: Are physical meeting rooms currently managed anywhere? (Outlook resources, a spreadsheet, nothing?)
5. **Target user**: Plant operators? Office workers? Engineers? Executives? Different groups live in different tools.

## Phase 1 Gate Resolution (user decision, 2026-04-10)

**User answers to premise gate:**
1. **Calendar stack**: None / portal is first calendar. Doowon has NO existing Outlook, Teams, Google Workspace, or standard groupware calendar that employees live in today.
2. **Real pain**: Meeting output → PMS/Docs auto-linking (memory loss, status visibility gap). Confirms both reviewers' diagnosis of the wedge.
3. **Data policy**: ON-PREM TRANSCRIPTION REQUIRED. Confidential industrial content cannot flow to OpenAI. HARD CONSTRAINT.
4. **Direction**: Approach A (full Meeting app, 5 PR plan) — user chose to keep the original scope.

### How the user's answers change the review

- **Invalidated concerns** (both voices): shadow-calendar trap, duplicate-of-Outlook competitive risk, portal-identity ≠ calendar-identity problem. These assumed an existing corporate calendar that does not exist at Doowon. With no incumbent, building the first-party calendar is no longer reinventing the wheel.
- **Still valid concerns**: task-level ACL complexity (15 call sites, expiry/audit/revocation semantics), calendar grid reuse claim is hollow (PlannerView renders from empty array), SpaceDoc share hides a new table, home widget is the first real API-backed home section, `allow_conflicts=True` default makes conflict detection decorative unless acted on.
- **New hard constraint**: transcription and summarization pipeline MUST be on-prem. OpenAI Whisper API and GPT API are removed from scope.

### Plan change: on-prem transcription swap (replaces the OpenAI section above)

The "녹음/전사 파이프라인" section (section 5 in the original backend plan) is replaced with this:

- **Worker dependency swap**: Remove `openai` Python SDK. Add `faster-whisper` (CTranslate2-backed Whisper, CPU or GPU). Model choice: `large-v3` for Korean quality (multilingual, best-in-class for KR as of 2026), with `medium` fallback if GPU is unavailable. Models cached under a dedicated path, not pulled per job.
- **GPU / resource planning**: The worker host needs either (a) a GPU with ≥8GB VRAM for `large-v3` real-time, or (b) CPU-only with acceptance that a 60-minute meeting takes ~30–60 minutes to transcribe. This is a deployment decision — flag it to the ops owner, do not ship blind.
- **LLM summarization**: Since OpenAI is out, summarization must use a locally hosted LLM. Recommended: **Ollama** running a Korean-capable model (`gemma2:9b-instruct`, `qwen2.5:14b-instruct`, or `llama3.1:8b-instruct`) on the same worker host, called via HTTP. Alternative: route summarization through an existing internal LLM gateway if the company already runs one (check with AI team before building a new one). Leaves "which LLM exactly" as a taste decision to be resolved in Phase 3 eng review.
- **Job state machine**: unchanged from the original plan — `pending → transcribing → summarizing → done → failed`.
- **Cost risk**: eliminated (no external API calls). Replaced with capacity risk (worker throughput). Add a queue length metric and alerting so ops knows when transcription is backing up.
- **Data policy**: all audio stays within the cluster. Media storage uses the existing `domains/media` abstraction (do not invent a new bucket). Add an explicit "confidential / on-prem only" tag on `MeetingRecording` records for audit traceability, in case a future version adds an opt-in cloud path.

### PR sequencing insight from the gate

Both CEO reviewers and the user agree the minutes → PMS/Docs linkage is the highest-value piece. Reorder the 5-PR plan so the minutes pipeline ships earlier and can be validated with real users before the calendar grid, rooms, or conflict detection are built:

1. **PR1**: `meeting` domain skeleton (Meeting, MeetingAttendee, MeetingTaskLink, MeetingDocLink, MeetingRecording tables), AppBar registration, MeetingView list + create modal (no calendar grid yet), TaskPickerModal, DocPickerModal, AI sidebar deep-link rewired.
2. **PR2** ✅ **shipped 2026-04-13** ([PR1-STATUS.md 라운드 13](PR1-STATUS.md) 참고): `IssueUserAccess` with audit/expiry/revocation (full treatment per H3), 3-mode ACL split per H2 (`_ensure_list_member` / `_ensure_issue_readable` / `_ensure_issue_writable`, only 3 of 14 callsites get IssueUserAccess fallback), DocMeetingAccess fallback per H4 (NativeDoc only, SpaceDoc deferred). Multi-meeting safety via `(issue_id, user_id, granted_by_meeting_id) WHERE revoked_at IS NULL` partial unique. Cross-workspace attendees rejected with 422. PMS `pms_projects` → `pms_lists` rename (Strategy B, table + FK + URL alias). Meeting create one-step (`task_ids[]`/`doc_ids[]` atomic), reschedule TTL sync, MeetingDetail click UI to PMS/Docs detail, ensure_*_attachable to block chain abuse. Verified: 80 pytest passed, web typecheck 0, dev DB head `8b1b7fa4b72b`.
3. **PR3**: Recording upload + worker `meeting_transcription` job (faster-whisper + Ollama), auto Doc generation, status polling endpoint.
4. **PR4**: `calendar` domain + shared events + Planner wiring, MeetingCalendar grid extraction, RoomPicker + meeting rooms admin, AttendeePicker with availability overlay, conflict detection.
5. **PR5**: Home widget, conflict toast, ICS export, RRULE weekly, audit logs, accessibility, rate limits.
   - ~~**이월 from PR1 (2026-04-13)**: Space Docs 페이지 단위 reorder/move DnD UX — `NativeDocPage.sort_order` 필드와 router 의 sort_order 저장은 준비 완료 상태이나, DocsView 프런트에 drag-and-drop affordance 가 없음. dnd-kit 또는 유사 라이브러리로 트리 reorder + sibling 이동 UI 추가. 예상 4–6h.~~ **완료 2026-04-15** — `@dnd-kit` 도입 후 DocsView 를 `DocsPageTreeNode` + `DndContext` 로 재작성, 순수 유틸 + 14 vitest + 2 pytest + 키보드/포인터 E2E 확인. 상세는 TODO-PLAN.md:118.
   - **이월 from PR1 (2026-04-13)**: 다크모드 색상 contrast audit — `.dark` 토큰과 약 130곳의 `text-app-ink/40` opacity 변형, 6곳의 direct `bg-gray-500` 사용처, shadow 대비를 WCAG AA (4.5:1) 기준으로 검증. D6 항목의 재강조.

PR1–PR3 deliver the differentiated wedge. PR4–PR5 deliver the "standard meeting system" completeness the user asked for. If PR1–PR3 ship and usage metrics show meeting minutes is the whole value, PR4–PR5 can be trimmed. If usage shows scheduling conflicts are the real pain, PR4 gets invested in fully.

**Phase 1 Status: COMPLETE.** Premise gate passed with clarifications. Proceeding to Phase 2 (Design Review).

---

# AUTOPLAN REVIEW — Phase 2: Design

## Design Dual Voices Summary

**Both voices strongly agree** on the same set of P0 issues. No meaningful disagreement — the plan is architecturally detailed but underspecified as a UI/UX contract. The implementer and the user's mental model do not match.

### Claude Design Subagent (independent)

Scorecard:

| # | Dimension | Score | What a 10 looks like |
|---|---|---|---|
| 1 | Information hierarchy | 3/10 | Wireframe-level "first/second/third glance" spec for MeetingView landing, Create modal, Detail, home widget |
| 2 | Missing states | 2/10 | Every surface ships with loading/empty/error/partial/success specified |
| 3 | Journey emotional arc | 5/10 | Named magical moments (auto-minutes-on-task) and named friction mitigations (progressive disclosure, optimistic UI, persistent progress) |
| 4 | Specificity | 3/10 | Each component has token-level spec (sizes, placement, copy, lucide icons, state transitions) |
| 5 | Edge case paranoia | 2/10 | All 8 edge cases (a–h) plus cancelled/declined flows have behavior rules |
| 6 | Accessibility | 2/10 | Focus order, ARIA, keyboard schema, live regions, contrast specified in PR2 not PR5 |
| 7 | Design system alignment | 4/10 | Every component references which existing token/class/primitive it extends |

Missing states matrix — every new surface (MeetingView list, MeetingCalendar grid, MeetingCreateModal, AttendeePicker, TaskPickerModal, DocPickerModal, MeetingDetail, RecordingControls, LiveNotes, MeetingRoomsAdmin, Home widget, Conflict toast) is missing loading/empty/error/partial states. Only `transcription_status` enum has partial-state treatment. Everything else assumes the API returns on the first try.

Top P0 issues:
1. Transcription wait UX is a black hole (4-hour recordings → 10+ min jobs with no progress surface).
2. AvailabilityOverlay has zero visual spec despite being the hero of MeetingCreateModal.
3. All surfaces missing loading/empty/error specs.
4. a11y deferred to PR5 with a one-line bullet — focus trap, keyboard nav for calendar grid (Planner currently has NONE), live regions for transcription status, color-only conflict badges must move to PR2.

Design system drift risks: plan never names `app-text-*` classes, `card`, `SectionHeader`, `sidebar-submenu-*`, lucide icon vocabulary, or `--ui-color-warning/danger/success` tokens. HomeView priority colors use raw Tailwind (`red-500`) — if Meeting copies that pattern for semantic conflict state, it will drift from Docs/PMS semantics. Dark mode never mentioned.

### Codex Design Voice (adversarial, with code grounding)

Core verdict: "Plan serves the developer's data model first; it does not yet serve the user's mental model."

- **Create modal hierarchy is inverted.** Plan lists fields in schema order: title → time → room → attendees → availability → tasks → docs → save. User's eye should land on **meeting purpose and linked work first**: title → PMS task/Doc linkage → time → attendees → room. Availability becomes a decision aid near Save, not another widget in the middle.
- **Conflict handling must be loud, not passive.** If `allow_conflicts=True`, the primary action must change to `겹쳐도 생성` with an amber inline banner above Save: `2명 일정이 겹칩니다: 김민수, 박지현`. Buttons: `시간 다시 보기` (secondary) and `겹쳐도 생성` (primary, amber). Row badge: `충돌 2명`. Red is reserved for failed save or unavailable room, NOT allowed conflicts.
- **Home widget must follow HomeView row rhythm, NOT cards.** Existing HomeView is calm, narrow, bordered rows with SectionHeader (HomeView.tsx:84). "Today's Meetings" should be a compact row list: time, title, linked task/doc chip, status. No dashboard blocks.
- **MeetingDetail hierarchy is a component inventory, not a layout.** Top of detail should be: meeting title/status, linked PMS task/Doc, next action. Recording/minutes generation belongs above secondary metadata when active. Attendees and room are supporting context.
- **Transcription progress rail is missing.** `pending → transcribing → summarizing → done` is backend state. User should see `녹음 업로드됨 → 음성 인식 중 → 회의록 정리 중 → PMS 태스크에 첨부됨`. Show queue position or coarse ETA for on-prem workers. Completion must be discoverable from Home, MeetingDetail, AND the linked PMS task — not hidden inside Meeting.
- **SchedulePopover is not a sufficient modal base** — it's a 400px bottom popover with placeholder "ClickUp tasks and docs" text (SchedulePopover.tsx:73). A real MeetingCreateModal needs a proper workflow, not a repainted planner quick-add.
- **Planner reuse will haunt implementation.** PlannerView currently has `events = []` at line 176, mouse-only drag selection, no overlap layout, no timezone model, no keyboard nav. Extraction without a design spec produces a hollow grid with colored rectangles. See PR4 block for the explicit must-have rewrite list (overlap math, now indicator, all-day strip, drag-move/resize, agenda view, Monday week-start, unscheduled PMS drawer).
- **Accessibility cannot wait until PR5.** Create modal, conflict warning, recording controls, toast/feed, and calendar selection need a11y in the first PR where each appears. Planner cells are clickable `div`s, drag is mouse-only, icon buttons lack labels — copying this is a non-starter.

## DESIGN CONSENSUS TABLE

```
════════════════════════════════════════════════════════════════════════════
  Dimension                              Claude     Codex      Consensus
  ────────────────────────────────────── ────────── ────────── ─────────────
  1. Info hierarchy serves user?         NO (3/10)  NO         CONFIRMED NO
  2. Missing states covered?             NO (2/10)  NO (broad) CONFIRMED NO
  3. Journey has no friction cliffs?     NO (5/10)  NO         CONFIRMED NO
  4. Specific enough for 2 implementers? NO (3/10)  NO         CONFIRMED NO
  5. Edge cases covered?                 NO (2/10)  NO         CONFIRMED NO
  6. A11y fits scope/PR?                 NO (2/10)  NO         CONFIRMED NO
  7. Design system alignment explicit?   NO (4/10)  NO         CONFIRMED NO
════════════════════════════════════════════════════════════════════════════
No disagreements. Overall: 3.0/10 average — plan is NOT a design spec.
```

## Design Decisions Locked In (auto-decided via 6 principles)

Both voices agree on specific prescriptions. These are **auto-decided** as MECHANICAL (P5 explicit-over-clever + P1 completeness) and written into the plan as requirements for implementation:

### D1. MeetingCreateModal field order (user mental model, not schema)
1. **Meeting purpose**: Title input (focus on open, full-width, 200 char limit with Korean line-clamp-2)
2. **Linked work (hero)**: "연결된 업무" section with TaskPicker + DocPicker chips. This is the magical-moment anchor. Promoted to second position.
3. **Time**: Date/time range picker. Korean timezone (Asia/Seoul) displayed explicitly.
4. **Attendees**: AttendeePicker with inline avatar row.
5. **Availability (decision aid, not hero widget)**: Appears below attendees once ≥1 attendee is selected. Horizontal strip per attendee, 15-min slot granularity, busy blocks in `--ui-color-warning`, max 8 rows before virtual scroll. If more attendees, show aggregate "N명 중 M명 가능" summary on top.
6. **Room**: RoomPicker (searchable dropdown + "회의실 직접 추가" CTA for ad-hoc).
7. **Save row**: Sticky bottom. Left: "취소". Right: primary button. Primary button text is **dynamic**:
   - No conflicts: `회의 만들기` (default accent)
   - Conflicts detected: `겹쳐도 생성` (amber `--ui-color-warning`) with inline banner above: `⚠ 2명 일정이 겹칩니다: 김민수, 박지현` and a secondary `시간 다시 보기` link.

### D2. Home "Today's Meetings" widget follows HomeView row pattern
- Placed ABOVE "Assigned to me" (highest morning relevance).
- Uses the same `SectionHeader` component and `border-t border-app-border` row pattern (HomeView.tsx:87–102).
- Row content: `{start_time HH:mm} · {title (line-clamp-1)} · {linked task chip, optional} · {status dot}`.
- Max 5 rows, then `전체 보기 ({N})` link to `/meeting`.
- Sort: `start_at asc` for upcoming today; completed meetings today are grayed (`opacity-50`) and sorted after upcoming.
- States: loading = 3 skeleton rows (reuse existing skeleton pattern from PMS), empty = `오늘 예정된 회의가 없습니다` with SectionHeader subtitle, error = `불러올 수 없습니다. 다시 시도` inline retry link.

### D3. MeetingDetail hierarchy (role-based layout)
Top-to-bottom in the main column:
1. Header: title, status badge, start/end time with room.
2. **Linked work row** (hero, only if links exist): `이 회의는 {task chip} {doc chip}에 관한 것입니다.`
3. **Active state hero** (only while `in_progress` or a recording is processing): Recording controls + LiveNotes OR a transcription progress rail (see D4).
4. Attendees list with response chips (accepted/declined/pending).
5. Agenda/description.
6. Completed outputs: linked auto-generated meeting notes Doc, recording file, transcript excerpt.
7. Meta: organizer, created_at, audit trail (for admins).

Side column (right panel, md+): Quick actions (edit, cancel, export ICS), copy meeting link, "add to my calendar" stub.

### D4. Transcription progress rail (the magical-moment backbone)
Replace raw status enum with a four-step user-visible rail:
```
[●]──[●]──[○]──[ ]──[ ]
 업로드  음성인식  회의록정리  PMS첨부  완료
```
- Rail appears on MeetingDetail, on the Home widget row (as an inline badge `⏳ 회의록 정리 중`), and on the linked PMS task detail (`📄 회의록 생성 중…` banner).
- Each step is a live region so screen readers announce state changes.
- "Safe to leave" affordance: after upload completes, show `이 페이지를 닫아도 됩니다. 완료되면 알려드립니다.`
- On failure: amber banner with `다시 시도` button (calls retry endpoint).
- On completion: toast `회의록이 {task 제목}에 첨부되었습니다` with a `바로 보기` link. A notification is pushed to the PMS task assignee.
- Progress is polled every 3s while rail is visible; no websocket for v1 (simpler, and queue-backed jobs benefit from predictable polling).

### D5. Conflict warning flow (loud, not passive)
- In AttendeePicker: busy cells highlighted in `--ui-color-warning`.
- In Create modal save row: amber inline banner (see D1).
- In MeetingView list: row badge `충돌 {N}명` using lucide `AlertTriangle` + text (never color-only).
- In Home widget row: if meeting has unresolved conflict, show `⚠ 충돌 {N}명` pill.
- In portal conflict toast: fires on login if user has upcoming meeting with `conflict_detected=true AND seen_conflict_at IS NULL`. Copy: `{date} {time} 회의가 {other meeting title}와 겹칩니다. [확인] [회의 보기]`.

### D6. Accessibility moves to PR2 (not PR5)
Concrete a11y requirements shipped with each feature's first PR (not polish PR5):
- **PR1 (MeetingView list + Create modal)**: Modal focus trap + focus return, all form fields labeled, conflict banner as `role="alert"` with live region, Korean screen-reader smoke test (VoiceOver + Pretendard), RecordingControls with `aria-live` announcing recording state, icon-only buttons have `aria-label`.
- **PR2 (ACL + pickers)**: TaskPicker / DocPicker keyboard nav (arrow keys, Enter to select, Esc to close), selected chips announced.
- **PR3 (Recording + transcription)**: Progress rail as `aria-live="polite"`, each state change announced with a full sentence not just the step name.
- **PR4 (Calendar grid)**: Arrow-key navigation across cells, Enter to create, Space to select range, Esc to cancel. Replace Planner's `div` cells with real `button role="gridcell"` elements. Do NOT carry forward Planner's mouse-only drag.
- **PR5 (Polish)**: Color-contrast audit (4.5:1 minimum) across both light and dark mode for every semantic color (warning/danger/success/status dots).

### D7. Design system usage table (mandatory reference in implementation)

| Surface | Typography | Container | Tokens | Icons (lucide) |
|---|---|---|---|---|
| MeetingView list row | `app-text-body`, `app-text-caption` | `border-t border-app-border` row (HomeView pattern) | `--ui-color-ink`, `--ui-color-ink-subtle` | `Video`, `Users`, `AlertTriangle` |
| Home widget row | Same as MeetingView list row | Same — `SectionHeader` + border row | Same | Same + `ChevronRight` |
| MeetingCreateModal | `app-text-title-md` header, `app-text-body` fields, `app-text-caption` hints | `@aidoo/ui` `Dialog` (centered, NOT SchedulePopover) | `--ui-color-surface`, `--ui-color-border`, `--ui-color-warning` for conflict banner | `X` close, `Calendar`, `Users`, `MapPin`, `CheckCircle`, `FileText`, `Plus` |
| MeetingDetail | `app-text-title-lg`, `app-text-title-md`, `app-text-body` | `card` class for hero, bordered sections for rest | `--ui-color-surface`, semantic status via `--ui-color-success/warning/danger` | `Video`, `Mic`, `FileText`, `Link2`, `Users`, `MapPin`, `Clock` |
| AvailabilityOverlay | `app-text-micro` for time labels | Inner panel of Create modal | `--ui-color-warning` busy, `--ui-color-success` free | none (pure rectangles) |
| RecordingControls | `app-text-body` | `card` or inline panel | `--ui-color-danger` pulsing dot while recording | `Mic`, `Square` (stop), `Upload`, `Pause` |
| TranscriptionRail | `app-text-caption` step labels | Inline below actions | `--ui-color-accent` active, `--ui-color-ink-subtle` inactive | `Check` (done), `Loader2` (in-progress spin) |
| ConflictToast | `app-text-body` | `@aidoo/ui` Toast | `--ui-color-warning` background | `AlertTriangle` |
| MeetingRoomsAdmin | `app-text-title-md`, `app-text-body` | Table (same pattern as PMS admin views) | Standard | `Plus`, `Edit2`, `Trash2`, `MapPin` |

**Dark mode**: All surfaces ship both light and dark. Use the existing `dark:` Tailwind variants — do not invent new tokens.

### D8. Edge cases (bound to specific rules)

| Case | Rule |
|---|---|
| 30+ attendees | AvailabilityOverlay virtualizes rows after 8; aggregate header shows `N명 중 M명 가능`. Attendee chips wrap with `flex-wrap`, not horizontal scroll. |
| 200-char Korean title | `line-clamp-1` in grid chip, calendar event block, widget row. `line-clamp-2` in list cards. Full in detail header with `break-all` for Korean wrapping. |
| 4-hour recording mid-transcription | Transcription rail persists on Home widget + PMS task. "Safe to leave" message shown. ETA copy: `약 10–30분 소요` when known, else `처리 중` spinner only. |
| Event crosses midnight | Calendar grid renders a continuing block on both days with top/bottom arrow indicators. List view shows one row with `{date} 23:55 → {date+1} 00:10`. |
| Attendee deleted mid-meeting | Tombstone chip: `탈퇴한 사용자`, grayed, no avatar. ACL cleanup async job removes their `IssueUserAccess` rows. |
| Linked PMS task archived | Task chip shown with strikethrough + `보관됨` badge. Still clickable (read-only view). ACL row remains (no auto-revoke — separate admin decision). |
| 3 simultaneous conflicts | `conflict_count` (int) on MeetingAttendee, not boolean. Badge shows `충돌 3건`. Tooltip lists conflicting event titles. |
| 12 meetings on Home widget today | Show first 5 + `전체 보기 (12)` link. Do not scroll-inside-widget. |

## Phase 2 Status: **COMPLETE.** 8 design decisions (D1–D8) locked in as implementation requirements. Proceeding to Phase 3 (Eng Review).

---

# AUTOPLAN REVIEW — Phase 3: Eng

## Eng Dual Voices Summary

**Both voices independently found the same three CRITICAL landmines and the same six HIGH issues.** Extraordinary consensus. Every finding is verified against real file paths and line numbers. This is the strongest signal in the whole autoplan run.

## ENG CONSENSUS TABLE

```
════════════════════════════════════════════════════════════════════════════
  Dimension                              Claude     Codex      Consensus
  ────────────────────────────────────── ────────── ────────── ─────────────
  1. Architecture sound?                 NO         NO         CONFIRMED NO
  2. Test coverage sufficient?           NO (4/17)  NO         CONFIRMED NO
  3. Performance risks addressed?        NO (index) NO (index) CONFIRMED NO
  4. Security threats covered?           NO (ACL)   NO (ACL)   CONFIRMED NO
  5. Error paths handled?                NO         NO         CONFIRMED NO
  6. Deployment risk manageable?         NO (no migrations) NO CONFIRMED NO
════════════════════════════════════════════════════════════════════════════
```

**Cross-phase themes** (concerns appearing in 2+ phases' dual voices independently):
- **PMS ACL complexity** — CEO phase flagged "15 call sites not 2, dangerous security side quest", Eng phase independently verified and produced the route-by-route audit. HIGH CONFIDENCE.
- **Whisper pipeline state machine / worker architecture** — CEO phase flagged "1 PR hides a sprint", Eng phase confirmed there's no production Celery job contract (no acks_late, retry, time limits, DLQ, cancellation, idempotency) and this would be the first real long-running job. HIGH CONFIDENCE.
- **Transcription wait UX missing** — Design phase flagged as the single biggest UX risk, Eng phase confirmed the backend state machine is insufficient for multi-hour jobs. Both phases converge on the same gap. HIGH CONFIDENCE.

## Critical Findings (CONFIRMED by both voices)

### C1. Project has no Alembic — plan's "Alembic 마이그레이션" is unimplementable
- Verified: `apps/api/pyproject.toml:12` lists Alembic as a dependency, but there is NO `alembic.ini`, NO `alembic/`, NO `versions/` directory.
- Current schema management: `apps/api/src/aidoo_api/core/db.py:41` calls `Base.metadata.create_all()` plus hand-written compatibility SQL.
- Impact: PR1 cannot safely add ~10 new tables as described. Any ALTER in later PRs will silently diverge from the declared models.
- **AUTO-DECISION (Mechanical, P1 completeness)**: Add a **PR0** before PR1 that (a) bootstraps Alembic (`alembic init`, generate baseline from current Base.metadata via `alembic revision --autogenerate`, stamp head), (b) adds CI guard that fails if models drift from the latest revision, (c) documents the migration workflow in the API app's README. Alternative (fallback): stay on create_all with additive-only schema and hard-block any ALTER until Alembic ships. Plan must pick one in PR0.

### C2. Media router + orphan cleanup beat will silently DELETE meeting recordings
- Verified:
  - `apps/api/src/aidoo_api/domains/media/router.py:24` — upload reads entire file into memory via `await file.read()`
  - `apps/api/src/aidoo_api/domains/media/router.py:50` — size cap is 10 MB (`MAX_MEDIA_UPLOAD_SIZE`)
  - `apps/api/src/aidoo_api/domains/media/router.py:216` — `resource_type` accepts only `issue` and `space_doc_page`
  - `apps/worker/src/aidoo_worker/celery_app.py:15` — beat schedule includes `cleanup_orphan_media` hourly
  - `apps/worker/src/aidoo_worker/tasks/media.py:50` — task deletes media rows older than 24h where `resource_type IS NULL`
- Impact: A 4-hour recording is ~115 MB and will be rejected by the 10 MB cap. Even if uploaded, if the ingest code forgets to set `resource_type='meeting_recording'`, the hourly beat task silently deletes the file. This is a **data loss** bug waiting to happen.
- **AUTO-DECISION (Mechanical, P1 completeness)**: The plan adds a dedicated `POST /api/v1/meeting/recordings` endpoint (PR3) with (a) streaming upload to MinIO via `put_object(..., length=-1, part_size=5*1024*1024)` multipart, (b) per-resource size cap (1 GB), (c) `audio/*` content-type policy, (d) `resource_type='meeting_recording'` and `resource_id=recording.id` on the MediaFile row so orphan cleanup skips it. Do NOT reuse `/media/upload`. Also: `apps/worker/src/aidoo_worker/tasks/media.py:50` gets a fix that explicitly excludes `resource_type IN ('meeting_recording')` even when it IS set, as a belt-and-suspenders guard, and an integration test verifies the cleanup job does NOT delete meeting recordings.

### C3. No production Celery job contract — meeting_transcription would be the first long-running workload
- Verified: existing tasks at `apps/worker/src/aidoo_worker/celery_app.py:8`, `apps/worker/src/aidoo_worker/tasks/ocr.py:4`, `apps/worker/src/aidoo_worker/tasks/media.py:38` are all stubs or short cleanup jobs. None have `acks_late=True`, `task_time_limit`, retry policy, DLQ, cancellation, idempotency keys, or progress heartbeats.
- Impact: A 4-hour recording running through faster-whisper + Ollama will blow past Celery defaults, not retry correctly on transient Ollama failures, continue running if the meeting is deleted, and leave orphan partial Docs if the summarization step crashes.
- **AUTO-DECISION (Mechanical, P1 completeness + P5 explicit)**: PR3 includes a production Celery contract for meeting jobs, documented inline:
  - Split into `meeting.transcribe` (CPU/GPU-bound) and `meeting.summarize` (LLM-bound) chained via Celery `chain()`. Each retries independently.
  - `acks_late=True`, `task_time_limit=3600` (1h hard), `task_soft_time_limit=3300`, `autoretry_for=(TransientError,)`, `max_retries=3`, `retry_backoff=True`, `retry_jitter=True`.
  - Idempotency key = `(MeetingRecording.id, stage)`. Each stage writes a transition atomically; on retry, skip completed stages.
  - Dedicated serial queue for Whisper + Ollama: `celery -Q meeting_transcribe -c 1` (single-GPU hosts require this).
  - Cancellation: store `task_id` on `MeetingRecording`; DELETE meeting calls `task.revoke(terminate=True)` and sets a tombstone state on the recording. Each stage entry checks `Meeting.status != 'cancelled'` and raises `Ignore()` if cancelled.
  - Dead-letter queue: `task_reject_on_worker_lost=True` + `meeting_dead_letter` queue that writes `failure_reason` and triggers an alert.
  - Progress heartbeat: long-running transcription updates `MeetingRecording.progress_pct` every 30s so the UI rail (D4) can show movement.
  - Transient-error classification: network timeout / 503 from Ollama / Whisper GPU OOM → transient → retry. Unsupported codec / 4xx → permanent → fail fast.

## High Findings (CONFIRMED by both voices)

### H1. Duplicated sources of truth: Event + Meeting + mirror EventAttendee
Plan stores title/time on Event AND Meeting AND per-attendee mirror Event rows. Write amplification: 1 meeting × 20 attendees = 21 Events + 20 EventAttendees + 20 MeetingAttendees. On PATCH/reschedule/cancel, all 3 sources must be kept in sync. Drift is inevitable.
- **AUTO-DECISION (Mechanical, P5 explicit + P4 DRY)**: Drop attendee mirror events entirely. One canonical `Event` row per meeting (organizer-owned). Attendee calendar view is derived by JOIN on `EventAttendee`. The `MeetingAttendee` table has NO `event_id`. This saves 20 rows per meeting and eliminates sync bugs. Meeting keeps its own `event_id` (FK to the single canonical Event) for the organizer relationship. Availability query uses `EventAttendee JOIN Event` which is one query, not N queries.

### H2. PMS ACL refactor is not "split helper" — it's a route-by-route read/write matrix
Both voices independently audited `_ensure_project_access` callers. Binary readable/writable split would over-grant project metadata (list_issues, list_labels, list_statuses, templates, custom_fields, CSV export) to meeting attendees. The real fix needs THREE modes:
- **AUTO-DECISION (Mechanical, P1 + P5)**: Replace the binary split with three helpers:
  - `_ensure_project_member(user, project)` — project-scoped lists and metadata. Members only. NO fallback to IssueUserAccess.
  - `_ensure_issue_readable(user, issue)` — issue detail, comments, attachments (`router.py:2954`), custom field values (`:3740`). Falls back to IssueUserAccess where `access_level='read'`.
  - `_ensure_issue_writable(user, issue)` — issue edits, status changes, assignment changes. Members/editors only. NO fallback.
  
  Route-by-route audit (from Eng subagent, verified by Codex against the real file):

  | Line | Route / helper | Mode |
  |---|---|---|
  | 970 | `_ensure_project_owner` wrapper | `_ensure_project_member` |
  | 978 | `_ensure_project_editor` wrapper | `_ensure_project_member` |
  | 1454 | `_get_issue_for_user` | `_ensure_issue_readable` |
  | 1805 | GET `/projects/{id}` | `_ensure_project_member` |
  | 1865 | list_project_members | `_ensure_project_member` |
  | 1987 | list_milestones | `_ensure_project_member` |
  | 2070 | list_project_labels | `_ensure_project_member` |
  | 2164 | list_issues | `_ensure_project_member` **(NOT issue_readable — exclude from fallback)** |
  | 2954 | download_attachment | `_ensure_issue_readable` |
  | 3334 | list_project_statuses | `_ensure_project_member` |
  | 3473 | export_project_issues (CSV) | `_ensure_project_member` (writable-ish; leaks full project) |
  | 3560 | list_templates | `_ensure_project_member` |
  | 3656 | list_custom_fields | `_ensure_project_member` |
  | 3740 | list_issue_custom_field_values | `_ensure_issue_readable` |

  Only 3 sites fall back to IssueUserAccess: issue detail (1454), download_attachment (2954), and per-issue custom fields (3740). Everything else is members-only.

### H3. IssueUserAccess model is too thin
Plan: `id, issue_id, user_id, access_level, granted_by_meeting_id, granted_at`. Missing fields for proper lifecycle.
- **AUTO-DECISION (Mechanical, P1 completeness)**: Add:
  - `expires_at` (nullable, default = meeting end + 7 days) — auto-expire via daily beat task for least-privilege / GDPR posture
  - `revoked_at` (nullable) — soft delete for audit trail
  - `granted_by_user_id` — who added the issue to the meeting
  - `reason` enum (`meeting_attendee`, `explicit`, `inherited`) — future-proof non-meeting grants
  - Unique partial index `(issue_id, user_id) WHERE revoked_at IS NULL`
  - Index `(user_id, revoked_at)` for "what issues do I have read access to?" UI
  - Service-layer revocation (NOT FK cascade) so audit row is written on attendee removal

### H4. Docs share has no meeting provenance
Plan reuses `upsert_native_doc_user_share()` but that function doesn't know about meetings. Attendee removal can't clean up because there's no link back.
- **AUTO-DECISION (Mechanical, P1 completeness)**: Add a parallel `DocMeetingAccess` table: `(id, doc_item_id, user_id, granted_by_meeting_id, granted_by_user_id, expires_at, revoked_at)`. Permission check on Docs items does the same 3-mode fallback pattern as PMS. SpaceDoc stays member-only for MVP (SpaceDocUserShare is explicitly deferred to a post-MVP PR).

### H5. Impossible index: `EventAttendee(user_id, start_at)`
`start_at` is on Event, not EventAttendee. The index as described cannot exist.
- **AUTO-DECISION (Mechanical, P5 explicit)**: Use `EventAttendee(user_id, event_id)` + `Event(workspace_id, start_at, end_at)` + partial index `Event(workspace_id, start_at, end_at) WHERE cancelled_at IS NULL`. Hash join performs well at the expected volume. If production profiling later shows the join is a bottleneck, denormalize `start_at/end_at` onto EventAttendee with a service-layer sync (NOT a DB trigger — explicit over clever). Also add `Event(source_type, source_id)` for meeting ↔ event lookups during PATCH.

### H6. Conflict detection is stale — boolean `conflict_detected` contradicts D8 `conflict_count`
Plan has `MeetingAttendee.conflict_detected: bool` computed once on create. D8 design decision requires `conflict_count: int` with a tooltip listing conflicting titles. Also no recompute when OTHER meetings move into the same slot.
- **AUTO-DECISION (Mechanical, P1 completeness + P5 explicit)**:
  - Change `conflict_detected` (bool) → `conflict_count` (int, default 0) on MeetingAttendee.
  - Add a separate `MeetingAttendeeConflict` table: `(id, meeting_attendee_id, conflicting_event_id, detected_at)` — holds the actual list for the tooltip.
  - Sync detection runs inline on create/PATCH.
  - **New Celery task** `meeting.recompute_conflicts` triggered from any meetings PATCH commit: finds all meetings overlapping the new window that share attendees, updates their `conflict_count` + clears `seen_conflict_at`. Debounced 5s per meeting_id. Required to handle the "other meeting moved into my slot" case.

### H7. Test coverage gap (~4 budgeted, ~17 needed)
- **AUTO-DECISION (Mechanical, P1 + user engineering preferences "too many tests > too few")**: Expand the verification section with per-PR test checklist:
  - PR0 (Alembic bootstrap): migration smoke test, CI model-drift guard test.
  - PR1 (Meeting skeleton): meeting create transaction rollback test (force error at step 4), meeting CRUD contract tests, SubSidebar "+" event dispatch test (Vitest), Korean title truncation test.
  - PR2 (ACL + pickers): `_ensure_issue_readable` fallback test, `_ensure_issue_writable` rejection test (reader tries to write), attendee removal → revocation cascade test, project-metadata-not-granted test, TaskPicker keyboard nav test (Vitest).
  - PR3 (Recording + transcription): Celery retry test (mocked faster-whisper), Ollama timeout test, meeting-deleted-mid-job race test, large upload streaming test (100MB fixture), cleanup-safety integration test (verify `cleanup_orphan_media` does NOT delete meeting recordings), idempotency key test on duplicate upload.
  - PR4 (Calendar + rooms): availability query EXPLAIN assertion (n_attendees=20, 2 weeks), RRULE weekly expansion test, retroactive conflict recompute test (other meeting moves), cross-midnight event render test, Planner regression test after calendar-api swap.
  - PR5 (Polish): color-contrast audit snapshot, ICS golden file test, Home widget TZ boundary test, a11y smoke tests (VoiceOver + Pretendard).

### H8. Observability gap — plan mentions one metric
- **AUTO-DECISION (Mechanical, P1 completeness)**: Required metrics/alerts (added to verification section):

  | Metric | Type | Alert |
  |---|---|---|
  | `availability_query_duration_seconds{n_attendees}` | Histogram | p95 > 500ms |
  | `meeting_create_total{result}` | Counter | rollback rate > 1% |
  | `meeting_transcribe_queue_depth` | Gauge | > 50 |
  | `whisper_realtime_factor` (wall / audio duration) | Histogram | > 3.0 |
  | `ollama_latency_seconds`, `ollama_request_total{status}` | Histogram + Counter | 5xx > 2% |
  | `issue_user_access_grants_total{result}` | Counter | + audit log line |
  | `recording_upload_bytes`, `recording_upload_duration_seconds` | Histogram | — |
  | `minio_bucket_bytes_used{bucket}` | Gauge | > 90% |
  | `feature_flag_eval_total{flag,result}` | Counter | — |

  Structured JSON logs include `meeting_id`, `user_id`, `workspace_id` on every line for correlation.

## Medium Findings (CONFIRMED or single-voice)

- **M1 Feature flags for rollback** (single voice, Claude): Add `workspace_features.calendar.backend` flag so PR1 calendar-api swap can be rolled back without losing Planner. Auto-decide: YES, add to PR1 acceptance criteria.
- **M2 Presigned playback URLs** (single voice, Claude): Recording playback should use `presigned_get_object` with 1h TTL, not proxied download. Auto-decide: YES, PR3 acceptance criteria.
- **M3 Recording size cap misalignment** (single voice, Claude): Media router has 10MB cap; recording endpoint needs 1GB. Keep them separate — new endpoint, new cap. Auto-decide: YES.
- **M4 RRULE materialization** (single voice, Claude): v1 hard-caps RRULE to WEEKLY only. Availability query expands RRULE inline via CTE or pre-expanded `event_occurrences` view. Auto-decide: hard-cap WEEKLY in v1, defer materialization strategy to Phase 2 of the feature.
- **M5 Ad-hoc room dedup** (single voice, Claude): Partial unique index `(workspace_id, lower(name)) WHERE ad_hoc = true`. Auto-decide: YES.
- **M6 Idempotency key on recording upload** (single voice, Claude): Client pre-generates `recording_id`, POST uses it as idempotency key. Auto-decide: YES.
- **M7 Worker graceful shutdown** (single voice, Claude): `worker_graceful_shutdown_timeout = 1200` so in-flight transcription jobs survive worker upgrades. Auto-decide: YES.
- **M8 Whisper model / GPU capacity** (both voices touched): `large-v3` for Korean quality needs ~8GB VRAM; CPU fallback is 30–60min for a 60-min meeting. This is an ops/deployment decision that must be made before PR3. **TASTE DECISION** — surfaced at final gate.
- **M9 Summarization LLM choice** (Ollama gemma2:9b vs qwen2.5:14b vs llama3.1:8b vs existing internal LLM gateway): **TASTE DECISION** — surfaced at final gate.

## Architecture ASCII Diagram (Eng subagent, verified)

```
                       ┌────────────────────────┐
                       │  apps/web (React 19)   │
                       │  MeetingView / Planner │
                       └──────┬─────────┬───────┘
                              │         │
                   calendar-api         meeting-api
                              │         │
             ┌────────────────▼─────────▼────────────────┐
             │             FastAPI aidoo_api             │
             │                                            │
             │  ┌──────────┐      ┌───────────┐          │
             │  │ calendar │◄─────│  meeting  │          │
             │  │  domain  │ FK   │  domain   │          │
             │  │ Event    │      │ Meeting   │          │
             │  │ EventAtt │      │ MtgAtt    │          │
             │  └─────▲────┘      │ Room/Rec  │          │
             │        │           └─┬───┬───┬─┘          │
             │        │             │   │   │            │
             │        │   pms ◄─────┘   │   │            │
             │        │   (TaskLink +   │   │            │
             │        │    IssueUser    │   │            │
             │        │    Access)      │   │            │
             │        │                 │   │            │
             │        │   docs ◄────────┘   │            │
             │        │   (DocLink +        │            │
             │        │    DocMeetingAccess)│            │
             │        │                     │            │
             │        │   media ◄───────────┘            │
             │        │   (MediaFile resource_type=      │
             │        │    'meeting_recording')          │
             │        │                                  │
             │   planner (frontend) ─► calendar (writes) │
             └────┬───────────────────────────────────────┘
                  │ Celery chain(meeting.transcribe, meeting.summarize)
                  ▼
       ┌──────────────────────────────┐
       │ apps/worker (Celery)         │
       │ tasks/meeting.py:            │
       │   faster-whisper (large-v3)  │
       │   → Ollama / internal LLM    │
       │   → docs.create_native_doc   │
       │   → update MeetingRecording  │
       │   → link to PMS task         │
       └──────────────────────────────┘
```

## Phase 3 Status: **COMPLETE.** All findings auto-decided via 6 principles except two ops-level taste decisions (M8 Whisper host capacity, M9 summarization LLM choice) surfaced at final gate.

---

# AUTOPLAN REVIEW — Decision Audit Trail

<!-- AUTONOMOUS DECISION LOG -->

| # | Phase | Decision | Class | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO | Pause at premise gate (both voices reject premise) | User Challenge | N/A | Required human judgment on calendar stack + data policy | Auto-decide |
| 2 | CEO | Approach A (full Meeting app) kept after user clarified no existing calendar | User | N/A | User confirmed portal is first calendar, invalidating "duplicate of Outlook" concern | Approach B/C/D |
| 3 | CEO | Swap OpenAI API → faster-whisper + Ollama (on-prem) | Mechanical | P1+user constraint | Hard constraint from user: industrial data cannot leave cluster | Keep OpenAI |
| 4 | CEO | Reorder PRs: minutes pipeline earlier (PR1–PR3), calendar/rooms later (PR4–PR5) | Mechanical | P1+P6 | Both voices and user agree minutes is the highest-value piece; validate it first | Keep original order |
| 5 | Design | D1 Create modal field order: title → linked work → time → attendees → availability → room → save | Mechanical | P5 explicit | Both voices flagged schema-order hierarchy as serving developer not user | Schema order |
| 6 | Design | D2 Home widget follows HomeView row pattern, not cards, ABOVE Assigned | Mechanical | P5+P4 | Both voices confirmed, cards would drift from existing calm row rhythm | Cards/dashboard blocks |
| 7 | Design | D3 MeetingDetail hierarchy: title/status → linked work → active state → attendees → agenda → outputs → meta | Mechanical | P5 | Component inventory is not a layout; role-based ordering serves user | Inventory layout |
| 8 | Design | D4 Transcription progress rail visible on MeetingDetail + Home widget + PMS task | Mechanical | P1 | "Magical moment" invisible without discoverability path; both voices flagged | Hide inside Meeting |
| 9 | Design | D5 Conflict flow: amber inline banner + dynamic primary button label "겹쳐도 생성" | Mechanical | P5+P2 | Passive badge fails with allow_conflicts=True; both voices prescribe loud flow | Passive badge only |
| 10 | Design | D6 Accessibility moves from PR5 "polish" to each PR where feature ships | Mechanical | P1 completeness | Both voices flagged a11y-polish-PR as expensive rework; copy-pasting Planner's div cells is non-starter | Keep PR5 |
| 11 | Design | D7 Design system usage table: every new surface references tokens/classes/icons | Mechanical | P5 explicit | Prevents drift from PMS/Docs/Planner. Both voices flagged token vacuum | Freeform component spec |
| 12 | Design | D8 Edge case rules (30+ attendees, 200-char Korean, cross-midnight, archived task, etc.) | Mechanical | P1 | Both voices found all 8 edges unspecified; rules avoid two-implementer drift | Leave implementer to decide |
| 13 | Eng | C1 Add PR0 to bootstrap Alembic before PR1 | Mechanical | P1 | Plan's "Alembic migration" is unimplementable against current create_all codebase | Stay on create_all (additive only) |
| 14 | Eng | C2 New streaming `/meeting/recordings` endpoint + resource_type='meeting_recording' on MediaFile | Mechanical | P1 | 10MB cap + orphan cleanup silent delete = data loss | Reuse /media/upload |
| 15 | Eng | C3 Production Celery contract (acks_late, time limits, DLQ, cancellation, chain split, idempotency) | Mechanical | P1+P5 | First long-running job in repo; defaults will crash multi-hour transcription | Ship defaults |
| 16 | Eng | H1 Drop attendee mirror events; derive from single canonical Event | Mechanical | P5+P4 DRY | Write amplification + desync risk; mirror rows serve no query | Keep mirrors |
| 17 | Eng | H2 Three-mode ACL (member/readable/writable) not binary; route-by-route audit locked in | Mechanical | P1 | Binary split over-grants project metadata (security bug) | Binary readable/writable |
| 18 | Eng | H3 IssueUserAccess gets expires_at, revoked_at, granted_by_user_id, reason, unique partial index, service-layer revoke | Mechanical | P1 completeness | Audit/GDPR/revocation semantics missing | Thin model |
| 19 | Eng | H4 New DocMeetingAccess table for Docs meeting-provenance grants (SpaceDoc deferred) | Mechanical | P1 | Existing Native share lacks meeting provenance; revocation on attendee removal is wrong | Reuse existing share |
| 20 | Eng | H5 Fix impossible index: use `EventAttendee(user_id, event_id)` + `Event(workspace_id, start_at, end_at)` partial index | Mechanical | P5 | Original index cannot exist (start_at is not on EventAttendee) | Denormalize start_at (defer to profiling) |
| 21 | Eng | H6 Replace `conflict_detected` bool with `conflict_count` int + MeetingAttendeeConflict table + `meeting.recompute_conflicts` task | Mechanical | P1+P5 | Boolean can't support D8 tooltip; retroactive conflict case ignored | Keep boolean |
| 22 | Eng | H7 Per-PR test checklist (expand from 4 to 17+ flows) | Mechanical | P1+user pref | User engineering pref: "too many tests > too few" | Keep thin budget |
| 23 | Eng | H8 Observability: 9 metrics + structured logs with correlation IDs | Mechanical | P1 | Plan mentions one queue metric; no alerts, no correlation | Ship with minimal logging |
| 24 | Eng | M1–M7 (feature flag, presigned URL, size cap, RRULE weekly-only v1, room dedup, idempotency, graceful shutdown) | Mechanical | Various | All single-voice but clear right answers | — |
| 25 | Eng | M8 Whisper host capacity (GPU vs CPU) | **TASTE** | — | Ops/deployment decision; affects throughput and user wait time | Surfaced at final gate |
| 26 | Eng | M9 Summarization LLM choice (Ollama gemma2/qwen2.5/llama3.1 vs internal gateway) | **TASTE** | — | Quality vs. infra preference; user may have an internal gateway | Surfaced at final gate |

**Totals**: 26 decisions logged. 1 user challenge resolved. 23 mechanical auto-decisions. 2 taste decisions surfaced at final gate. 0 user challenges remaining.

---

# AUTOPLAN REVIEW — Pre-Gate Verification

## Phase 1 (CEO) outputs

- [x] Premise challenge with specific premises named (calendar stack, meeting pain, data policy, room booking, target user)
- [x] All applicable review sections have findings (premise, leverage map, scope, regret scenarios, competitive risk, alternatives)
- [x] Error & Rescue Registry: N/A at CEO level (moved to Eng phase observability/failure modes)
- [x] Failure Modes Registry: in Eng phase (10 production failure scenarios)
- [x] "NOT in scope" implicit via Approach A decision (deferred items: Microsoft Graph integration, discovery gate, Planner-first approach)
- [x] "What already exists" section written (verified leverage map)
- [x] Dream state delta: current (no calendar, no meetings, Planner stub) → plan → 12-month ideal (unified portal with minutes-first meeting workflow, PMS linkage, on-prem AI)
- [x] Completion Summary: CEO dual voices summary + consensus table
- [x] Dual voices ran (Claude subagent + Codex)
- [x] CEO consensus table produced
- [x] Premise gate passed (user decision 2026-04-10)

## Phase 2 (Design) outputs

- [x] All 7 dimensions evaluated with scores (both voices)
- [x] Issues identified and auto-decided (8 UI contracts D1–D8)
- [x] Dual voices ran (Claude subagent + Codex)
- [x] Design litmus scorecard produced
- [x] Missing states matrix produced (Claude subagent)
- [x] Edge case rules locked in (D8)

## Phase 3 (Eng) outputs

- [x] Scope challenge with actual code analysis (file paths + line numbers verified by both voices)
- [x] Architecture ASCII diagram produced
- [x] Test diagram mapping codepaths to test coverage (17 flows, PR-by-PR checklist)
- [x] Test plan artifact: inline in plan file (plan mode — external write disallowed, noted explicitly)
- [x] "NOT in scope" section: SpaceDocUserShare deferred post-MVP, RRULE daily/hourly deferred, Alembic-as-separate-PR0
- [x] "What already exists" section: existing media abstraction, Celery scaffolding, create_all schema management, PMS ACL helpers
- [x] Failure modes registry: 10 production scenarios enumerated
- [x] Completion Summary: 3 Critical + 8 High + 9 Medium findings
- [x] Dual voices ran (Claude subagent + Codex)
- [x] Eng consensus table produced
- [x] Decision audit trail complete (26 rows)

## Cross-phase themes

- [x] PMS ACL complexity (CEO + Eng independent)
- [x] Whisper/worker architecture (CEO + Eng independent)
- [x] Transcription wait UX (Design + Eng independent)

## Artifacts note (plan mode constraint)

The /autoplan skill normally writes a restore point file, a test plan artifact, and review log entries to `~/.gstack/projects/{slug}/`. Plan mode restricts writes to the plan file only, so all of those artifacts are inlined in this plan file instead. Once plan mode exits and implementation begins, the gstack-review-log bash calls from the autoplan skill can be run then to backfill the review history.

---

# AUTOPLAN REVIEW — Phase 4 Final Gate Resolution (user decision, 2026-04-10)

**User choice**: B) Accept all 23 mechanical auto-decisions, resolve M8/M9 at this gate.

**M8 Whisper host capacity — RESOLVED**:
- **Decision**: GPU host running `large-v3`, real-time ~1x factor.
- Worker host needs ≥8GB VRAM. Recommended: RTX 3060 12GB or better, or a cloud GPU instance if on-prem GPU is not available.
- Per-job expectation: 60-minute recording transcribes in 3–10 minutes wall time. UI progress rail (D4) shows movement every 30s via heartbeat.
- PR3 acceptance criteria: runs on the target GPU host, not CPU fallback. Ops task: provision GPU + install CUDA + verify `faster-whisper` can load `large-v3` before PR3 merges.

**M9 Summarization LLM — CONDITIONAL**:
- **First choice**: Route summarization through an existing internal LLM gateway if the AI team confirms one exists. This gives the best ops posture (single audit trail, cost centralization, one HTTP endpoint for the worker).
- **PR3 acceptance criteria first step**: Before writing the summarize task, PR3 author asks the AI team (or searches for internal LLM endpoint config) whether a production-ready Korean-capable internal LLM gateway exists.
- **Fallback if no internal gateway**: Ollama `qwen2.5:14b-instruct` running on the same GPU host as Whisper (shared VRAM budget: Whisper ~5GB + Ollama ~9GB → 16GB+ card needed, OR Whisper+Ollama serialized on the 12GB card with model unload between stages). Quantize to `Q4_K_M` (6GB) if memory is tight.
- **Plan requirement**: PR3 must record which path was taken in the PR description. If the internal gateway path is chosen, the worker config reads the endpoint from a settings variable so swapping later is trivial.

**All 26 decisions finalized**. No user challenges outstanding. Plan is ready for implementation.

---

# AUTOPLAN REVIEW — Final Summary

## Review Scores Recap

| Review | Voice | Initial Verdict | After Gate Resolution |
|---|---|---|---|
| CEO | Claude subagent | All 6 dimensions NO | 3/6 invalidated by user answers, 3/6 still valid → folded into Eng phase |
| CEO | Codex | All 6 dimensions NO | Same as above |
| Design | Claude subagent | 3.0/10 avg across 7 dimensions | 8 UI contracts (D1–D8) locked in |
| Design | Codex | "architecturally detailed but not a UX spec" | Same — fixed by D1–D8 |
| Eng | Claude subagent | 3 Critical + 10 High + 10 Med/Low | All auto-decided |
| Eng | Codex | 3 Critical + 6 High + 3 Medium (same Criticals as Claude) | All auto-decided |

## What This Plan Now Ships (post-review)

**PR0 (new, critical prerequisite)**: Alembic bootstrap. `alembic init`, baseline revision autogenerated from current `Base.metadata`, stamp head, CI model-drift guard, README for migration workflow.

**PR1: Meeting domain skeleton + list UI + AppBar**
- New backend domain `meeting/` (no calendar/events yet): `Meeting`, `MeetingAttendee` (no mirror event_id), `MeetingRoom`, `MeetingTaskLink`, `MeetingDocLink`, `MeetingNote`, `MeetingRecording` tables via Alembic migration.
- AppBar registration: `constants.ts`, `app-shell.ts`, `App.tsx`, `WorkspaceGate featureCode="nav.meeting"`, AI sidebar `meeting-minutes` rewired as deep link.
- MeetingView shell with List, Recordings, Rooms tabs (no Calendar tab yet — deferred to PR4). List shows meetings sorted by start time.
- MeetingCreateModal with field order per D1 (title → linked work → time → attendees → room → save row). @aidoo/ui Dialog component (not SchedulePopover). Save row has dynamic primary button text per D5.
- Accessibility per D6: modal focus trap + return, conflict banner as `role="alert"` with live region, Korean VoiceOver smoke test.
- `nav.meeting` feature flag seeded.
- Tests per H7: meeting create transaction rollback, CRUD contract, SubSidebar "+" event dispatch, title truncation.

**PR2: PMS task-level ACL + TaskPicker + DocPicker + Docs meeting-provenance**
- `IssueUserAccess` table with full field set from H3 (expires_at, revoked_at, granted_by_user_id, reason, unique partial index, service-layer revoke with audit row).
- `DocMeetingAccess` parallel table for Docs (H4). NativeDoc only — SpaceDocUserShare deferred to post-MVP.
- Three-mode ACL refactor per H2: `_ensure_project_member`, `_ensure_issue_readable`, `_ensure_issue_writable`. Route-by-route audit applied to all 15 call sites per the matrix in Phase 3 findings.
- TaskPickerModal with workspace-wide search endpoint (promoted from sub-bullet to explicit deliverable). DocPickerModal.
- Daily beat task `expire_meeting_acls` scans `IssueUserAccess.expires_at < now` and soft-deletes.
- Tests per H7: readable fallback, writable rejection, attendee removal → revocation cascade, project-metadata-not-granted, TaskPicker keyboard nav.

**PR3: Recording + on-prem transcription pipeline**
- Dedicated `POST /api/v1/meeting/recordings` endpoint with streaming MinIO multipart upload, 1 GB cap, `audio/*` content-type policy, idempotency key (client-generated recording_id), `MediaFile.resource_type='meeting_recording'` marker.
- Fix `cleanup_orphan_media` beat task (`apps/worker/.../tasks/media.py:50`) to exclude `resource_type='meeting_recording'` AND write a regression test.
- Worker tasks per C3 production contract: `meeting.transcribe` (faster-whisper `large-v3` on GPU) and `meeting.summarize` (internal LLM gateway if exists, else Ollama `qwen2.5:14b-instruct` fallback) chained via Celery `chain()`. Full retry/DLQ/cancellation/idempotency/heartbeat contract from C3.
- `meeting.recompute_conflicts` async task triggered from meeting PATCH commits (H6).
- Auto Docs generation via existing `createNativeDoc` + BlockNote block conversion. Doc titled `회의록: {meeting.title} ({YYYY-MM-DD})`. `MeetingDocLink` and `MeetingRecording.linked_doc_id` populated atomically.
- Presigned GET URL (1h TTL) for audio playback, not proxied download.
- Tests per H7: Celery retry, Ollama timeout, meeting-deleted-mid-job race, 100MB streaming upload, cleanup-safety regression, idempotency.

**PR4: Calendar + events + rooms + availability + MeetingCalendar**
- New `calendar/` backend domain: `Event`, `EventAttendee` (no start_at column — see H5), `POST /calendar/availability` batch endpoint.
- Fix index per H5: `EventAttendee(user_id, event_id)` + `Event(workspace_id, start_at, end_at) WHERE cancelled_at IS NULL` partial index + `Event(source_type, source_id)`.
- `MeetingCalendar` grid extracted from PlannerView into `components/views/PlannerView/CalendarGrid.tsx` shared component. This is NOT "extract and reuse" — it is a rewrite budgeted as the largest sub-task in PR4. Implementer owns:
  - **Data layer**: replace hardcoded `events = []` (PlannerView.tsx:176) with `calendar-api` hook, keyed by visible date range.
  - **Overlap/stack layout**: n-column interval-tree algorithm (GCal-style). Current `absolute top-1 left-1 right-1` (PlannerView.tsx:567) is broken for any 2 overlapping events.
  - **All-day / multi-day strip**: sticky row above the hour grid. Multi-day events span horizontally. Required for 종일 회의, 휴가, 출장.
  - **Now indicator**: horizontal line at current time on Week/Day, tick every 60s.
  - **Event drag-to-move / drag-to-resize**: Pointer Events (touch-compatible), snap to 30 min default.
  - **Event detail popover**: click existing event → read/edit popover with title, time, attendees, linked PMS/Docs chips, "Open meeting" deep-link. Separate from the create popover.
  - **Agenda/List view**: 4th view mode alongside Month/Week/Day. Linear list of upcoming events with empty state.
  - **Week starts Monday + ISO week numbers**: Korean business convention. Replace `PICKER_DAYS` (PlannerView.tsx:15) and `weekDates` calc (PlannerView.tsx:166-174). Sunday still rendered red.
  - **Korean timezone (KST)**: all date math through a single helper; no raw `new Date(y,m,d)` in the render path.
  - **Keyboard nav + ARIA grid per D6** (line 457): `button role="gridcell"`, arrow nav, Enter/Space, Esc, `:focus-visible`.
- **Unscheduled PMS tasks drawer + drag-to-schedule** (product differentiation — ClickUp/Motion/Notion Calendar parity, the one thing our PMS-native position gives us for free): right-side drawer lists current user's open PMS issues (missing `dueAt` or overdue). Drag onto grid → POSTs calendar event with `source_type='pms'`, `source_id=issue_id`. No new backend — uses existing PMS list API + calendar-api POST.
- **Calendar source toggles**: left mini-panel checkboxes (Meeting / PMS due / Focus / OOO / Personal) filter rendered events by `source_type`. Persist per-user in localStorage.
- **Mini date-picker density dots**: `DatePickerPopover` (PlannerView.tsx:94-131) shows a dot per date based on event count (0 / 1 / 2+).
- **Deferred to PR5 backlog unless PR4 has slack**: natural-language quick add, Cmd+K palette, copy/paste events, undo toast, working-hours shading, snap-granularity toggle, secondary TZ column, side-by-side user columns, focus/busy/OOO visual differentiation.
- Planner migrates to `calendar-api` (behind `workspace_features.calendar.backend` feature flag per M1).
- `MeetingCreateModal` gains drag-to-create from calendar grid (in addition to list "+" button from PR1).
- `AttendeePicker` now calls batch availability endpoint. `AvailabilityOverlay` renders per D1 spec (virtualized after 8 rows, aggregate header for larger groups).
- Meeting rooms admin (`hasSystemRole(user, 'admin')` gate) with table layout (not cards).
- `conflict_count` (int) replaces `conflict_detected` (bool) per H6. `MeetingAttendeeConflict` child table populated on save.
- RRULE hard-cap to WEEKLY per M4.
- Tests per H7: availability EXPLAIN assertion (20 attendees, 2 weeks), RRULE weekly expansion, retroactive conflict recompute, cross-midnight rendering, Planner regression behind flag.

**PR5: Home widget + conflict toast + ICS + audit + polish**
- "Today's Meetings" home widget per D2 (HomeView row pattern, above Assigned to me, 5 max + "전체 보기" link, loading/empty/error states).
- Conflict toast from portal login via `GET /meeting/meetings/mine/conflict-feed` (D5 copy).
- ICS export `GET /meeting/meetings/{id}.ics` with golden-file test.
- Audit logging for ACL grants, revocations, meeting creates/deletes via existing audit channel.
- Observability metrics from H8 (9 metrics, structured JSON logs, correlation IDs, alerts).
- Color-contrast audit across light/dark for all semantic colors. Dark mode parity check on every new surface.
- Korean VoiceOver final smoke tests.

## Verification End-to-End

1. **Alembic bootstrap smoke** (PR0): `alembic upgrade head` against clean database reproduces current schema; CI fails on undeclared model changes.
2. **Meeting create happy path** (PR1): Admin user creates meeting with title, time, 3 attendees, room → row appears in list → all attendees see it on /meeting → audit log entry written.
3. **ACL grant** (PR2): User A (project member) creates meeting linked to issue `INDUSTRIAL-123`, adds User B (no project access). B can GET `/pms/issues/INDUSTRIAL-123` → 200 (read-only), cannot GET `/pms/projects/INDUSTRIAL/issues` list → 403 (project metadata not granted). B's `IssueUserAccess.expires_at` set to meeting end + 7 days.
4. **On-prem transcription** (PR3): User uploads 60-min Korean WAV → job chains transcribe → summarize → Doc creation → PMS task link in ≤15 min wall time on GPU host → `linked_doc_id` populated → PMS task shows "회의록" badge → D4 progress rail was visible on Home, MeetingDetail, and PMS task throughout. Test: delete meeting mid-transcription → task revoked, no partial Doc.
5. **Availability + conflict + retroactive recompute** (PR4): A creates meeting 10–11am with B,C. B already has 10:30–11:30 → `conflict_count=1`. A moves a different meeting D to 10–11am with C → C's original meeting triggers async `meeting.recompute_conflicts` → C sees amber badge on next login.
6. **Home widget + conflict toast** (PR5): User with upcoming conflict logs in → amber toast fires once, dismissed on ack. Home widget shows 3 upcoming meetings with linked task chips. ICS export opens cleanly in a test calendar client.
7. **Cleanup safety regression** (every PR): `cleanup_orphan_media` beat task runs → meeting recordings with `resource_type='meeting_recording'` are NOT deleted even after 24h.
8. **Dark mode + a11y smoke** (every PR): every new surface passes 4.5:1 contrast in both modes; VoiceOver reads recording state transitions and conflict warnings.

---

**/autoplan status: DONE.** 26 decisions recorded. Plan is ready for implementation. Recommend `/ship` once Phase 0 (Alembic bootstrap, PR0) is ready to merge.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | /autoplan phase 1 | Strategy & scope | 2 (Claude + Codex) | DISAGREE → user resolved | Premise challenge passed after user confirmed no existing calendar; OpenAI swap forced; scope kept |
| Codex Review | /autoplan phase 1,2,3 | Independent 2nd opinion | 3 (CEO, Design, Eng) | Extensive agreement with Claude subagent | 3 Critical confirmed, 6 High confirmed, multiple medium |
| Design Review | /autoplan phase 2 | UI/UX gaps | 2 (Claude + Codex) | Confirmed 7/7 dimensions NO | 8 UI contracts D1–D8 locked |
| Eng Review | /autoplan phase 3 | Architecture & tests | 2 (Claude + Codex) | Confirmed 6/6 dimensions NO | 3 Critical (Alembic, media delete, Celery contract), 8 High, 9 Medium all auto-decided |

**VERDICT:** APPROVED — 26 decisions recorded in audit trail, all findings either auto-decided or resolved via user gate. Plan is implementation-ready starting with PR0 (Alembic bootstrap).



