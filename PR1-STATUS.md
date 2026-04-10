# PR1 진행 상태 — Meeting 도메인 스켈레톤 (검증/디버깅 단계)

> **새 세션 첫 메시지 예시**: "프로젝트 루트의 [PR1-STATUS.md](PR1-STATUS.md), [PR1-HANDOFF.md](PR1-HANDOFF.md), [PR0-RESULT.md](PR0-RESULT.md) 세 파일 읽고 PR1 검증/디버깅 이어서 진행해주세요."

작성일: 2026-04-10
모델: Claude Opus 4.6 (1M context)
이전 세션 요약: PR1 의 백엔드/프런트엔드 산출물 작성 → 자동화 검증 통과 → 사용자 피드백 두 번 (`참석자 검색 누락`, `다크모드 가독성`) 반영

## 1. 한 줄 요약

**PR1 산출물은 모두 작성됐고 자동화 검증 (pytest, typecheck, 마이그레이션 왕복) 은 모두 green 입니다. 원격 dev DB 에 마이그레이션도 적용 완료. 남은 작업은 브라우저로 사람 손 QA 와 사용자가 추가로 발견할 수 있는 디버깅 라운드입니다.**

## 2. 이번 세션이 할 일 (요청 받은 범위)

사용자 요청: "PR1 작업 상황 좀 더 체크하고 디버깅 할거야"

해석: 코드 추가가 아니라 **검증/QA/회귀 확인 + 사용자가 dev 서버 만지면서 발견하는 이슈 잡기** 가 주 작업. 새 기능 추가는 사용자 명시 요청이 있을 때만.

## 3. PR1 산출물 (이전 세션에서 완료)

### 백엔드 (`apps/api/`)

**신규 도메인 폴더** [apps/api/src/aidoo_api/domains/meeting/](apps/api/src/aidoo_api/domains/meeting/)
- `models.py` — 5개 SQLAlchemy 모델: Meeting, MeetingAttendee, MeetingTaskLink, MeetingDocLink, MeetingRecording
- `schemas.py` — Pydantic 요청/응답 (MeetingCreateRequest, MeetingDetail, MeetingListResponse, MeetingUserItem 등)
- `service.py` — 비즈니스 로직 (`create_meeting`, `update_meeting`, `delete_meeting`, `attach_task`, `attach_doc`, `list_meetings`, `_replace_attendees` 등)
- `permissions.py` — `ensure_meeting_organizer`, `ensure_issue_readable`, `ensure_doc_readable`
- `router.py` — REST 엔드포인트 (`/api/v1/meeting/meetings`, `/api/v1/meeting/users` 등)
- `__init__.py`

**Alembic 마이그레이션** [apps/api/alembic/versions/d8fe1ed8923a_add_meeting_tables.py](apps/api/alembic/versions/d8fe1ed8923a_add_meeting_tables.py)
- 5 CREATE TABLE 정확히. 다른 변경 0
- baseline `0b843a383b2b` 다음의 첫 실제 마이그레이션
- 로컬 docker 에서 upgrade → downgrade → upgrade 왕복 검증 완료
- **원격 dev DB (`14.39.166.163:37677/doowon_ai_portal_dev`) 에 적용 완료** — `alembic current` → `d8fe1ed8923a (head)`

**라우터 마운트와 시드**
- [apps/api/src/aidoo_api/app.py](apps/api/src/aidoo_api/app.py) — `meeting_router` include
- [apps/api/src/aidoo_api/domains/auth/access.py](apps/api/src/aidoo_api/domains/auth/access.py) — `meeting` 워크스페이스 + `nav.meeting` 정책 + `APP_FEATURE_CODES["meeting"] = "nav.meeting"`
- [apps/api/src/aidoo_api/core/db.py](apps/api/src/aidoo_api/core/db.py) — meeting 모델 import (init_db)
- [apps/api/alembic/env.py](apps/api/alembic/env.py) — meeting 모델 import (autogenerate)
- [apps/api/tests/conftest.py](apps/api/tests/conftest.py) — meeting 모델 import

