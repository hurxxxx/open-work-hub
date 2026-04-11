# PR1 인계 — Meeting 도메인 스켈레톤

> 이 문서는 **PR1 착수 시점 handoff 원본**이다. 현행 상태나 다음 작업을 잡을 때는 [PR1-STATUS.md](PR1-STATUS.md) 와 [TODO-PLAN.md](TODO-PLAN.md) 를 먼저 보고, 이 문서는 PR1 범위/원 설계 확인용으로만 사용한다.

> **새 세션 첫 메시지 예시**: "프로젝트 루트의 [PR1-STATUS.md](PR1-STATUS.md), [TODO-PLAN.md](TODO-PLAN.md), [PR1-HANDOFF.md](PR1-HANDOFF.md) 읽고 현재 head 기준으로 이어서 진행해주세요."

> 주의: 아래 경로/권한 설명은 **PR1 당시 기준**이다. 현재 main 에서는 `/w/:workspaceSlug/<app>` 경로 체계와 workspace `enabled_apps` 모델이 추가로 반영돼 있다.

## 0. 프로젝트 한 줄 컨텍스트

Doowon AI Portal 은 Nx 모노레포다. React 19 + Router v7 프런트 (`apps/web`), FastAPI 백엔드 (`apps/api`, 패키지명 `aidoo_api`), 잡 워커 (`apps/worker`). 회사 내부 직원용 포털이며 PMS/Docs 도메인이 이미 백엔드에 있고, Meeting 앱을 5개 PR 에 걸쳐 신규 도입 중.

## 1. PR1 이 뭔가

[MEETING-APP-PLAN.md](MEETING-APP-PLAN.md) line 323 (Phase 1 reorder 결정) 인용:

> **PR1**: `meeting` 도메인 스켈레톤 (Meeting, MeetingAttendee, MeetingTaskLink, MeetingDocLink, MeetingRecording 테이블), AppBar 등록, MeetingView list + create modal (calendar grid 없음), TaskPickerModal, DocPickerModal, AI sidebar deep-link 재연결.

핵심: **"meeting minutes → PMS task / Docs 연결" 의 첫 슬라이스**. calendar grid, rooms, 충돌 감지, 녹음/전사는 전부 PR3-4 로 미뤄져 있음. PR1 은 회의 메타데이터를 만들고 거기에 Task/Doc 을 첨부할 수 있는 정도까지만.

### 백엔드 산출물

- 새 도메인 폴더: `apps/api/src/aidoo_api/domains/meeting/{__init__.py, models.py, router.py, schemas.py, service.py, permissions.py}`
- 5개 SQLAlchemy 모델 (아래 §4 참조)
- Alembic 마이그레이션 1개 — `alembic revision --autogenerate -m "add_meeting_tables"`. **PR0 이후 첫 실제 마이그레이션이라 milestone 의미가 있음**
- REST 엔드포인트:
  - `GET /api/v1/meeting/meetings?scope=mine|upcoming&from=&to=` — 리스트
  - `POST /api/v1/meeting/meetings` — 생성 (트랜잭션: Meeting + MeetingAttendee 행들)
  - `GET /api/v1/meeting/meetings/{id}` — 상세
  - `PATCH /api/v1/meeting/meetings/{id}` — 수정 (참석자 추가/제거 포함)
  - `POST /api/v1/meeting/meetings/{id}/tasks` / `DELETE .../tasks/{issue_id}` — 태스크 첨부/제거
  - `POST /api/v1/meeting/meetings/{id}/docs` / `DELETE .../docs/{doc_item_id}` — Doc 첨부/제거
- workspace feature flag: `nav.meeting` 시드 추가 (`apps/api/src/aidoo_api/domains/auth/access.py` 의 seed 확장)
- 권한: organizer 만 수정/삭제, 참석자는 read. PMS task 첨부 시 task 권한 검증 (`_ensure_issue_readable` 류 — **단, IssueUserAccess 폴백은 PR2 작업이므로 PR1 에서는 권한 없으면 단순 403**)

### 프런트엔드 산출물

