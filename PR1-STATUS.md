# PR1 진행 상태 — Meeting 도메인 + 부수 PMS access 보강

> **새 세션 첫 메시지 예시**: "프로젝트 루트의 [PR1-STATUS.md](PR1-STATUS.md), [PR1-HANDOFF.md](PR1-HANDOFF.md), [PR0-RESULT.md](PR0-RESULT.md) 세 파일 읽고 이어서 진행해주세요."

작성일: 2026-04-10 (라운드 1), 마지막 갱신: 2026-04-11 (라운드 8 — dev DB reset + access model 보강 방향 결정)
모델: Claude Opus 4.6 (1M context)
이전 세션 요약: PR1 skeleton 작성 → 자동화 검증 → 사용자 dog-food 디버깅 8 라운드

## 1. 한 줄 요약

**PR1 본체는 완전히 안정화됐고 (pytest 62 passed, typecheck 신규 0), 원격 dev DB 는 reset 후 fresh 시드 상태로 돌아와 사용자 QA 대기 중입니다.** 사용자 디버깅 중에 PR1 범위를 넘는 근본 버그 세 개 (ProjectMember 좀비 테이블, ensure_seed_data 가 user data 파괴, groupedSpaces 가 role 드롭) 를 잡고 PMS space 멤버 관리 UI 를 신규로 만들었습니다. **다음 작업은 "3 레이어 권한 모델 UX 보강 진단" 을 사용자 요청에 따라 별도 세션에서 따로 시작**.

## 최신 라운드 (8) — 2026-04-11

**세션 마지막에 사용자 결정**: 현재 3-레이어 access 모델 (system role + workspace binding + team membership) 은 **유지**하되, 사용하기 편하게 **보강** 방향으로 가기로 함. 보강안 1~5 번은 다음 세션에서 사용자가 다시 진단 요청 예정. 이번 세션은 여기서 종료하고 dev DB 를 깨끗한 상태로 reset.

**이번 라운드에 한 일**:
- `codex/meeting-delete-confirm-dialog` 를 포함한 stale codex branch 들 (docs-unified-hub, pms-space-hierarchy-stabilization, meeting-delete-confirm-dialog) 을 모두 main fast-forward 또는 무손실 삭제로 정리. 현재 로컬/원격 모두 `main` 하나만 존재.
- 원격 dev DB 를 `reset_dev_db --force --seed-dev-accounts` 로 **완전 리셋**. 좀비 `pms_docs` 테이블도 이참에 제거됨.
- `reset_dev_db.py` 의 **두 개 잠재 버그** 를 같이 수정 (commit `0321c45`):
  1. `meeting`/`docs` 도메인 models 를 import 하지 않아 `Base.metadata.drop_all()` 이 meeting_task_links 등을 인지 못해 FK 순서 에러
  2. `Base.metadata.drop_all()` 자체가 orphan 테이블 (예: `pms_docs`) 을 처리 못함 — `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` 으로 교체
- SpaceMembersModal 을 Linear-style 로 리디자인 (아바타/divide-y/overflow 메뉴) → **CreateSpaceModal 에 멤버 초대 섹션 통합** (사용자 피드백 "따로 뒤에 뜨지 말고"). SpaceOverviewView 에 멤버 panel 추가.
- 작업 문서 업데이트 (이 라운드).

**현재 원격 dev DB 상태** (reset 직후):
```
users:            8 (시드 계정)
workspaces:       6
feature_policies: 6
pms teams:        1 (Team Space)
team_members:     2 (pms-member: member, pms-viewer: viewer)
pms_projects:     1 (DEMO)
pms_issues:       0
meetings:         0
docs_native_docs: 0
pms_docs 좀비:    제거됨
```

**시드 계정 공유 비밀번호**: `Aidoo!dev1234`

## 2. PR1 본체 (라운드 1-2) — 완료 상태

PR1 skeleton 작성 당시 산출물. **자세한 체크리스트는 §3, §5 참고 (히스토리 보존).**

| 영역 | 상태 |
|---|---|
| Backend meeting 도메인 (models/schemas/service/router/permissions) | ✅ |
| Alembic 마이그레이션 `d8fe1ed8923a_add_meeting_tables` | ✅ 원격 dev DB 적용 완료 |
| Frontend meeting 도메인 + MeetingView + 7 컴포넌트 | ✅ |
| AppBar/라우팅/SubSidebar 등록 | ✅ |
| pytest + typecheck + alembic 왕복 검증 | ✅ 모두 green |
| 다크모드 토큰 조정 | ✅ |

## 3. 후속 라운드 변경 사항 (라운드 2-8 누적)

## 3a. 라운드 2-3 — 2026-04-10 후속 세션

### Fixed: `list_meetings(scope="upcoming"|"all")` 가 비참석자에게 leak

**증상**: 워크스페이스 바인딩만 있는 비조직자·비참석자 사용자도 Upcoming 탭을 열면 다른 사람이 만든 회의가 다 보임. 클릭하면 403 (`get_meeting` 에서 `_ensure_user_can_view` 차단).

**원인**: [service.py:list_meetings](apps/api/src/aidoo_api/domains/meeting/service.py) 의 `scope="upcoming"` / `"all"` 분기가 user 필터를 안 걸었음. `scope="mine"` 만 organizer/attendee 로 좁혔음.

**Fix**: platform admin 이 아닌 caller 에게는 모든 scope 에 organizer-or-attendee 필터를 항상 적용. platform admin 은 종전대로 `upcoming`/`all` 에서 워크스페이스 전체 조회 가능. `mine` 은 admin 도 본인 것만 보도록 명시 좁힘 (탭 라벨이 정확하게).

**테스트**: `test_upcoming_scope_does_not_leak_other_users_meetings` 추가. mine/upcoming/all 세 scope 모두에서 비참석자가 0건 보고, 그 후 초대되면 1건 보는지 검증. 직접 GET 도 403 확인.

**자동화 결과**: pytest 51→52 passed.

### Diagnosed (fix 보류, 사용자 결정 대기): 타임존 roundtrip 버그