**테스트** [apps/api/tests/test_meeting.py](apps/api/tests/test_meeting.py) — 9 케이스
1. `test_meeting_create_get_update_delete_happy_path`
2. `test_non_organizer_attendee_cannot_modify_meeting`
3. `test_attach_task_requires_issue_access`
4. `test_attach_task_returns_403_for_user_without_project_access`
5. `test_attach_doc_links_native_doc_to_meeting`
6. `test_meeting_create_rejects_invalid_time_range`
7. `test_user_without_meeting_workspace_access_is_blocked`
8. `test_meeting_user_search_returns_users_without_pms_access` ← 사용자 검색 회귀 가드
9. `test_meeting_update_changes_time_and_attendees` ← 회의 수정 회귀 가드

### 프런트엔드 (`apps/web/`)

**도메인 레이어** [apps/web/src/domains/meeting/](apps/web/src/domains/meeting/)
- `meeting-api.ts` — 모든 REST 호출 래퍼. `listMeetings`, `getMeeting`, `createMeeting`, `updateMeeting`, `deleteMeeting`, `attachTaskToMeeting`, `detachTaskFromMeeting`, `attachDocToMeeting`, `detachDocFromMeeting`, `listMeetingUsers`
- `meeting-permissions.ts` — `isOrganizer`, `canEditMeeting`

**MeetingView 컴포넌트** [apps/web/src/components/views/MeetingView/](apps/web/src/components/views/MeetingView/)
- `MeetingView.tsx` — 루트. 탭 (Upcoming / My Meetings / Recordings) + 리스트 영역 + 우측 detail 사이드패널 + create 모달 마운트. `meeting:create-event` window 이벤트 리스너로 SubSidebar 의 "+ Meeting" 액션 받음
- `MeetingList.tsx` — 회의 리스트 row (제목, 시간, 주최자, 상태 배지, 카운터)
- `MeetingCreateModal.tsx` — 새 회의 생성. 필드 순서는 design §D1 에 맞춰 (1) 제목 (2) 연결된 업무 (3) 시간 (4) 참석자 (5) 안건. 태스크/문서 첨부는 로컬 칩으로 모았다가 create 후 순차 attach
- `MeetingEditModal.tsx` — 회의 수정. 제목/시간/안건/참석자만 편집 (태스크/문서 첨부는 detail 패널에서 관리). 주최자 칩은 X 버튼 숨김
- `MeetingDetail.tsx` — 우측 패널. 헤더 + 연결된 태스크/문서/참석자 섹션 + 안건 + 삭제 푸터. 헤더에 연필 아이콘 (Edit) 버튼 추가됨
- `TaskPickerModal.tsx` — PMS 태스크 선택. `onPick` 은 full `PmsIssue` 객체를 전달
- `DocPickerModal.tsx` — Docs hub NativeDoc 선택. `onPick` 은 full `DocsHubItem` 객체를 전달

**AppBar/라우팅 등록**
- [apps/web/src/constants.ts](apps/web/src/constants.ts) — `ShellAppId`/`AppBarItem` 유니온에 `meeting` 추가, `APP_BAR_ITEMS` 에 Meeting 진입점 (Users 아이콘), `NAV_ITEMS` 에 meeting 카테고리 3개. AI 사이드바의 `meeting-minutes` 항목에 `path: '/meeting?tab=recordings'` 부착 (deep-link)
- [apps/web/src/app-shell.ts](apps/web/src/app-shell.ts) — `ShellAppId` + `FEATURE_BY_APP_ID` 에 `meeting: 'nav.meeting'` 추가, `/meeting/...` 경로 매칭 분기
- [apps/web/src/App.tsx](apps/web/src/App.tsx) — `<Route path="/meeting/*">` + `WorkspaceGate featureCode="nav.meeting"`, `MeetingView` import
- [apps/web/src/components/layout/AppBar.tsx](apps/web/src/components/layout/AppBar.tsx) — `featureByAppId` 에 meeting 추가
- [apps/web/src/components/layout/SubSidebar.tsx](apps/web/src/components/layout/SubSidebar.tsx) — "+" 드롭다운에 Meeting 아이템 + `meeting:create-event` 디스패치
- [apps/web/src/domains/auth/auth-api.ts](apps/web/src/domains/auth/auth-api.ts) — `FEATURE_TO_APP['nav.meeting'] = 'meeting'` 매핑

**다크 모드 글로벌 토큰** [packages/ui/styles.css](packages/ui/styles.css)
사용자 피드백 두 번 받아서 다음 토큰을 다크 모드에서 더 밝게 조정:

