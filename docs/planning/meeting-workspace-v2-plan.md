# Meeting Workspace 전환 계획 v2 — Workspace/ACL 변경 반영

## 상태

- 이 계획은 저장용 기준 문서다.
- 실제 구현은 `워크스페이스별 앱 사용 권한 차등 정책`에 대한 논의와 선행 패치 이후 진행한다.
- 선행 논의 주제:
  - workspace별 앱 enable/disable 모델이 운영상 실제 이점이 큰가
  - `meeting notes`를 `meeting` 기능으로 볼지 `docs` 기능으로 볼지
  - `meeting enabled / docs disabled` 조합을 계속 허용할지

## Summary

`2026-04-13`의 마지막 커밋 `fix(workspace): bind request-scoped meeting flows` 이후에는 `meeting` 관련 동작이 더 이상 전역 workspace fallback에 기대면 안 된다. 새 계획은 이를 반영해 `meeting workspace`와 `meeting notes`를 모두 **request-scoped workspace 기준**으로 설계한다.

이번 수정의 핵심 판단은 다음이다.

- `meeting notes`는 이번 PR에서는 `meeting app의 내장 기능`으로 취급한다.
- 따라서 `meeting`이 켜진 workspace에서는 `docs` 앱이 꺼져 있어도 meeting 화면 안에서 notes 작성은 허용한다.
- 대신 `Open in Docs`는 `docs` 앱이 켜져 있고 사용자가 `nav.docs`를 가진 경우에만 노출한다.
- 새 구현은 어떤 계층에서도 “현재 workspace를 추론해서 fallback” 하지 않는다. 라우트, API, 서비스 모두 명시적 workspace를 사용한다.

## Key Changes

### 1. Workspace / ACL 기준 수정

- 새 미팅 화면 경로는 `/w/:workspaceSlug/meeting/:meetingId`로 고정한다.
- 미팅 목록 행 클릭은 항상 위 경로로 이동한다. `?id=` 기반 패널 상세보기는 주 흐름에서 제거한다.
- 모든 새 meeting endpoint는 `require_current_workspace`를 사용하고, 서비스 함수도 `workspace`를 인자로 받는다.
- 새 기능에서 `getCurrentOrLastWorkspaceSlug()` 같은 fallback 기반 탐색은 쓰지 않는다. meeting workspace는 항상 라우트의 `workspaceSlug`를 진실 원본으로 사용한다.
- cross-workspace 접근은 slug 기준으로 엄격히 막는다. 다른 workspace slug로 같은 `meetingId`를 열면 404/403으로 처리한다.
- meeting notes 생성/조회/저장은 `meeting participant` 권한을 기준으로 허용한다. `nav.docs`는 필수 조건이 아니다.
- `Open in Docs` 버튼과 docs deep-link는 `docs` 앱이 현재 workspace에 enabled이고 사용자가 `nav.docs`를 가진 경우에만 노출한다.

### 2. Meeting Notes 모델 / API

- `Meeting`에 `notes_doc_id`, `notes_page_id`를 추가한다.
- meeting notes는 `1 meeting : 1 dedicated native doc + 1 root page`로 고정한다.
- dedicated notes는 `POST /api/v1/meeting/meetings/{meeting_id}/notes/ensure`에서만 생성/보장한다.
- `notes/ensure`는 idempotent 해야 하며, 같은 meeting에 이미 notes가 있으면 그대로 반환한다.
- notes 생성은 docs router의 `create_native_doc`를 호출하지 않고, meeting domain 내부에서 `create_native_doc_for_user(...)`를 직접 사용한다. 이유는 notes가 `docs feature`가 아니라 `meeting feature`에 속해야 하기 때문이다.
- notes access grant는 기존 `DocMeetingAccess`를 재사용한다. organizer와 attendee는 meeting grant로 notes를 읽고 편집한다.
- meeting attendee 변경 시 notes doc grant도 기존 meeting grant 갱신 흐름에 맞춰 동기화한다.
- dedicated notes doc는 `doc_links`와 별개다. 회의 참고 문서는 계속 `doc_links`, 회의 본문 메모는 `notes_doc_id`로 분리한다.
- 이번 PR에서는 notes content CRUD를 위한 별도 meeting-owned rich text API는 만들지 않는다. notes doc/page 메타만 meeting API가 관리하고, 실제 블록 content read/write는 기존 docs item/page endpoint를 재사용한다.
- 단, meeting workspace에서 docs endpoint를 호출할 때는 meeting 전용 client helper를 둬서 `workspaceSlug`를 명시적으로 넘긴다. ambient path/fallback에 기대는 generic docs 호출은 사용하지 않는다.