**원격 dev DB 직접 조회 결과**:
```
SHOW TIMEZONE = Etc/UTC
now() = 2026-04-10 11:30 UTC
meetings:
  '미팅1'        start_at=2026-04-10 02:00, end_at=03:00
  'ㅎㅇㅎㄹㅇㄴ'  start_at=2026-04-10 11:00, end_at=12:00
```

**Node TZ 검증** (`TZ=Asia/Seoul node`):
- `new Date("2026-04-10T11:00").toISOString()` → `"2026-04-10T02:00:00.000Z"` (KST→UTC)
- `new Date("2026-04-10T11:00:00")` (백엔드가 돌려준 tz 마커 없는 ISO) → 로컬 KST 11:00 으로 해석 → 화면엔 "오전 11:00"

**체인**:
1. 사용자가 datetime-local 에 wall-clock 11:00 입력
2. [MeetingCreateModal.localInputToIso](apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx) 의 `new Date(value).toISOString()` 가 KST→UTC 변환해서 `"02:00Z"` 전송
3. 백엔드 pydantic → tz-aware. SQLAlchemy + naive `DateTime` 컬럼 + postgres session UTC → naive `02:00` 저장
4. 읽기: 백엔드가 `"02:00:00"` (Z 없음) 반환
5. [MeetingList.formatTimeRange](apps/web/src/components/views/MeetingView/MeetingList.tsx) / [MeetingDetail.formatRange](apps/web/src/components/views/MeetingView/MeetingDetail.tsx) 가 `new Date(iso)` → 로컬 KST 02:00 으로 해석 → "오전 02:00" 표시

**현재 dev DB 데이터로 본 실제 동작** (KST 브라우저 가정):
- '미팅1' 입력=11:00 KST, 저장=02:00 UTC, 화면=오전 02:00 (9시간 어긋남)
- 'ㅎㅇㅎㄹㅇㄴ' 입력=20:00 KST, 저장=11:00 UTC, 화면=오전 11:00 (9시간 어긋남)

스크린샷에 '오전 11:00' 으로 보이는 회의는 사실 사용자가 8 PM 으로 입력했을 가능성이 큼.

**`MeetingEditModal.toLocalInputValue` 도 같은 문제** — 백엔드가 돌려준 ISO 를 local 로 잘못 해석해서 picker 에 표시. 사용자가 그대로 저장하면 추가 9시간 어긋남이 누적될 수 있음 (Edit 한번 더 도는 케이스 검증 필요).

**`scope="upcoming"` 의 `datetime.utcnow() vs Meeting.end_at`** — 양쪽 모두 UTC-naive 로 통일돼 있어서 시간 비교 자체는 맞음. 다만 위 chain 의 영향으로 "사용자가 의도한 시간" 과 "DB 의 시간" 이 다르므로, 사용자가 "내일 11:00 회의" 를 만들었다고 생각해도 실제로는 9시간 어긋난 시각으로 필터링됨.

**해결 옵션** (사용자 결정 필요):

| 옵션 | 변경 범위 | 기존 데이터 |
|---|---|---|
| **A. Display 측만 fix** — 백엔드 ISO 가 UTC 라고 명시 (frontend 에서 'Z' 부착 후 parse) | `formatRange`, `formatTimeRange`, `toLocalInputValue` 3곳 (~10줄) | 의미적으로 자동 복원 (저장된 02:00 UTC = 11:00 KST 로 표시) |
| **B. Input 측만 fix** — `localInputToIso` 가 wall-clock 그대로 (Z 없이) 보내도록 | `localInputToIso` 1곳 (~3줄) | 복원 안 됨 (기존 데이터는 그대로 어긋난 채 표시) |
| **C. Backend 를 TIMESTAMPTZ 로 마이그레이션** | models.py + alembic 마이그레이션 + pydantic serializer | 마이그레이션이 변환 |
| **D. 그대로 두고 PR4 (Event 도메인) 가 한꺼번에 처리** | 0 | — |

권장: **A**. 가장 작고, 기존 데이터 의미가 자동 복원되며, 백엔드 변경 없음. 단점은 "백엔드가 돌려주는 naive ISO 는 실은 UTC" 라는 암묵적 컨벤션이 frontend 에 박힘. PR4 에서 Event 도메인 + TIMESTAMPTZ 로 전환할 때 cleanup.

이 옵션 중 어느 걸 갈지는 사용자 결정 후 다음 라운드에서 작업.

### Fixed (3 라운드): 타임존 표시 chain — 옵션 A 적용

**계기**: 사용자가 Edit 모달에서 시작=오후 9시, 종료=오후 11시 로 저장했더니 화면이 오후 12시 ~ 오후 2시 로 표시되는 증상을 직접 보고 (스크린샷 2장). 정확히 KST→UTC 9시간 offset.

**컨벤션 명시**: 백엔드가 돌려주는 tz 마커 없는 ISO (`"2026-04-10T12:00:00"`) 는 **UTC** 로 해석한다. JS `new Date()` 가 이걸 local 로 잘못 해석하지 않도록 frontend 에서 'Z' 를 부착한 뒤 parse.

**Fix 위치**:
- [apps/web/src/domains/meeting/meeting-api.ts](apps/web/src/domains/meeting/meeting-api.ts) — `parseServerDateTime(iso)` helper 추가. tz 마커가 없으면 'Z' 부착. PR4 에서 TIMESTAMPTZ 전환 시 제거 예정이라고 docstring 에 명시.
- [apps/web/src/components/views/MeetingView/MeetingList.tsx](apps/web/src/components/views/MeetingView/MeetingList.tsx) `formatTimeRange` — `new Date(iso)` → `parseServerDateTime(iso)`
- [apps/web/src/components/views/MeetingView/MeetingDetail.tsx](apps/web/src/components/views/MeetingView/MeetingDetail.tsx) `formatRange` — 동일
- [apps/web/src/components/views/MeetingView/MeetingEditModal.tsx](apps/web/src/components/views/MeetingView/MeetingEditModal.tsx) `toLocalInputValue` — 동일