- AppBar 등록 3군데:
  - [apps/web/src/constants.ts:44,49,55](apps/web/src/constants.ts#L44) — `ShellAppId` 유니온, `APP_BAR_ITEMS`, `NAV_ITEMS` 에 `meeting` 추가
  - [apps/web/src/app-shell.ts:4,11](apps/web/src/app-shell.ts#L4) — `ShellAppId` 유니온, `FEATURE_BY_APP_ID` 에 `meeting: 'nav.meeting'`
  - [apps/web/src/App.tsx:199-242](apps/web/src/App.tsx#L199) — `<Route path="/meeting/*" element={<WorkspaceGate featureCode="nav.meeting"><MeetingView /></WorkspaceGate>} />`
- 도메인 레이어: `apps/web/src/domains/meeting/{meeting-api.ts, meeting-permissions.ts}`
- 메인 뷰: `apps/web/src/components/views/MeetingView/{MeetingView.tsx, MeetingList.tsx, MeetingCreateModal.tsx, TaskPickerModal.tsx, DocPickerModal.tsx, MeetingDetail.tsx}`
- AI 사이드바의 기존 `meeting-minutes` 항목 경로를 `/meeting?tab=recordings` 로 deep-link 변경 (현재는 placeholder)
- SubSidebar "+" 드롭다운 (최근 커밋 `5ecdd05` 에서 추가됨) 에 "New Meeting" 항목

### 명시적으로 PR1 범위 밖

| 항목 | 어느 PR | 이유 |
|---|---|---|
| `MeetingRoom` 모델, room_id FK | PR4 | room booking 은 calendar 와 함께 |
| `Event` 테이블, `event_id` FK on Meeting/Attendee | PR4 | shared calendar 는 PR4 의 calendar 도메인 |
| `allow_conflicts`, `conflict_detected`, `seen_conflict_at` 필드 | PR4 | 충돌 감지 자체가 PR4 |
| `MeetingRecording` 의 transcription 워커 (faster-whisper, Ollama) | PR3 | 단, **테이블 자체는 PR1 에 포함**. status 컬럼은 default 'pending' 으로 두고 워커는 PR3 가 채움 |
| `IssueUserAccess` 폴백 권한 | PR2 | PR1 은 권한 없으면 그냥 403 반환 |
| 캘린더 그리드 (`MeetingCalendar`), AvailabilityOverlay, AttendeePicker 가용성 표시 | PR4 | calendar 의존 |
| 홈 위젯 "Today's Meetings", 충돌 토스트, ICS export, RRULE | PR5 | finishing 작업 |

## 2. 이미 돼있는 것 (PR0 산출물)

자세한 건 [PR0-RESULT.md](PR0-RESULT.md). 핵심만:

- **Alembic 인프라가 셋업돼 있다.** `apps/api/alembic.ini` + `apps/api/alembic/env.py` + baseline `0b843a383b2b_baseline_2026_04_10`
- **원격 dev DB (`14.39.166.163:37677/doowon_ai_portal_dev`) 는 baseline 으로 stamp 돼 있다.** `alembic current` → `0b843a383b2b (head)`
- **PR0 이후 첫 마이그레이션**: PR1 의 5개 Meeting 테이블 + feature_policies 시드 변경 (있다면)
- `init_db()` 는 더 이상 `create_all()` 을 부르지 않음. `DOOWON_API_AUTO_MIGRATE=1` 일 때만 `alembic upgrade head` 호출. **prod 에서는 절대 이 플래그 켜지 말 것**
- 테스트는 ephemeral Docker postgres 를 씀 (`apps/api/tests/conftest.py` 의 `postgres_dsn` 픽스처). Docker Desktop 켜져있어야 동작
- 모델 드리프트 가드: `apps/api/tests/test_alembic_migrations.py` 가 매 테스트 실행마다 `alembic check` 를 돌려, 모델만 바꾸고 마이그레이션을 깜빡한 PR 을 빨갛게 만듦

## 3. 작업 순서 제안

```
1. 도메인 폴더 생성
   apps/api/src/aidoo_api/domains/meeting/{__init__.py, models.py, schemas.py, router.py, service.py, permissions.py}

2. 5개 SQLAlchemy 모델 작성 (아래 §4 스키마)

3. apps/api/src/aidoo_api/core/db.py 의 init_db() 에 meeting 모델 import 추가
   apps/api/alembic/env.py 에도 import 추가 (autogenerate 가 메타데이터 인지하도록)

4. 마이그레이션 생성 + 검토
   cd apps/api
   uv run --python 3.12 alembic revision --autogenerate -m "add_meeting_tables"
   # 생성된 파일을 손으로 열어서:
   # - 5개 CREATE TABLE 만 들어있는지 확인 (다른 변경이 잡혔다면 모델 드리프트가 있다는 뜻 → 원인 추적)
   # - FK 순서, 인덱스 이름, nullable 기본값 점검
   # - downgrade() 가 올바른 역순인지 확인

5. 로컬 검증 — 일회용 Docker postgres 띄워서 upgrade head + downgrade 한 번 왕복
   docker run --rm -d --name pr1-check -e POSTGRES_USER=u -e POSTGRES_PASSWORD=p -e POSTGRES_DB=d -p 55432:5432 postgres:18
   DOOWON_POSTGRES_DSN=postgresql+psycopg://u:p@127.0.0.1:55432/d uv run --python 3.12 alembic upgrade head
   DOOWON_POSTGRES_DSN=postgresql+psycopg://u:p@127.0.0.1:55432/d uv run --python 3.12 alembic downgrade base
   DOOWON_POSTGRES_DSN=postgresql+psycopg://u:p@127.0.0.1:55432/d uv run --python 3.12 alembic upgrade head
   DOOWON_POSTGRES_DSN=postgresql+psycopg://u:p@127.0.0.1:55432/d uv run --python 3.12 alembic check
   docker rm -f pr1-check

6. 백엔드 라우터/서비스/스키마 작성

7. 백엔드 테스트 — apps/api/tests/test_meeting.py 신규
   - 생성/조회/수정/삭제 happy path
   - organizer 가 아닌 사용자의 수정 시도 → 403
   - 태스크 첨부 시 task 권한 검증
   - test_alembic_migrations.py 의 drift guard 가 통과해야 함

8. pytest apps/api/tests/ 전부 통과 확인

9. 원격 dev DB 에 마이그레이션 적용 (사용자 승인 후)
   cd apps/api
   uv run --python 3.12 alembic upgrade head
   uv run --python 3.12 alembic current  # 새 리비전이 head 로 표시되는지 확인

10. 프런트엔드 작업
    - constants.ts, app-shell.ts, App.tsx 3군데 수정
    - domains/meeting/ 도메인 레이어
    - components/views/MeetingView/ 컴포넌트들
    - 디자인 토큰: app-text-*, card, sidebar-submenu-*, --ui-color-warning/danger/success 사용
      (raw Tailwind red-500 같은 거 쓰지 말 것 — plan line 363 디자인 시스템 드리프트 경고)

11. pnpm -w vitest run apps/web/src/domains/meeting (있다면)
    pnpm -w typecheck (전체)

12. 커밋 → 푸시 → PR
```

## 4. 모델 스키마 (PR1 확정안)

### Meeting

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | `String(36)` PK | uuid |
| `workspace_id` | `String(36)` FK→workspaces.id, indexed | |
| `organizer_id` | `String(36)` FK→users.id, indexed | |
| `title` | `String(200)` | |
| `agenda` | `Text` default `''` | nullable=False |
| `start_at` | `DateTime` | |
| `end_at` | `DateTime` | |
| `status` | `String(24)` default `'scheduled'`, indexed | `scheduled / in_progress / completed / cancelled` |
| `created_at` | `DateTime` default utcnow_naive | |
| `updated_at` | `DateTime` default+onupdate utcnow_naive | |

**의도적 제외 (PR4 에서 추가)**: `room_id`, `event_id`, `allow_conflicts`. 이렇게 하면 PR4 가 ALTER TABLE ADD COLUMN 으로 깔끔히 확장 가능.

### MeetingAttendee

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | `String(36)` PK | |
| `meeting_id` | `String(36)` FK→meetings.id, indexed | |
| `user_id` | `String(36)` FK→users.id, indexed | |
| `role` | `String(24)` default `'required'` | `required / optional` |
| `response` | `String(24)` default `'pending'` | `pending / accepted / declined / tentative` |
| `created_at` | `DateTime` default utcnow_naive | |

`UniqueConstraint('meeting_id', 'user_id', name='uq_meeting_attendee')`

**의도적 제외**: `event_id`, `conflict_detected`, `seen_conflict_at`.

### MeetingTaskLink

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | `String(36)` PK | |
| `meeting_id` | `String(36)` FK→meetings.id, indexed | |
| `issue_id` | `String(36)` FK→pms_issues.id, indexed | |
| `added_by_id` | `String(36)` FK→users.id | |
| `created_at` | `DateTime` default utcnow_naive | |

`UniqueConstraint('meeting_id', 'issue_id', name='uq_meeting_task_link')`

### MeetingDocLink

**결정 필요**: doc 참조 방식. 두 옵션:

- **(a) NativeDoc 직접 FK**: `doc_id String(36) FK→docs_native_docs.id`. 단순. SpaceDoc 은 PR2 결정사항.
- **(b) Polymorphic**: `source_type String(24)` + `source_doc_id String(36)`. `apps/api/src/aidoo_api/domains/docs/models.py` 의 `DocsUserItemPref` 가 이미 이 패턴을 씀. 양쪽 다 첨부 가능하지만 FK 무결성 약함.

**권장**: (a). PR1 은 NativeDoc 만 지원, plan §2 line 65 의 SpaceDoc share 결정은 PR2 로 미뤄져 있음. 단순함이 우선.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | `String(36)` PK | |
| `meeting_id` | `String(36)` FK→meetings.id, indexed | |
| `doc_id` | `String(36)` FK→docs_native_docs.id, indexed | |
| `added_by_id` | `String(36)` FK→users.id | |
| `created_at` | `DateTime` default utcnow_naive | |

`UniqueConstraint('meeting_id', 'doc_id', name='uq_meeting_doc_link')`

### MeetingRecording

테이블은 PR1 에 포함하되, 업로드 엔드포인트와 워커는 PR3.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | `String(36)` PK | |
| `meeting_id` | `String(36)` FK→meetings.id, indexed | |
| `storage_key` | `String(512)` unique | media 도메인의 키 |
| `duration_sec` | `Integer` nullable | |
| `uploaded_by_id` | `String(36)` FK→users.id | |
| `source` | `String(16)` default `'upload'` | `upload / live` |
| `transcription_status` | `String(24)` default `'pending'`, indexed | `pending / transcribing / summarizing / done / failed` |
| `transcript_text` | `Text` nullable | PR3 가 채움 |
| `summary_text` | `Text` nullable | PR3 가 채움 |
| `failure_reason` | `String(255)` nullable | |
| `linked_doc_id` | `String(36)` FK→docs_native_docs.id, nullable | PR3 가 채움 |
| `created_at` | `DateTime` default utcnow_naive | |

기존 `apps/api/src/aidoo_api/domains/auth/models.py` 의 `utcnow_naive()` 와 `apps/api/src/aidoo_api/domains/pms/models.py` 의 패턴을 그대로 따라가면 됨.

## 5. 결정해야 할 것 (recommended defaults 와 함께)

| 결정 | 권장 | 이유 |
|---|---|---|
| Doc 참조 방식 | NativeDoc 직접 FK | §4 MeetingDocLink 참조 |
| Meeting `agenda` 가 nullable=True 인지 default `''` 인지 | default `''` (nullable=False) | 기존 PMS Issue.description 패턴과 일치 |
| Recording 테이블 PR1 포함 여부 | 포함 | PR3 가 ALTER TABLE 로 컬럼만 추가하는 것보다 처음부터 풀스키마가 깔끔. 단 업로드 엔드포인트는 PR3 |
| `IssueUserAccess` 폴백 | PR1 에서 안 함 | PR2 의 본 작업. PR1 의 task 첨부는 권한 없으면 403 |
| feature flag 시드 | `nav.meeting` 추가, default enabled | 기존 nav.\* 패턴 따라감 |
| 마이그레이션 파일명 | `add_meeting_tables` | PR0 baseline 다음의 첫 실제 마이그레이션 |

이 결정들이 사용자 의도와 다르면 작업 시작 전에 확인 받을 것. 특히 Recording 테이블 PR1 포함 여부는 한 번 더 사용자에게 확인 권장.

## 6. 검증 체크리스트

작업 끝나기 전 다음이 모두 통과해야 함:

- [ ] `pytest apps/api/tests/` 전부 green (드리프트 가드 포함)
- [ ] `alembic check` 0 drift
- [ ] `alembic upgrade head` + `alembic downgrade base` + `alembic upgrade head` 왕복 성공
- [ ] 새 마이그레이션 파일이 5개 CREATE TABLE + 인덱스/제약만 포함 (다른 변경 0)
- [ ] 원격 dev DB 가 새 head 리비전으로 업그레이드됨 (사용자 승인 후 적용)
- [ ] `pnpm -w typecheck` (web 사이드 작업이 들어가면)
- [ ] AppBar 에 Meeting 항목이 보이고 `/meeting` 접근 가능
- [ ] Meeting 생성 → Task 첨부 → Doc 첨부 → 상세 조회 의 happy path 가 UI 로 동작

## 7. 절대 하지 말 것

- ❌ `_apply_postgres_schema_compat()` 같은 손제작 SQL 추가. 모든 스키마 변경은 alembic 마이그레이션
- ❌ `Base.metadata.create_all()` 호출 추가. PR0 에서 의도적으로 제거됨
- ❌ prod 환경에서 `DOOWON_API_AUTO_MIGRATE=1` 사용
- ❌ 테스트 conftest 가 원격 DB 에 붙도록 변경. 테스트는 schema drop/recreate 를 반복하므로 ephemeral docker 만
- ❌ legacy `pms_docs` 테이블 (PR0-RESULT.md §미해결 참조) 을 모델로 부활시키기
- ❌ raw Tailwind 색상 (`bg-red-500` 등) 을 새 컴포넌트에 사용. `--ui-color-warning/danger/success` 토큰 사용
- ❌ PR1 범위 밖 항목 추가 (rooms, calendar grid, conflict detection, transcription worker). plan 의 §1 표 참조
- ❌ 운영팀 승인 없이 원격 dev DB 에 마이그레이션 적용. 사용자에게 명시 확인

## 8. 참조 위치

| 무엇 | 어디 |
|---|---|
| 전체 plan (Phase 0-3 결정 기록) | [MEETING-APP-PLAN.md](MEETING-APP-PLAN.md) |
| PR1 정의 | MEETING-APP-PLAN.md line 323 |
| 풀스펙 모델 (PR4 까지의 종합) | MEETING-APP-PLAN.md line 33-42 |
| Alembic 워크플로 가이드 | [apps/api/README.md](apps/api/README.md) "데이터베이스 마이그레이션" 섹션 |
| PR0 산출물과 인프라 상태 | [PR0-RESULT.md](PR0-RESULT.md) |
| 원격 DB DSN | [.env](.env) `DOOWON_POSTGRES_DSN` |
| FastAPI app composition | [apps/api/src/aidoo_api/app.py](apps/api/src/aidoo_api/app.py) |
| Alembic env.py (모델 import 위치) | [apps/api/alembic/env.py](apps/api/alembic/env.py) |
| init_db (도메인 import 위치) | [apps/api/src/aidoo_api/core/db.py](apps/api/src/aidoo_api/core/db.py) |
| 기존 도메인 모델 패턴 참조 | [apps/api/src/aidoo_api/domains/pms/models.py](apps/api/src/aidoo_api/domains/pms/models.py) |
| 인증/권한 헬퍼 | [apps/api/src/aidoo_api/domains/auth/dependencies.py](apps/api/src/aidoo_api/domains/auth/dependencies.py) |

## 9. 사용자 선호 (이전 세션에서 확인됨)

- 원격/공유 인프라에 쓰기 전 명시 승인 요구. autopilot 으로 진행하지 말 것
- 작업 도중 결정/상태 변화는 즉시 PR0-RESULT.md 같은 작업 파일에 기록할 것 (메모리 시스템 X, 프로젝트 루트 임시 파일 O — 작업 끝나면 삭제 예정)
- 한국어 응답 선호
- 백엔드 변경은 테스트로 검증한 뒤 보고할 것