| 토큰 | Before | After |
|---|---|---|
| `--ui-color-accent` | `#3d47b8` | `#818cf8` (Tailwind indigo-400) |
| `--ui-color-accent-hover` | `#5662d4` | `#a5b4fc` (indigo-300) |
| `--ui-color-ink` | `#d5d6d7` | `#e8eaed` |
| `--ui-color-ink-muted` | `#9ca3af` | `#b8bdc7` |
| `--ui-color-ink-subtle` | `#6b7280` | `#9ca3af` |
| `--color-gray-500` (Tailwind, .dark scope) | gray-500 | gray-400 (`oklch(0.707 0.022 261.325)`) |
| `--color-gray-600` (Tailwind, .dark scope) | gray-600 | gray-400 |

마지막 두 줄은 Tailwind v4 의 그레이 팔레트를 `.dark` 셀렉터에서 직접 remap 한 것. 코드베이스에 `text-gray-500` 가 205곳, `text-gray-600` 이 70곳 가까이 있는데 대부분 `dark:` override 가 없어서 한 번에 잡았음. `bg-gray-500` / `border-gray-500` 6곳 (PMS status dot, gantt fallback, hover border) 도 함께 영향받지만 모두 장식적 용도라 회귀 위험 낮음.

## 4. 자동화 검증 결과 (이전 세션 마지막 시점)