**Backend 미변경**: 입력 측 (`localInputToIso` → `Date.toISOString()`) 는 그대로 KST→UTC 변환해서 전송. Backend 는 그대로 naive 컬럼에 저장. 표시 측만 fix 했더니 chain 이 self-consistent 가 됨.

**기존 데이터 의미 자동 복원**:
- '미팅1' 저장값 02:00 → 표시 11:00 KST (사용자가 원래 의도했던 11 AM)
- 'ㅎㅇㅎㄹㅇㄴ' 저장값 11:00 → 표시 20:00 KST (8 PM)

**회귀 테스트**: `test_meeting_time_roundtrip_with_utc_iso_input` 추가. 프론트엔드 파이프라인 (`Date.toISOString()` 의 Z-suffixed UTC ISO) 으로 POST/GET/PATCH 한 결과가 모두 동일한 wall-clock 값으로 돌아오는지 검증.

### Fixed (3 라운드): Edit/Create 모달 outside-click 닫힘

**계기**: datetime-local picker 의 달력 popup 에 확정 버튼이 없어서 외부 클릭으로 닫는 게 native 동작. 그런데 modal 도 outside-click 으로 닫혀서, picker 닫으려다가 modal 까지 같이 닫히고 작성 중인 데이터가 사라짐.

**Fix**: [packages/ui/src/lib/primitives/dialog.tsx](packages/ui/src/lib/primitives/dialog.tsx) Dialog 컴포넌트에 `dismissOnInteractOutside?: boolean` prop 추가 (default `true` — 기존 동작 유지). `false` 일 때 Radix `onPointerDownOutside` / `onInteractOutside` 에서 `event.preventDefault()` 호출. ESC 와 X 버튼은 항상 동작.

[MeetingCreateModal](apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx) 와 [MeetingEditModal](apps/web/src/components/views/MeetingView/MeetingEditModal.tsx) 에서 `dismissOnInteractOutside={false}` 사용.

**다른 8개 Dialog 사용처**: 비파괴 (default `true` 그대로). 추후 form 입력 위주 모달은 같은 패턴으로 이전할 가치 있음 — 이번 PR1 범위는 아님.

**자동화 결과**: pytest 52→53 passed, typecheck 신규 0 (사전 12개 그대로).

### Fixed (4 라운드): Picker 모달 권한 부족 시 한글 안내

**계기**: ai-member 계정 (`nav.meeting` 만 보유, `nav.pms`/`nav.docs` 없음) 으로 로그인한 사용자가 본인이 만든 회의에서 "+ 태스크" 또는 "+ 문서" 클릭 → Task/Doc Picker 모달이 열리고 → 백엔드 PMS/Docs 라우터의 `require_feature_access` 가드가 403 Forbidden 반환 → 모달엔 의미 불명의 영문 에러 또는 빈 화면.

사용자 확인: "이게 맞지?" → **네 의도된 차단**. 다만 안내 메시지가 한글로 명확해야 함.

**Fix**: [TaskPickerModal](apps/web/src/components/views/MeetingView/TaskPickerModal.tsx) / [DocPickerModal](apps/web/src/components/views/MeetingView/DocPickerModal.tsx) 가 `useAuth().hasFeature('nav.pms')` / `'nav.docs'` 로 사전 체크.

- 권한 없음 → API 호출 자체를 skip 하고 (403 안 일으킴), 자물쇠 아이콘 + 한글 안내 패널 렌더링:
  > "PMS 워크스페이스 접근 권한이 없어 태스크를 첨부할 수 없습니다.
  > 관리자에게 PMS 권한을 요청하시거나, PMS 권한이 있는 회의 주최자에게 첨부를 요청해주세요."
- 권한 있음 → 종전대로 프로젝트/이슈 리스트 로드.

**의도적으로 안 한 것**: "+ 태스크" / "+ 문서" 버튼을 처음부터 숨기거나 disabled 처리하지 않음. 이유:
1. 사용자가 "이 기능이 존재한다는 것" 자체는 인지해야 권한 요청을 할 수 있음
2. 현재 로그인 사용자가 organizer 가 아닌 경우 [`editable` 가드](apps/web/src/components/views/MeetingView/MeetingDetail.tsx) 가 이미 버튼을 숨김 — picker 모달까지 도달하는 사용자는 organizer 임이 보장됨

**자동화 결과**: typecheck 신규 0 (사전 12개 그대로). 권한 분기는 frontend-only render 변경이라 backend 테스트는 불필요.

### Refactored (5 라운드): NoAccessNotice 공통 컴포넌트로 추출

**계기**: 사용자 피드백 — "이런 비슷한 상황이 더 있을건대... 공통화 할 수 있나?". 권한 부족 시 한글 안내를 모달마다 직접 작성하면 향후 추가될 모달도 같은 코드를 복붙하게 됨.

**Fix**: [apps/web/src/components/common/NoAccessNotice.tsx](apps/web/src/components/common/NoAccessNotice.tsx) 신규. `workspaceLabel`, `action`, optional `helpText` prop 만 받음. 자물쇠 아이콘 + 표준 한글 메시지 + override 가능한 보조 텍스트.

[TaskPickerModal](apps/web/src/components/views/MeetingView/TaskPickerModal.tsx) 와 [DocPickerModal](apps/web/src/components/views/MeetingView/DocPickerModal.tsx) 가 인라인 JSX 대신 `<NoAccessNotice workspaceLabel="..." action="..." />` 호출.

향후 권한 게이트가 필요한 새 모달은 `useAuth().hasFeature('nav.X')` + `<NoAccessNotice />` 패턴을 그대로 재사용 가능.

### Fixed (5 라운드): 첨부 권한 완화 + 삭제 권한 분리

**계기**: 사용자 피드백 — "문서와 태스크는 참여자도 추가를 할 수 있어야 할 것 같은데, 회의 자료를 미리 올리는 용도가 될 수 있으니깐. 그러나 첨부된 태스크 문서 첨부파일은 미팅 최초 승인자나 등록한 사용자만 삭제 할 수 있도록 해야 할듯."