### 3. Frontend / 화면 구조

- 새 `MeetingWorkspaceView`를 추가한다.
- 중앙 영역은 `BlockEditor` 하나만 두고, dedicated notes root page를 autosave 편집한다.
- 우측 rail에는 `회의 정보`, `참가자`, `agenda`, `연결 태스크`, `연결 문서`, `첨부 파일`, `녹음`, `후처리 상태`만 둔다.
- 기존 `DocsView`의 좌측 트리, 공유 모달, 문서 셸은 meeting workspace에 가져오지 않는다.
- meeting workspace 진입 시 순서는 `getMeeting -> notes_doc_id 없으면 notes/ensure -> notes page load -> editor mount`로 고정한다.
- 메모 저장은 docs와 동일하게 debounce autosave를 사용한다.
- 회의 notes는 single-page 편집만 노출한다. multi-page notebook UI는 넣지 않는다.
- `Open in Docs`는 조건부 노출이다.
  - `docs` 앱 enabled + 사용자가 `nav.docs` 보유: 노출
  - 그 외: 숨김
- recording 영역은 현재 구현된 `RecordingControls`, `RecordingRecoveryBanner`, `useChunkedRecorder`, `useRecordingPoll`를 재사용한다.
- recording 상태 표시는 `원본 업로드`와 `배치 후처리`를 분리한다.
  - 예: `원본 업로드 완료`, `전사 대기 중`, `요약 중`, `후처리 실패`
- 업로드 후에는 “이제 페이지를 닫아도 됩니다” 문구를 보여주고, 후처리는 배치 상태로만 추적한다.

### 4. 타입 / 테스트 / 검증 포인트

- `MeetingDetail`에 `notes_doc_id`, `notes_page_id`, `can_edit_notes`, `docs_entry_available`를 추가한다.
- recording 응답은 `asset_status`, `processing_status`, `failure_stage`, `ready_for_playback`를 추가해 UI가 저장/배치를 분리해서 표시하게 한다.
- API 테스트:
  - `notes/ensure` 첫 생성과 재호출 idempotency
  - 다른 workspace slug로 같은 meeting 접근 차단
  - `meeting enabled / docs disabled` workspace에서도 notes 생성/편집 가능
  - attendee가 `nav.docs` 없이도 meeting notes read/edit 가능
  - `Open in Docs` 조건 필드 계산
- Web 테스트:
  - 목록 행 클릭 시 `/w/:workspaceSlug/meeting/:meetingId` 이동
  - 첫 진입 시 notes 자동 생성
  - autosave 후 reload 시 내용 유지
  - docs disabled일 때 editor는 열리지만 `Open in Docs`는 숨김
  - recording 카드에서 upload와 processing 상태가 분리되어 표시
- E2E:
  - workspace A 회의를 workspace B slug에서 열면 접근 차단
  - docs disabled workspace에서 meeting notes 작성 가능
  - docs enabled workspace에서는 same note가 docs 화면에서도 열림
  - 녹음 업로드 후 playback 가능, 후처리 상태는 queued/failed/done으로 별도 갱신

## Assumptions And Defaults

- 이번 PR에서는 `meeting notes = meeting 기능`으로 고정한다. `workspace별 앱 권한 선택 모델` 자체의 재설계는 다음 PR 논의 주제로 미룬다.
- 따라서 `docs` 앱 disabled 여부는 meeting notes 작성 가능성에 영향을 주지 않는다. 영향을 주는 것은 `Open in Docs` 같은 docs-shell 진입만이다.
- dedicated meeting notes는 회의 전용 자산이며, generic docs attachment와 섞지 않는다.
- notes content 저장은 기존 docs primitives를 재사용하되, workspace는 항상 명시적으로 전달한다.
- 향후 docs ACL이 더 강하게 조여져 item/page endpoint 재사용이 어려워지면, 그때 meeting-owned notes content API로 분리하는 후속 PR을 연다. 이번 PR에서는 분리하지 않는다.