| 항목 | 결과 |
|---|---|
| `pytest apps/api/tests/` | **51 passed** (기존 42 + 신규 9) |
| `pytest tests/test_meeting.py` | 9/9 passed |
| `alembic check` (로컬 docker) | 0 drift |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` (로컬 docker) | 성공 |
| 원격 dev DB `alembic current` | `d8fe1ed8923a (head)` |
| `pnpm nx typecheck web` | **12 사전 오류 그대로, 신규 0** |

신규 typecheck 오류가 없는 것이 핵심. 사전 12 개는 전부 main branch 에 이미 있던 것 (PMSView, SubSidebar, BoardView, admin-console, admin-permissions 등 PR1 와 무관한 widening/string|null 이슈).

## 5. 사람 손 QA — 아직 안 한 것 (이번 세션에서 확인 필요)

다음 시나리오들은 코드는 작성했지만 실제 브라우저로 클릭해보지 않았습니다. 새 세션에서 dev 서버 띄우고 확인해야 합니다.

**핵심 happy path**
- [ ] AppBar 에 Meeting 항목이 보이는지 (platform_admin 로그인)
- [ ] `/meeting` 라우트 진입 가능, 빈 상태에서 "예정된 회의가 없습니다" 표시
- [ ] "+ New Meeting" 클릭 → 모달 오픈 → 제목/시간 입력 → "회의 만들기" → 우측 detail 패널 자동 오픈
- [ ] CreateModal 의 "연결된 업무" 섹션에서 + 태스크 / + 문서 클릭 → 픽커 모달 → 선택 → 칩으로 회수
- [ ] 칩 X 버튼으로 연결 해제, 다시 추가 가능
- [ ] 회의 만든 직후 detail 패널의 연결된 태스크/문서 섹션에 정확히 표시되는지
- [ ] 참석자 검색 input 에 "pms" / 다른 이메일 일부 입력 → 서버측 검색 결과 노출 → 클릭 → 칩으로 추가
- [ ] 빈 input 에서 dropdown focus 시 "이름 또는 이메일을 입력하세요" 힌트만 (사용자 목록 노출 X)
- [ ] detail 패널의 연필 아이콘 → EditModal 오픈 → 제목/시간 변경 → 저장 → 즉시 detail 패널 갱신
- [ ] EditModal 에서 참석자 추가/제거, 주최자 제거 시도 (X 버튼이 없어야 함)
- [ ] detail 패널의 + 추가 (task/doc) 도 attach 후 즉시 반영
- [ ] 회의 삭제 → 확인 dialog → detail 패널 닫힘 + 리스트에서 사라짐

**권한 검증**
- [ ] 일반 사용자에게 meeting workspace binding 부여 → /meeting 진입 가능, 본인이 organizer 가 아닌 회의는 read-only (수정/삭제 버튼 안 보임)
- [ ] meeting workspace binding 없는 사용자 → /meeting 진입 시 403 (WorkspaceGate 의 AccessDeniedView)

**SubSidebar / Deep-link**
- [ ] /meeting 들어간 후 좌측 SubSidebar 가 meeting 카테고리 (Upcoming/My Meetings/Recordings) 노출
- [ ] SubSidebar "+" 드롭다운에 Meeting 아이템 보이고, 클릭 시 모달 트리거 (`meeting:create-event` 이벤트)
- [ ] AI 사이드바의 "회의록" 클릭 → /meeting?tab=recordings 로 이동, Recordings 탭이 활성

**다크 모드 가독성** (사용자가 사용성 보고했던 부분)
- [ ] Meeting 화면 전체에서 "+ 추가", 상태 배지 ("예정"), 라벨 텍스트가 충분히 밝게 보이는지
- [ ] **Planner 화면**: 캘린더 SUN/MON/TUE 헤더, 날짜 숫자, "Add Event" 버튼이 다크 모드에서 잘 보이는지
- [ ] **PMS 화면**: 라벨, 캡션, 사이드바 텍스트가 너무 밝거나 너무 어둡지 않은지
- [ ] **Docs 화면**: 마찬가지
- [ ] **Admin Console**: 마찬가지
- [ ] PMS 의 status dot (backlog 회색, gantt fallback) 이 미세하게 밝아진 것이 어색하지 않은지

**참석자 검색 보강 검증** (사용자 보고: "pms-member 가 검색 안된다")
- [ ] 어드민 콘솔에서 사용자 목록 확인. `pms-member@aidoo.local`, `pms-viewer@aidoo.local` 등 dev 시드 계정이 실제로 존재하는지
- [ ] 없다면 → `/auth/bootstrap-status` 가 localhost 에서 호출돼서 `ensure_dev_login_seed_data` 가 동작하는지 확인. `dev_admin_login_available` 이 false 면 환경변수 `DOOWON_API_ALLOW_DEV_ADMIN_LOGIN=1` 확인
- [ ] 있다면 → CreateModal 참석자 input 에 "pms" 입력 시 검색 결과에 실제로 잡히는지 (서버측 ILIKE 검색이라 잡혀야 함)

## 6. 알려진 잔재 / 미해결 사항

### 원격 dev DB 의 사전 드리프트 (PR1 무관, 운영팀 작업)
PR0-RESULT.md §미해결 사항 의 연장. PR1 마이그레이션 적용 후 `alembic check` 가 두 가지 잔재를 보고합니다.

1. **legacy `pms_docs` 테이블** — 모델/baseline 어디에도 없는 prototype 잔재. 운영팀이 백업 후 DROP
2. **`pms_user_doc_prefs` 의 stale 인덱스** — `ix_pms_user_doc_prefs_doc_id` (구) vs `ix_pms_user_doc_prefs_space_doc_id` (모델 정의). 컬럼 rename 이 PR0 이전에 진행되면서 인덱스 이름이 안 따라간 흔적

**둘 다 PR1 와 무관**하고 로컬 docker DB (baseline + d8fe1ed8923a) 에서는 drift 0 입니다. 새 세션에서 건드리지 말 것.

### 사전 typecheck 오류 12 개 (PR1 무관)
`pnpm nx typecheck web` 결과 12 개 오류가 main 시점부터 존재합니다. PR1 작업 시작 전 git stash 로 확인했음. 신규 0. 주요 위치:
- `src/app-shell.ts(137,31)` — `canShowAppChrome(item.appId)` 가 'home' 을 받음 (NavItem.appId widening)
- `src/App.tsx(127,23)` — FEATURE_BY_APP_ID indexer 'home' 누락
- `src/components/layout/SubSidebar.tsx(1318,54)` — PmsSpace 타입 mismatch
- `src/components/views/PMSView/BoardView.tsx(81,20)` — motion drag handler
- `src/components/views/PMSView/PMSView.tsx(194,27)` 등 — string|null 3건
- `src/domains/admin/admin-console.tsx` — Select disabled / NoticeTone 3건
- `src/domains/admin/admin-permissions.ts(13,54)` — string|literal mismatch

### 작업 트리에 PR1 와 무관한 사전 수정 4 개

**중요**: 이번 세션 시작 시점에 이미 작업 트리에 다음 4 개 파일이 modified 상태로 있었습니다. PR1 작업과 무관합니다.

```
M apps/api/src/aidoo_api/domains/admin/router.py  (+289 lines)
M apps/api/tests/test_health.py                   (+26 lines)
M apps/web/src/domains/admin/admin-api.ts         (+29 lines)
M apps/web/src/domains/admin/admin-console.tsx    (+253 lines)
```

마지막 commit (`6dbea8e`) 이후 누군가의 진행 중 작업으로 보임. **PR1 commit 만들 때 절대 stage 하지 말 것**. 사용자에게 "이 4 파일은 PR1 무관 사전 수정인데 어떻게 처리할까요?" 라고 명시 확인 받아야 함.

### 의도적으로 PR1 범위 밖
[PR1-HANDOFF.md §1](PR1-HANDOFF.md) 의 표 그대로:

- MeetingRoom, room_id FK → PR4
- Event 테이블, event_id FK on Meeting/Attendee → PR4
- `allow_conflicts`, conflict 감지 → PR4
- MeetingRecording **테이블은 포함**, 업로드 라우트 + 워커는 PR3
- `IssueUserAccess` 폴백 → PR2 (PR1 의 task 첨부는 권한 없으면 단순 403)
- 캘린더 그리드, AvailabilityOverlay → PR4
- 홈 위젯, 충돌 토스트, ICS export, RRULE → PR5

### 의도적인 단순화 두 가지 (PR1 범위 안에서)

1. **MeetingDocLink 의 doc 권한 폴백** — 현재 owner-only. NativeDocUserShare/SpaceDoc 폴백은 PR2 와 함께 처리
2. **Meeting workspace_id 출처** — 요청 본문에서 받지 않고 `key='meeting'` 워크스페이스를 자동 조회. platform_admin 은 자동 노출, 일반 사용자는 admin UI 에서 binding 필요

### 디자인 §D1 ~ §D8 중 PR1 에 미반영된 것

[MEETING-APP-PLAN.md](MEETING-APP-PLAN.md) Phase 2 design review 의 결정 사항 중:

- **D2 홈 위젯 "Today's Meetings"** — PR5 로 미룸
- **D3 MeetingDetail 의 hero 영역** (linked work row, active state hero) — PR1 은 단순한 섹션 분리만, hero row 는 PR2/3 에서
- **D4 transcription progress rail** — PR3 (녹음 워커) 와 함께
- **D5 충돌 경고** — PR4 와 함께
- **D6 a11y 확장** — PR1 은 modal focus + role="alert" 정도만

## 7. 새 세션 첫 작업 추천 순서

```
1. 이 문서 + PR1-HANDOFF.md + PR0-RESULT.md 읽기 (자급자족)