**의미**: PR1 기존 동작은 organizer 만 attach/detach. 사용자는 attendee 도 prep material 을 미리 올릴 수 있고, 누가 올린 attachment 는 그 사람 (또는 organizer) 만 삭제할 수 있어야 한다고 명시.

**Backend**:
- [permissions.py](apps/api/src/aidoo_api/domains/meeting/permissions.py) 에 `is_participant`, `ensure_meeting_participant`, `ensure_link_remover` 추가.
  - `ensure_meeting_participant` — organizer/attendee/admin 통과, 그 외 403
  - `ensure_link_remover` — organizer/admin/`added_by_id == user.id` 통과, 그 외 403
- [service.py](apps/api/src/aidoo_api/domains/meeting/service.py) 의 `attach_task` / `attach_doc` 가 `ensure_meeting_organizer` → `ensure_meeting_participant` 로 교체. `detach_task` / `detach_doc` 는 link 의 `added_by_id` 를 조회한 후 `ensure_link_remover` 호출.

**Frontend**:
- [meeting-permissions.ts](apps/web/src/domains/meeting/meeting-permissions.ts) 에 `isParticipant`, `canAttachToMeeting`, `canRemoveAttachment` 추가. 기존 `canEditMeeting` 은 metadata edit (organizer-only) 용도로 의미 명시.
- [MeetingDetail.tsx](apps/web/src/components/views/MeetingView/MeetingDetail.tsx) 의 "+ 추가" 버튼은 `canAttach`, 각 row 의 휴지통은 `canRemoveAttachment(user, meeting, link)` 로 분기.

**테스트**:
- `test_attendee_can_attach_doc_and_only_adder_can_remove` — attendee 가 자기 doc 첨부 OK, organizer doc 삭제 시도 403, 자기 doc 삭제 OK, organizer 가 attendee doc 삭제 OK
- `test_non_participant_cannot_attach_doc` — meeting 워크스페이스 바인딩만 있고 invitation 없는 stranger 는 attach 시 403

NB: 권한 매트릭스 테스트는 task 가 아닌 **doc** 으로 작성. 이유: `ensure_issue_readable` 가 `ProjectMember` 테이블을 직접 조회하는데 PMS 의 `add_project_member` 라우터가 SpaceMember 만 채우고 ProjectMember 는 안 채우는 PR2 미해결 항목이 있어, attendee 가 PMS issue 를 readable 로 만들 마땅한 setup 경로가 없음. Doc 는 `ensure_doc_readable` 가 owner 만 확인하므로 attendee 가 자기 doc 만 만들면 setup 끝.

### Added (5 라운드): MeetingFileAttachment — 회의에 임의 파일 업로드

**계기**: 사용자 피드백 — "태스크 문서 뿐만 아니라 첨부 파일도 미팅에 추가가 가능해야 할듯."

**아키텍처**: PMS Attachment 패턴 그대로 복용. MinIO 경로는 `meeting/{meeting_id}/{attachment_id}/{filename}`. 1시간 presigned GET URL 발급. 100 MB 사이즈 제한.

**Backend**:
- [models.py](apps/api/src/aidoo_api/domains/meeting/models.py) `MeetingFileAttachment` 모델 — id, meeting_id, filename, content_type, size_bytes, storage_key (unique), added_by_id, created_at. Meeting 에 cascade delete 관계 추가.
- [alembic/versions/13e887cfb1db_add_meeting_file_attachments.py](apps/api/alembic/versions/13e887cfb1db_add_meeting_file_attachments.py) — autogenerate 로 생성. CREATE TABLE 1개 + 인덱스 2개 (meeting_id, added_by_id). upgrade/downgrade/upgrade 왕복 + alembic check drift 0 검증 완료. **단 dev DB 에는 아직 미적용** (사용자 승인 후 적용).
- [schemas.py](apps/api/src/aidoo_api/domains/meeting/schemas.py) `MeetingFileAttachmentOut` 추가, `MeetingDetail.file_attachments` 필드.
- [service.py](apps/api/src/aidoo_api/domains/meeting/service.py) `attach_file` (async, multipart UploadFile), `detach_file`, `_serialize_file_attachment`, `_build_file_download_url` (모듈 레벨 — 테스트에서 monkeypatch 가능). `_load_meeting` 의 selectinload 에 `file_attachments` + `MeetingFileAttachment.added_by` 추가.
- [router.py](apps/api/src/aidoo_api/domains/meeting/router.py) `POST /meetings/{id}/files` (multipart), `DELETE /meetings/{id}/files/{file_id}`.

**Frontend**:
- [meeting-api.ts](apps/web/src/domains/meeting/meeting-api.ts) `MeetingFileAttachment` 타입, `uploadMeetingFile` (FormData multipart), `deleteMeetingFile` 함수. `MeetingDetail.file_attachments` 필드 추가.
- [MeetingDetail.tsx](apps/web/src/components/views/MeetingView/MeetingDetail.tsx) 새 "첨부 파일" Section. 숨겨진 `<input type="file" />` + ref 패턴, "+ 추가" 클릭 시 파일 선택. 업로드 중에는 라벨이 "업로드 중..." 으로 바뀜 (Section 컴포넌트에 `addLabel?: string` prop 추가). 파일 row 는 다운로드 링크 (presigned URL 새 탭) + 사이즈 + 업로더 이름 + (organizer/uploader 만) 휴지통 버튼.

**테스트** (mocked MinIO):
- `_FakeMinioClient` + `_install_fake_minio` 헬퍼 — `monkeypatch` 로 `meeting_service.get_minio_client` 와 `meeting_service._build_file_download_url` 를 in-memory 객체로 교체. PMS Attachment 는 backend 테스트가 아예 없는 반면, 새 meeting file attachment 는 happy path + 권한 매트릭스 모두 자동화로 검증.
- `test_meeting_file_attachment_upload_and_permission_matrix` — attendee 업로드 → 메타데이터 전부 검증 → admin 두 번째 업로드 → attendee 가 admin 파일 삭제 시도 403 → attendee 자기 파일 삭제 OK → admin 잔여 파일 삭제 OK. fake minio 의 `objects` / `removed` 로 storage 호출도 검증.
- `test_meeting_file_upload_rejects_non_participant` — invitation 없는 사용자는 업로드 403.

