# PR1 진행 상태 — Meeting 도메인 스켈레톤 (검증/디버깅 단계)

> **새 세션 첫 메시지 예시**: "프로젝트 루트의 [PR1-STATUS.md](PR1-STATUS.md), [PR1-HANDOFF.md](PR1-HANDOFF.md), [PR0-RESULT.md](PR0-RESULT.md) 세 파일 읽고 PR1 검증/디버깅 이어서 진행해주세요."

작성일: 2026-04-10
모델: Claude Opus 4.6 (1M context)
이전 세션 요약: PR1 의 백엔드/프런트엔드 산출물 작성 → 자동화 검증 통과 → 사용자 피드백 두 번 (`참석자 검색 누락`, `다크모드 가독성`) 반영

## 1. 한 줄 요약

**PR1 산출물은 모두 작성됐고 자동화 검증 (pytest 52 passed, typecheck 신규 0) 은 모두 green 입니다. 원격 dev DB 에 마이그레이션도 적용 완료. 2 라운드 검증/디버깅에서 Upcoming leak 1건 fix + 회귀 테스트 추가, 타임존 chain 진단 완료 (사용자 결정 대기).**

## 1a. 2-3 라운드 (2026-04-10 후속 세션) 변경 사항

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

### 작업 트리에 PR1 와 무관한 사전 수정 4 개 (해결됨)

이전 세션 시작 시점에 작업 트리에 admin/health 관련 4 개 파일이 modified 상태로 남아있었고, PR1 commit 만들 때 stage 하면 안 된다는 경고가 여기 있었습니다.

**현재 상태**: 해당 작업은 **별도로 commit 되어 origin/main 에 있습니다**:
- `c544455 Add admin user list pagination and filtering`
- `927ff4f Improve admin people management`

PR1 커밋 (`3f7c7a9`, `dcced7a`) 과 섞이지 않았고, 작업 트리는 깨끗합니다. 이 섹션은 히스토리 보존용으로만 남겨둡니다.

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