2. git status 로 작업 트리 상태 확인. §6 의 사전 수정 4 개가 그대로 남아있는지 확인

3. 자동화 검증 한 번 더 돌려서 base line 확인:
   cd apps/api && uv run --python 3.12 --group dev pytest
   pnpm nx typecheck web

4. 사용자에게 dev 서버 띄워달라고 요청 + §5 의 QA 체크리스트 함께 진행
   - 해피 패스부터 시작
   - 발견한 이슈는 todolist 에 즉시 등록
   - 한 이슈 고치고 → 회귀 테스트 추가하고 → 다음 이슈

5. 이슈 발견 시 우선순위:
   (1) 회귀 (PR1 작업이 기존 화면 깨뜨림) — 즉시 fix + 회귀 테스트
   (2) Happy path 가 동작 안 함 — 즉시 fix + 회귀 테스트
   (3) UX 디테일 (다크모드 톤, 정렬, 라벨 등) — 사용자 합의 후 fix
   (4) 디자인 §D 중 PR1 에 빠진 것 — 사용자가 명시 요청할 때만 추가

6. 매번 작은 단위 commit (사용자 명시 요청 시에만)
```

## 8. 빠른 명령어 cheatsheet

```bash
# 백엔드 테스트
cd apps/api && uv run --python 3.12 --group dev pytest                # 전체
cd apps/api && uv run --python 3.12 --group dev pytest tests/test_meeting.py -x  # meeting 만

# 백엔드 dev 서버
pnpm nx dev api

# 프런트엔드 dev 서버
pnpm nx dev web

# 타입체크
pnpm nx typecheck web

# 마이그레이션 상태 확인 (원격 dev DB)
cd apps/api && uv run --python 3.12 alembic current
cd apps/api && uv run --python 3.12 alembic check