**자동화 결과**: pytest 53→57 passed (+4 신규), typecheck 신규 0 (사전 12개 그대로 — admin-pagination commit 으로 admin-console 라인 번호만 1021→1173 식으로 시프트).

**원격 dev DB 마이그레이션 적용**: **적용 완료** — `alembic current` → `13e887cfb1db (head)`. 적용 당시 사용자 "마이크레이션 커밋 푸시" 명시 승인.

**Commit**: `dcced7a` Refine Meeting domain: fixes, permissions, file attachments — 18 files, +1364/-146, origin/main 푸시 완료.

### Fixed (6 라운드): 파일 첨부 UX — Create 모달 첨부 + 명시 다운로드 버튼

**계기**: 사용자 피드백 — "미팅 등록 할때는 파일 첨부가 없음. 미팅 등록 후 미팅 우측 사이드 편집에서는 파일 업로드 및 열어보기는 잘됨" + "파일 다운로드용 버튼이 따로 있으면 좋겠음".

**Create 모달에 파일 첨부 추가** ([MeetingCreateModal.tsx](apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx)):
- `pickedFiles: File[]` 로컬 상태 + ref 기반 `<input type="file" multiple>` 숨김 처리
- "연결된 업무" 섹션에 "+ 파일" 버튼 (태스크/문서 버튼과 동일 라인)
- 선택된 파일은 칩 형태로 노출 (파일명 + 사이즈 + X 버튼)
- `handleCreate` 에서 기존 tasks/docs sequential attach 뒤에 `uploadMeetingFile` 루프 추가. failure collection 패턴 동일.
- Create 시점에 meeting_id 가 아직 없어서 tasks/docs 와 동일한 "로컬 수집 → post-create sequential upload" 패턴을 따름. 일부 업로드 실패 시에도 meeting 은 유지되고 사용자는 detail 패널에서 재시도 가능.

**다운로드 전용 버튼 분리** ([MeetingDetail.tsx](apps/web/src/components/views/MeetingView/MeetingDetail.tsx)):
- 기존: 파일명 자체가 presigned URL 링크 → 새 탭 open (브라우저가 PDF/image 는 미리보기, 그 외는 다운로드)
- 변경: 파일명은 preview 용 링크 (새 탭 open) 유지, 우측에 Download 아이콘 버튼 별도 추가
- Download 버튼은 `handleFileDownload` 호출 — fetch → blob → `URL.createObjectURL` → synthetic `<a download={filename}>` click → revoke. MinIO presigned URL 이 cross-origin 이라 `<a download>` attribute 가 무시되는 문제를 우회.
- 100 MB 파일까지는 브라우저 메모리에 올려도 체감 무리 없음.

**자동화 결과**: typecheck 신규 0 (사전 12개 그대로 — admin-people commit 으로 admin-console 라인 번호만 1173→1434 로 다시 시프트). Frontend-only 변경이라 pytest 는 동일 57 passed.

## 3b. 라운드 7 — 2026-04-11 근본 버그 라운드

사용자가 dog-fooding 하다가 "pms-member 가 만든 space 의 멤버가 자꾸 사라진다" 는 보고. 진단 결과 **세 개의 얽힌 root cause** 가 발견됐고 한 번에 모두 잡음.

### Root cause 1 — `ensure_seed_data` 가 user-created team memberships 를 매번 지움

**증상**: dev 서버가 재시작되거나 로그인 버튼만 눌러도 사용자가 만든 space 의 TeamMember row 가 사라짐. 사용자는 "분명 멤버를 추가했는데 나중에 0 명" 상태를 반복 경험.

**원인**: [access.py:ensure_dev_login_seed_data](apps/api/src/aidoo_api/domains/auth/access.py) 의 per-user reconcile loop 이 `"default_pms_space 가 아닌 TeamMember 는 무조건 DELETE"` 라는 공격적 로직을 가지고 있었음. 본래 의도는 "seed 계정의 default space 역할 관리" 였는데 user-created space 의 membership 까지 쓸어버림. `ensure_dev_login_seed_data` 는 매 부팅 + `GET /auth/bootstrap-status` + `POST /auth/dev-login` + `POST /auth/dev-admin-login` 마다 돌았기 때문에 사용자가 계정 전환만 해도 데이터가 파괴됨.

**Fix (2 단계)**:
1. **Round 7a** (commit `bc6bdab`) — seed loop 을 default_pms_space 의 row 만 reconcile 하도록 좁힘. 다른 space 의 membership 은 건드리지 않음. user data 파괴는 즉시 중단.
2. **Round 8a** (commit `1618b34`) — 더 깊은 수정: seed 는 **DB 초기화 시 한 번만** 돌아야 함. `is_infrastructure_seeded` + `are_dev_login_accounts_seeded` 두 guard 를 추가해서 이미 시드된 DB 에서는 no-op. `GET /auth/bootstrap-status` 는 순수 read 가 됨 (부작용 없음). `reset_dev_db.py` 는 drop 후 재시드하는 경로라 guard 가 자연스럽게 통과. 사용자 질문 "seed 는 초기화할 때 한 번만 하면 되는 것 아니냐" 를 반영.

### Root cause 2 — `ProjectMember` 테이블이 좀비 (INSERT 0 곳, 의사결정 read 0 곳)

**발견 계기**: 사용자가 pms-member 로 회의에 task 와 파일을 동시에 등록했는데 **파일만 저장되고 task 는 사라짐**. 파일이 성공한 건 silent failure 경로였고, task 는 meeting `ensure_issue_readable` 에서 403 을 받은 상태.

**원인**: meeting 의 [permissions.py:ensure_issue_readable](apps/api/src/aidoo_api/domains/meeting/permissions.py) 가 `ProjectMember` 테이블을 직접 조회했음. 그런데:
- `ProjectMember` 모델은 [pms/models.py:129](apps/api/src/aidoo_api/domains/pms/models.py#L129) 에 존재
- **INSERT 코드는 0 곳** (grep 으로 검증)
- `list_project_members` / `add_project_member` / `update_member_role` 라우터는 모두 내부적으로 `list_space_members`/`add_space_member`/`update_space_member` 를 호출하고 응답만 `ProjectMemberItem` 모양으로 다시 포장
- `Project.members` 관계는 `member_count` 계산 fallback 으로만 쓰이고, 실제 count 는 `Team.members` 로 별도 계산됨
- 즉 PMS 가 한 번 리팩토링되며 Project-level 멤버십 → Space-level 멤버십으로 평탄화됐고 ProjectMember 테이블은 완전 고아 상태 (ProjectMember row 를 읽는 곳이 meeting 의 권한 체크 1 곳뿐)

사용자가 세션 초반에 "ProjectMember 이거 진짜 사용 안 하는 건가? 사용 안 하는 거면 관련 코드 삭제해줘" 라고 정확하게 추측.

**Fix** (commit `98a4700`):
- 모델 + `Project.members` 관계 삭제
- 3 곳의 `selectinload(Project.members).selectinload(ProjectMember.user)` eager load 제거
- `list_project_members` / `add_project_member` / `update_member_role` 라우터는 **유지**하되 응답 모델을 `SpaceMemberItem` / `SpaceMemberListResponse` 로 교체 (필드 모양 동일 → frontend 변경 0)
- 새 alembic 마이그레이션 `6b21fc0a74c8_drop_pms_project_members` — 로컬 docker 왕복 + drift 0 검증 + 원격 dev DB 적용 완료
- `ensure_issue_readable` 은 PMS 와 동일한 `_ensure_space_access` 패턴 (= `resolve_team_role`) 로 재작성. meeting 의 attachable issue set 이 사용자가 PMS UI 에서 볼 수 있는 issue set 과 정확히 일치.
- 회귀 테스트 `test_attendee_can_attach_task_via_space_access` 추가.

### Root cause 3 — `groupedSpaces` 가 `current_user_role` 을 드롭

**증상**: 사용자가 space 를 만들어도 사이드바 hover 시 `+` / `...` 메뉴가 안 떠서 list 추가/멤버 관리 진입이 불가능.

**원인**: [SubSidebar.tsx:groupedSpaces](apps/web/src/components/layout/SubSidebar.tsx) reducer 가 `pmsTeams`/`pmsLists`/`pmsFolders` 를 flatten 하며 space 객체를 `{id, name, rootLists, folders}` 로만 복사하고 `current_user_role` 을 버림. `canManageSpace(space)` 가 항상 false → context menu 전체 숨김. typecheck 에 오래 남아있던 사전 오류 2 개 (`current_user_role does not exist`) 가 사실은 이 runtime 버그의 시그널이었음.

**Fix** (commit `742672c`): reducer 가 원본 `PmsSpace` 객체를 spread 로 보존. typecheck 오류 12 → 10 으로 줄어듦 (진짜 버그가 해결되면서).

### Silent failure 차단 (commit `bc6bdab` 일부)

[MeetingCreateModal.handleCreate](apps/web/src/components/views/MeetingView/MeetingCreateModal.tsx) 가 첨부 실패 시 `setError(...)` 하고 **그 직후 `onCreated`** 를 호출해 부모가 모달을 닫아버림. 사용자가 에러 메시지를 볼 시간이 0.

**Fix**: failure 발생 시 `onCreated` 를 호출하지 않고 모달 유지. 새 state `createdMeetingId` + "회의 보러 가기" 명시 버튼. 성공한 칩은 제거되고 실패한 칩만 남아 사용자가 어떤 게 안 됐는지 시각적으로 인지.

### PMS Space 멤버 관리 UI 신규 — round 7

**계기**: root cause 2 를 고쳐도 정작 어드민이 다른 사용자를 space 에 넣을 UI 가 없으면 의미 없음. Admin Console 도 space 멤버 관리 섹션이 아예 없었음 (`admin-api.ts` 에 함수는 정의됐는데 호출하는 곳 0).

**Fix** (commit `98a4700`):
- [SpaceMembersModal.tsx](apps/web/src/components/views/PMSView/SpaceMembersModal.tsx) 신규 — 처음엔 박스-per-row 스타일로 만들었다가 round 7b 에서 Linear 스타일로 리디자인
- SubSidebar 의 SpaceContextMenu 에 "멤버 관리" 진입점 추가
- PMS `/users` endpoint + `listPmsUsers` frontend 함수는 이미 존재해서 그대로 재사용

## 3c. 라운드 7b — SpaceMembersModal Linear 리디자인

사용자 피드백 "멤버관리 화면이 좀 촌스러운데 이게 현대적인 멤버관리 스타일인가?" → Linear 스타일로 리디자인 (commit `06bd0a1`):

- **아바타** 32px 원형, user_id 기반 hash 로 14색 팔레트에서 결정적 선택, `initials()` 헬퍼 재사용
- **Row 구조**: 4 개 박스 → 하나의 테두리 박스 안에 `divide-y`
- **Role 표시**: Select box → crown/shield 아이콘 + 텍스트 배지
- **Overflow 메뉴** (`⋮`): hover-revealed, portal 로 팝오버, 역할 변경 (체크 마크) + "스페이스에서 제거" (빨간 액션)
- **초대 섹션**: role select 제거 (기본 member, 나중에 변경), 한 줄 검색 + live dropdown
- **정렬**: Owner → Admin → Member → Viewer
- **Owner row**: 다른 row 와 동일 높이, action 자리는 빈 span 으로 정렬 유지

## 3d. 라운드 8 — Create 모달 통합 + seed guard + dev DB reset

### CreateSpaceModal 에 멤버 초대 통합 (commit `8d2f297`)

사용자 피드백 "멤버 추가는 스페이스 만드는 모달에서 같이 하도록 해줘 따로 뒤에 뜨지 말고".

**변경**: [CreateSpaceModal.tsx](apps/web/src/components/views/PMSView/CreateSpaceModal.tsx) 에 멤버 picker 섹션 직접 추가. 기존 name/description 아래에 "멤버 초대 (선택)" 섹션 — chip row + 검색 input + live dropdown. createSpace → sequential addSpaceMember. SubSidebar 의 `onCreated` 에서 SpaceMembersModal 자동 open 동작 제거.

### Seed idempotency guard (commit `1618b34`)

라운드 7 의 seed fix 를 더 깊이 확장. `ensure_seed_data` 와 `ensure_dev_login_seed_data` 에 각각 guard 추가:

- `is_infrastructure_seeded(db)` — `hq` OrgUnit + 6 개 DEFAULT_WORKSPACES 가 모두 존재하면 true
- `are_dev_login_accounts_seeded(db)` — 8 개 DEV_LOGIN_ACCOUNTS email 이 모두 존재하면 true
- 둘 다 true 면 seed 함수들이 **no-op 로 즉시 return**

결과: `ensure_seed_data` 는 DB 가 이미 형상에 있다면 admin 이 수정한 workspace 이름/설명을 덮어쓰지 않음. `ensure_dev_login_seed_data` 는 account 가 이미 모두 있으면 스킵하므로 매 로그인마다 reconcile 이 돌지 않음. bootstrap-status 는 부작용 있던 seed call 을 제거하고 순수 read 로 전환.

회귀 테스트 4 개:
- `test_seed_preserves_user_created_space_membership`
- `test_dev_login_is_idempotent_and_preserves_user_spaces`
- `test_ensure_seed_data_does_not_overwrite_workspace_renames`
- `test_seed_still_reconciles_default_space_membership`

### Dev DB 완전 리셋 (commit `0321c45`)

사용자 요청 "데이터 베이스를 리셋해줘 시드 적재하고". `reset_dev_db.py --force --seed-dev-accounts` 실행 중 두 개 잠재 버그 발견 및 수정:

1. **Missing imports** — `reset_dev_db.py` 가 `auth`/`media`/`pms` models 만 import 하고 `meeting`/`docs` 는 빼먹었음. `Base.metadata.drop_all()` 이 meeting_task_links 를 인지 못 해서 pms_issues drop 시 FK 에러.

2. **좀비 테이블 차단** — 수정 1 후에도 legacy `pms_docs` 테이블 (PR0 부터 남아있던 orphan) 이 `drop_all()` 을 막음. SQLAlchemy metadata-graph drop 은 metadata 에 등록된 테이블만 알기 때문에 구조적으로 orphan 처리 불가능.

**Fix**: `Base.metadata.drop_all()` → `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`. Alembic migration history 도 함께 초기화되므로 baseline 부터 head 까지 깨끗하게 재적용. 어떤 orphan 테이블이 있어도 확실하게 clean state.

**부가 효과**: PR0-RESULT.md §미해결 의 `legacy pms_docs` 항목이 해결됨.

## 4. 이번 세션이 할 일 (원래 요청 받은 범위)

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

## 5. 자동화 검증 결과 (라운드 8 시점 — 가장 최신)

| 항목 | 결과 |
|---|---|
| `pytest apps/api/tests/` | **62 passed** (라운드 1: 51 → 라운드 8: 62) |
| `alembic upgrade head → downgrade → upgrade → check` (로컬 docker) | 성공, drift 0 |
| 원격 dev DB `alembic current` | `6b21fc0a74c8 (head)` (최신) |
| `pnpm nx typecheck web` | **10 사전 오류** (라운드 1: 12 → 라운드 7: 10, groupedSpaces fix 가 2 개 해결) |

**신규 typecheck 오류 0** 이 핵심. 남은 10 개 사전 오류는 모두 PR1 과 무관한 legacy (PMSView string|null, admin-console Select disabled, admin-permissions literal, BoardView motion drag handler 등).

## 6. 사람 손 QA — 라운드 8 이후 fresh dev DB 기준

원격 dev DB 가 reset 됐고 현재 상태는 `Team Space` 하나 + `DEMO` 프로젝트 하나 + seed 계정 8 명. 다음 세션에서 dev 서버 띄우고 직접 눌러보면서 확인해야 할 것:

**Seed guard 검증 (round 8 의 핵심 fix)**
- [ ] 로그아웃 → 로그인 화면 열기 → pms-member 로 로그인 → **workspace 이름이 admin-edited 상태로 유지되는지** (seed 가 덮어쓰지 않음)
- [ ] pms-member 가 새 space 생성 → CreateSpaceModal 한 화면에서 멤버도 몇 명 추가 → 저장
- [ ] 로그아웃 → platform-admin 로그인 → 로그아웃 → pms-member 재로그인 → 방금 만든 space 의 멤버가 **여전히 그대로** 있는지 (seed loop 이 안 돈다는 검증)

**CreateSpaceModal 통합 흐름 (round 8)**
- [ ] Sidebar "+ New Space" → 한 모달에서 이름 + 설명 + 멤버 검색 + chip 추가까지 → 생성 → sidebar 갱신 + SpaceOverviewView 의 멤버 panel 에 추가한 멤버들 즉시 노출
- [ ] 멤버 chip 에 본인 (creator) 이 안 나타나는지 (자동으로 owner 추가되므로 검색 후보에서 제외)

**SpaceMembersModal (Linear 스타일)**
- [ ] SubSidebar 의 space 우클릭 → "멤버 관리" 진입
- [ ] 각 멤버 row 에 hover → `⋮` 버튼 노출 → 역할 변경/제거
- [ ] Owner row 에는 `⋮` 가 안 보임 + "소유자" 배지
- [ ] 상단 초대 input 에 이름/이메일 검색 → 드롭다운에서 클릭 → member 로 추가

**PR1 meeting 본체 — fresh DB 에서 회귀 없는지**
- [ ] Meeting 생성 (제목 + 시간 + 참석자 + 연결된 업무 + 첨부 파일)
- [ ] Task 첨부 / Doc 첨부 / File 업로드 각각 동작
- [ ] 파일 다운로드 버튼 (cross-origin blob roundtrip) 동작
- [ ] Attendee 가 본인 space 의 issue 를 meeting 에 첨부 가능 (ensure_issue_readable 수정 검증)
- [ ] 모달 outside-click 으로 안 닫히는지 (datetime picker 보호)

**아직 안 한 / 이번 세션에서 미뤄둔 사람 손 QA** (라운드 1-2 부터 이월)
- [ ] **다크모드 가독성** — Planner, PMS, Docs, Admin 전체 화면 톤 체크. 사용자가 "일단 문제 없는 듯 필요하면 다시 요청" 이라고 했음
- [ ] **AI 사이드바 deep-link** — "회의록" 클릭 → /meeting?tab=recordings 이동
- [ ] **SubSidebar "+" 드롭다운** — 다른 라우트에서 Meeting 클릭 시 라우팅 + 모달 이벤트

## 7. 알려진 잔재 / 미해결 사항 — 라운드 8 시점

### 해결됨 (이전 세션 잔재)
- ~~legacy `pms_docs` 테이블~~ — **round 8 의 `DROP SCHEMA public CASCADE` 로 제거됨**
- ~~`pms_user_doc_prefs` stale 인덱스~~ — DB reset 으로 자연 해소
- ~~`ProjectMember` 좀비 테이블~~ — round 7 에서 모델 + 마이그레이션으로 제거
- ~~ensure_seed_data 가 user data 파괴~~ — round 8 의 guard 로 차단

### 사전 typecheck 오류 10 개 (PR1 무관, main 시점부터 존재)
- `src/app-shell.ts(137,31)` — NavItem.appId 'home' widening
- `src/App.tsx(127,23)` — FEATURE_BY_APP_ID indexer 'home' 누락
- `src/components/views/PMSView/BoardView.tsx(81,20)` — motion drag handler
- `src/components/views/PMSView/PMSView.tsx(194,27)` 등 — string|null 3 건
- `src/domains/admin/admin-console.tsx` — Select disabled / NoticeTone 3 건
- `src/domains/admin/admin-permissions.ts(13,54)` — string|literal mismatch

### 다음 세션에서 사용자가 다시 진단 요청한 항목 — "3 레이어 권한 모델 보강"

세션 막바지 논의: 현재 access 모델 (system role + workspace binding + team membership) 은 **유지**, 하지만 사용하기 편하게 보강. 5 가지 옵션을 제시했고 사용자가 "지금을 유지하고 보강을 하지뭐" → "일단 지금 진단은 따로 다시 요청할테니" 로 **이번 세션은 종료**. 다음 세션에서 보강안 진단을 다시 요청하기로 함.

제시한 보강 옵션 (다음 세션 참조용):

1. **User edit dialog 에 space 목록 (읽기 전용)** — PeopleSection 의 "Accessible apps" 아래에 "PMS Spaces" 섹션 추가. 작음 (1-2h). 진단 가능성 큰 효과.
2. **PMS 바인딩 저장 시 orphan 경고** — WorkspacesSection 에서 nav.pms 바인딩 저장할 때 사용자가 team 에 안 속해있으면 경고 다이얼로그. 작음 (1h).
3. **User edit dialog 에서 space membership 편집** — 1 을 읽기 전용 → 편집 가능으로 업그레이드. 중간 (반나절).
4. **Access Group 에 workspace binding 템플릿** — 그룹에 사용자 넣으면 자동 fanout. 중간-큰 (1d). 데이터 파괴 위험 있어 신중.
5. **403 응답에 설명적 메시지 추가** — cross-app 403 에 "ask admin for nav.pms" 같은 힌트. 작음 (30m).

권장 순서: 1 → 2 → 3. 4 는 별도 세션 (fanout 위험), 5 는 1-3 후에 필요하면.

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

- ❌ 사용자 승인 없이 prod 환경 손댐, force-push, hook 우회
- ❌ 원격 dev DB 쓰기 작업 전 사용자 명시 승인 없이 진행
- ❌ `_apply_postgres_schema_compat()` 류 손제작 SQL 부활
- ❌ `Base.metadata.create_all()` 호출 추가
- ❌ prod 환경에서 `DOOWON_API_AUTO_MIGRATE=1` 사용
- ❌ 테스트 conftest 가 원격 DB 에 붙도록 변경
- ❌ PR1 범위 밖 항목 추가 (rooms, calendar grid, conflict detection, transcription worker)
- ❌ `ensure_seed_data` / `ensure_dev_login_seed_data` 의 guard 를 제거하거나 우회 — user data 파괴 회귀

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

## 13. 이번 세션 commit 히스토리 (가장 최근 → 오래된 순)

```
0321c45 reset_dev_db: drop schema wholesale instead of via metadata graph     (round 8)
1618b34 Seed must run on DB init only, not on every dev login                 (round 8)
8d2f297 Merge member invite into CreateSpaceModal                             (round 8)
bc6bdab Stop seed loop from deleting user-created space memberships           (round 7)
742672c Preserve current_user_role in groupedSpaces so space menus show up    (round 7)
98a4700 Add PMS space member management and remove ProjectMember zombie       (round 7)
06bd0a1 Redesign SpaceMembersModal in Linear-style                            (round 7b)
c81cdac Replace meeting delete confirm dialog                                 (round 7, user manual)
86068b9 Meeting file attachments: create modal + explicit download button     (round 6)
dcced7a Refine Meeting domain: fixes, permissions, file attachments           (round 5)
```

PR1 본체 skeleton (`3f7c7a9 Add Meeting domain skeleton (PR1)`) 와 PR0 (`8dd1458 Bootstrap Alembic with baseline migration`) 는 이전 세션.