# 새 마이그레이션 만들 일 생기면 (이번 세션은 안 만들 가능성 높음)
cd apps/api && uv run --python 3.12 alembic revision --autogenerate -m "..."
```

## 9. 디버깅에 자주 쓸 위치

### 백엔드
- 회의 생성/수정 로직: [apps/api/src/aidoo_api/domains/meeting/service.py](apps/api/src/aidoo_api/domains/meeting/service.py)
- 권한 검사: [apps/api/src/aidoo_api/domains/meeting/permissions.py](apps/api/src/aidoo_api/domains/meeting/permissions.py)
- 라우터 + 사용자 검색: [apps/api/src/aidoo_api/domains/meeting/router.py](apps/api/src/aidoo_api/domains/meeting/router.py)
- 워크스페이스/feature 시드: [apps/api/src/aidoo_api/domains/auth/access.py](apps/api/src/aidoo_api/domains/auth/access.py) (DEFAULT_WORKSPACES, DEFAULT_FEATURE_POLICIES)

### 프런트엔드
- API 호출: [apps/web/src/domains/meeting/meeting-api.ts](apps/web/src/domains/meeting/meeting-api.ts)
- Create modal (linked work + 참석자 검색 로직): [apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx](apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx)
- Edit modal: [apps/web/src/components/views/MeetingView/MeetingEditModal.tsx](apps/web/src/components/views/MeetingView/MeetingEditModal.tsx)
- Detail 패널 + edit 진입: [apps/web/src/components/views/MeetingView/MeetingDetail.tsx](apps/web/src/components/views/MeetingView/MeetingDetail.tsx)
- 다크 모드 토큰: [packages/ui/styles.css](packages/ui/styles.css) `.dark` 블록

## 10. 사용자 선호 (이전 세션에서 확인)

- **한국어 응답**
- 원격/공유 인프라 (dev DB, prod 등) 에 쓰기 전 **명시 승인** 요구. 멋대로 진행하지 말 것
- 작업 도중 결정/상태 변화는 즉시 작업 파일 (이 문서, PR0-RESULT.md 등) 에 기록. 메모리 시스템 X, 프로젝트 루트 임시 파일 O
- 백엔드 변경은 테스트로 검증한 뒤 보고
- 디자인/UX 결정은 정답이 명확하지 않으면 옵션 제시 후 합의
- 글로벌 토큰/디자인 시스템 변경처럼 영향 범위 넓은 작업은 별도 PR 권장 — 이번 다크 모드 토큰 작업처럼 사용자가 명시 요청한 경우는 OK
- raw Tailwind 색상 (`bg-red-500` 등) 새 컴포넌트에 쓰지 말 것 — `--ui-color-warning/danger/success` 토큰 사용

## 11. 절대 하지 말 것

- ❌ §6 의 사전 수정 4 파일을 PR1 commit 에 stage
- ❌ 원격 dev DB 의 legacy `pms_docs` 테이블 / stale 인덱스를 임의로 손댐 — 운영팀 작업
- ❌ 사용자 승인 없이 prod 환경 손댐, force-push, hook 우회
- ❌ `_apply_postgres_schema_compat()` 류 손제작 SQL 부활
- ❌ `Base.metadata.create_all()` 호출 추가
- ❌ prod 환경에서 `DOOWON_API_AUTO_MIGRATE=1` 사용
- ❌ 테스트 conftest 가 원격 DB 에 붙도록 변경
- ❌ PR1 범위 밖 항목 추가 (rooms, calendar grid, conflict detection, transcription worker)

## 12. 참조

| 무엇 | 어디 |
|---|---|
| PR1 의 원본 인계 (스펙) | [PR1-HANDOFF.md](PR1-HANDOFF.md) |
| PR0 결과 + Alembic 인프라 상태 | [PR0-RESULT.md](PR0-RESULT.md) |
| 전체 plan (Phase 0-3 결정 기록) | [MEETING-APP-PLAN.md](MEETING-APP-PLAN.md) |
| Alembic 워크플로 | [apps/api/README.md](apps/api/README.md) "데이터베이스 마이그레이션" 섹션 |
| 원격 DB DSN | [.env](.env) `DOOWON_POSTGRES_DSN` |
| FastAPI app composition | [apps/api/src/aidoo_api/app.py](apps/api/src/aidoo_api/app.py) |
| 디자인 토큰 단일 소스 | [packages/ui/styles.css](packages/ui/styles.css) |
