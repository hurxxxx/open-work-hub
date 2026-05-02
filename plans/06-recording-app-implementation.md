# Recording App Implementation Plan

> 문서 성격: 기존 Meeting 녹음 기능을 공용 Recording 도메인으로 승격하고, 별도 Recording 앱을 추가하는 실행 계획.
> 핵심 원칙: 레코딩 기능은 하나만 관리한다. Meeting 앱은 공용 Recording 기능의 consumer여야 하며, 별도 녹음 구현을 유지하지 않는다.

## Context

현재 시스템에는 Meeting 앱 내부에 녹음 기능이 이미 구현되어 있다.

- Backend: `apps/api/src/aidoo_api/domains/meeting/recordings.py`
  - chunk staging
  - MinIO 저장
  - playback URL
  - retry / delete / cleanup
  - meeting recording pipeline enqueue
- DB model: `MeetingRecording`, `MeetingRecordingStaging`
- Worker: `apps/worker/src/aidoo_worker/tasks/meeting.py`
  - `meeting.transcribe`
  - `meeting.summarize`
  - `meeting.extract_insights`
  - `meeting.generate_doc`
- Web: Meeting 화면 내부 recorder
  - `useChunkedRecorder`
  - `recording-db.ts`
  - `useRecordingRecovery`
  - `RecordingControls`
  - `RecordingRecoveryBanner`

새 요구는 Meeting 화면 안의 보조 기능이 아니라, 모바일/웹에서 빠르게 녹음을 시작하고 나중에 정리할 수 있는 first-class Recording 앱이다. 따라서 기존 구현을 복제하지 않고, Meeting에 갇힌 녹음 구현을 공용 Recording 도메인으로 승격한다.

2026-05-02 결정:

- 기존 Meeting 녹음 row/object는 canonical Recording으로 backfill하지 않는다. 필요하면 기존 녹음은 삭제해도 된다.
- Qwen/Qwen3-ASR-1.7B 검토와 ASR 파이프라인 연결은 저장/관리 UX 이후로 미룬다.
- 현 단계의 닫힘 기준은 Recording 앱에서 새 녹음을 만들고, 원본 음성을 안전하게 저장하고, 내 녹음 목록에서 재생/삭제까지 관리하는 것이다.

## Product Goal

Recording 앱의 목적은 사용자가 회의나 현장에서 앱을 열고 한 번의 동작으로 녹음을 시작한 뒤, 나중에 녹음 목록에서 회의/태스크/문서에 연결해 정리할 수 있게 하는 것이다.

v1의 성공 기준:

- 새 Recording 앱에서 녹음 종료 후 원본 음성이 canonical `recordings` row와 MinIO object로 저장된다.
- Recording 앱은 owner-private 목록, 재생, 삭제 관리를 제공한다.
- 전사/전사 원문 문서/회의록 문서 상태는 별도 pending 상태로 남겨서 백엔드 파이프라인 미완성 상태를 명확히 보여준다.
- 모바일 웹/PWA와 데스크톱 웹에서 Recording 앱 첫 화면의 Mic 버튼으로 즉시 녹음을 시작한다.
- 녹음 시작 전에 제목, 회의, 태스크, 참석자 같은 입력을 요구하지 않는다.
- 녹음 중 생성된 chunk는 먼저 로컬 IndexedDB에 저장하고, 가능한 즉시 서버 staging으로 업로드한다.
- 브라우저 탭/앱이 닫히면 이후 녹음 지속은 보장하지 않지만, 이미 캡처된 chunk는 복구 가능해야 한다.
- 사용자는 나중에 날짜/시간 기준으로 내 녹음 목록을 확인하고, 특정 회의나 PMS 태스크에 연결할 수 있다.
- 녹음 하나에서 기본 산출물 3개를 만든다.
  - 원본 음성
  - 전사 원문 문서
  - 회의록 문서

회의록 문서는 요약 문서가 아니다. 전사에 있는 내용을 임의로 추측하거나 줄이거나 늘리지 않고, 사람이 읽기 좋게 구조화하는 문서다.

## Architecture Principles

### 1. Recording is the canonical domain

새 도메인은 `apps/api/src/aidoo_api/domains/recording/`에 둔다.

Meeting 전용 recording service가 canonical이 되면 안 된다. 앞으로 녹음과 관련된 저장, 업로드, 복구, playback, retry, pipeline 상태 관리는 Recording 도메인이 소유한다.

Meeting 도메인은 다음만 담당한다.

- Meeting detail에서 연결된 recordings 표시
- Meeting recording compatibility endpoint 유지
- Meeting container에 연결된 recording을 기반으로 meeting insight/action extraction 실행

### 2. Meeting endpoints remain as compatibility wrappers

기존 API surface는 바로 제거하지 않는다.

기존 endpoint:

```text
/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting_id}/recordings/...
```

위 endpoint는 유지하되 내부에서 공용 Recording service를 호출한다. Meeting과의 관계는 별도 FK 컬럼이 아니라 `RecordingContainer`로 표현한다.

```text
container_app = "meeting"
container_type = "meeting"
container_id = <meeting_id>
```

### 3. Frontend recorder is shared

현재 Meeting 화면 내부에 있는 recorder hook과 IndexedDB 구현은 Recording 앱의 public API 경계로 이동한다.

목표 구조:

```text
apps/web/src/app-modules/recording/
  api/
    recording-api.ts
    recording-db.ts
  public-api.ts
  routes.tsx
  manifest.ts
  sidebar.ts
  views/
    RecordingView.tsx
    QuickRecordPanel.tsx
    RecordingList.tsx
    RecordingDetail.tsx
    RecordingRecoveryPanel.tsx
    RecordingAttachPanel.tsx
  recorder/
    useChunkedRecorder.ts
    useRecordingRecovery.ts
    RecordingControls.tsx
    RecordingRecoveryBanner.tsx
```

Meeting 화면은 `recording/public-api`에서 필요한 hook/component를 가져다 쓴다. Meeting 내부에 별도 recorder 구현을 남기지 않는다.

### 4. Processing pipeline is recording-first

공용 pipeline은 다음 순서다.

```text
recording.transcribe
recording.create_raw_transcript_doc
recording.create_minutes_doc
recording.finalize
```

Meeting 전용 insight/action extraction은 기본 pipeline에서 분리한다. Recording이 meeting container에 연결되어 있으면 후속 job으로 실행한다.

```text
recording.meeting.extract_insights
```

이렇게 나누면 Recording 앱에서 만든 일반 음성 메모와 Meeting에 연결된 녹음을 같은 저장/전사/문서화 경로로 처리하면서, Meeting 전용 action item/decision/follow-up 추출은 별도 관심사로 유지할 수 있다.

## Backend Design

### Models

`domains/recording/models.py`

```text
Recording
  id
  workspace_id
  owner_id
  title
  started_at
  ended_at
  duration_sec
  source
  storage_key
  file_size
  mime_type
  status
  progress_pct
  transcript_text
  failure_reason
  raw_transcript_doc_id
  minutes_doc_id
  celery_task_id
  transcribe_started_at
  transcribe_completed_at
  created_at
  updated_at
  trashed_at

RecordingStaging
  id
  workspace_id
  uploaded_by_id
  idempotency_key
  status
  spool_path
  storage_key
  mime_type
  bytes_received
  chunk_count
  highest_seq
  chunks_meta
  duration_sec_estimate
  started_at
  last_chunk_at
  completed_at
  promoted_recording_id
  initial_container_app
  initial_container_type
  initial_container_id

RecordingContainer
  id
  recording_id
  container_app
  container_type
  container_id
  is_primary
  sort_order
  added_by_id
  created_at
```

`MeetingRecording`과 `MeetingRecordingStaging`은 새 canonical 모델로 마이그레이션한다. 전환 중 호환이 필요하면 schema/API serialization 단계에서 `MeetingRecordingOut` 형태로 변환한다.

Meeting에 연결된 녹음은 사용자가 녹음 순서를 명확히 알아야 하므로 `RecordingContainer.sort_order`를 Meeting별 안정 순번으로 사용한다. 기존 Meeting 호환 레이어에서는 이를 `MeetingRecording.sequence_no`로 노출하고, Recording 도메인 전환 시 backfill 값은 `recording_containers.sort_order`로 이전한다. 신규 object key/다운로드 파일명은 녹음 시작 시각 기반(`YYYYMMDDTHHMMSSZ`)으로 만든다.

원본 음성 저장 상태와 후속 처리 상태는 분리한다. v1에서 사용자가 가장 먼저 신뢰해야 하는 상태는 “원본 음성이 안전하게 저장되었는가”이며, 전사/전사 원문 문서/회의록 문서/Meeting insight 생성은 각각 별도 처리 상태로 표시한다.

```text
audio_status = local_only | uploading | saved | failed
transcript_status = pending | transcribing | done | failed
raw_transcript_doc_status = pending | creating | done | failed
minutes_doc_status = pending | creating | done | failed
meeting_insight_status = none | pending | extracting | done | failed
```

### API

`domains/recording/router.py`

```text
POST   /recording/staging
PUT    /recording/staging/{staging_id}/chunks/{seq}
POST   /recording/staging/{staging_id}/complete
GET    /recording/staging
DELETE /recording/staging/{staging_id}

GET    /recording/recordings
GET    /recording/recordings/{recording_id}
PATCH  /recording/recordings/{recording_id}
DELETE /recording/recordings/{recording_id}

GET    /recording/recordings/{recording_id}/playback
GET    /recording/recordings/{recording_id}/media
POST   /recording/recordings/{recording_id}/retry

POST   /recording/recordings/{recording_id}/containers
DELETE /recording/recordings/{recording_id}/containers/{container_id}
```

Listing filters:

```text
view = mine | needs_review | processing | failed | archived
from
to
container_app
container_type
container_id
```

### Meeting compatibility API

기존 Meeting route는 유지한다.

```text
POST   /meeting/meetings/{meeting_id}/recordings/staging
PUT    /meeting/meetings/{meeting_id}/recordings/staging/{staging_id}/chunks/{seq}
POST   /meeting/meetings/{meeting_id}/recordings/staging/{staging_id}/complete
GET    /meeting/meetings/{meeting_id}/recordings/staging
DELETE /meeting/meetings/{meeting_id}/recordings/staging/{staging_id}
POST   /meeting/meetings/{meeting_id}/recordings/import
GET    /meeting/meetings/{meeting_id}/recordings/{recording_id}/playback
GET    /meeting/meetings/{meeting_id}/recordings/{recording_id}/media
POST   /meeting/meetings/{meeting_id}/recordings/{recording_id}/retry
DELETE /meeting/meetings/{meeting_id}/recordings/{recording_id}
```

하지만 내부 구현은 `recording.service`를 호출한다. Meeting별 단일 녹음 lock은 `RecordingStaging.initial_container_app/type/id`가 meeting container를 가리키는 활성 staging 기준으로 계산한다.

### Permission model

Recording 앱 자체는 owner-private 모델을 따른다.

- `/recording/recordings` 목록과 Recording detail은 기본적으로 `recordings.owner_id == current_user.id`인 내 녹음만 보여준다.
- `/recording/recordings?container_app=...&container_type=...&container_id=...`처럼 특정 object의 첨부 녹음을 조회하는 경우에는 owner가 아니라 해당 container object의 권한을 따른다.
- owner는 원본 음성 재생, 제목 변경, retry, 삭제, 연결 대상 추가/해제를 수행할 수 있다.
- 연결 대상 추가는 대상 도메인의 권한 검사를 통과해야 한다. 예를 들어 PMS task에 붙이려면 PMS task attach 권한, Meeting에 붙이려면 Meeting 참가/수정 권한, Docs object에 붙이려면 해당 Docs 권한을 사용한다.
- 녹음이 다른 앱의 object에 첨부된 뒤에는 그 object 화면에서의 노출/재생/검색 권한은 첨부 대상 object의 권한을 따른다. 즉 Recording 앱에서는 owner만 보지만, PMS task나 Meeting 화면에서는 그 object를 볼 수 있는 사용자가 연결된 녹음을 볼 수 있다.
- `/playback`과 `/media`는 owner 또는 접근 가능한 container object가 하나 이상 있는 사용자에게 허용한다. 단, 삭제와 영구 archive는 owner만 수행한다.
- container detach는 owner, attachment를 추가한 사용자, 또는 대상 object에서 attachment 제거 권한이 있는 사용자만 수행한다. 마지막 container가 제거되면 녹음은 다시 owner-private 상태로 남는다.
- 연결되지 않은 녹음과 연결되지 않은 전사/회의록 문서는 owner private ACL을 유지한다.
- Search/RAG projection은 source가 Recording 단독이면 owner ACL, container에 첨부된 문서이면 container object ACL을 적용한다.

## Document Generation

### Raw transcript doc

전사 원문 문서는 가능한 한 ASR 결과를 그대로 보존한다.

- 제목: `전사 원문: {recording title or timestamp}`
- source_app: `recording`
- source_kind: `raw_transcript`
- source_ref: `recording.id`
- 내용:
  - 녹음 시간/길이 metadata
  - segment timestamp가 있으면 `[00:01:23] 발화 내용`
  - speaker 정보가 생기면 speaker label 표시

### Minutes doc

회의록 문서는 요약이 아니라 가독성 정리본이다.

허용되는 변환:

- 긴 전사를 문단으로 나누기
- 시간 순서 유지
- 명시된 주제 전환을 heading으로 분리
- filler, 중복 추임새, 인식 노이즈를 보수적으로 정리
- 명시적으로 말한 결정/액션/이슈를 별도 section으로 재배치

금지되는 변환:

- 말하지 않은 내용 추가
- 불확실한 내용을 사실처럼 작성
- 임의 요약으로 정보 삭제
- 결론/맥락 추측
- 참석자나 발화자 추정

LLM을 사용하는 경우에도 원문 기반 검증을 둔다. 검증이 어려운 경우 deterministic transcript formatter로 fallback한다.

## Frontend UX

### App registration

새 app module:

```text
appId = "recording"
route = /w/:workspaceSlug/recording
detail route = /w/:workspaceSlug/recording/:recordingId
```

Mobile app menu에서 Recording 앱은 빠른 캡처 용도이므로 `Quick Record`를 기본 진입점으로 둔다.

Nav items:

- `recording-quick`: Quick Record
- `recording-mine`: My Recordings
- `recording-review`: Needs Review
- `recording-failed`: Failed / Recovery

### Quick Record

첫 화면의 핵심은 큰 Mic 버튼 하나다.

상태:

- idle
- requesting microphone permission
- recording
- stopping
- uploading
- saved
- recovery needed
- failed

시작 전 입력은 없다. 녹음 종료 후에만 제목 변경, 회의 연결, 태스크 연결, 문서 확인을 제공한다.

### Recording list

기본 정렬은 `started_at desc`.

목록 item은 다음을 보여준다.

- 날짜
- 시작 시간
- duration
- status
- 연결 대상
- 원본/전사/회의록 생성 여부
- 실패 사유가 있으면 retry CTA

### Attach flow

사용자는 Recording detail에서 연결 대상을 추가한다.

v1 대상:

- Meeting
- PMS task
- Docs native doc

Meeting 연결 후보는 녹음 시작/종료 시간과 겹치는 meeting을 우선 제안한다. 자동 attach는 하지 않는다.

## Migration Plan

### Step 0: Preserve current Meeting recording baseline

현재 Meeting 녹음이 이미 사용자 워크플로우에 들어가 있으므로, canonical 전환 전에 다음 동작을 baseline으로 고정한다.

- Meeting 화면에서 녹음 시작/중지 후 원본 음성이 MinIO에 저장된다.
- playback은 same-origin authenticated `/media` stream을 사용한다.
- Meeting별 녹음 순번은 안정적으로 유지된다.
- 원본 음성 저장 상태와 전사/후속 처리 상태는 분리되어 보인다.

### Step 1: Add canonical recording tables and service shell

새 테이블을 추가한다.

- `recordings`
- `recording_staging`
- `recording_containers`

이 단계에서는 새 테이블과 API/service shell을 추가하되, 기존 Meeting write path를 즉시 제거하지 않는다. `recording.service`에는 권한 helper, owner-private 조회, container ACL 조회, same-origin `/media` stream 계약을 먼저 둔다.

### Step 2: Switch new writes through Recording service

Recording 앱의 신규 저장은 `recording.service`를 호출한다. 가장 먼저 direct import endpoint로 원본 음성 저장, owner-private 목록, playback을 닫는다.

Meeting compatibility route가 `recording.service`를 호출하도록 바꾸는 작업은 그 다음 단계로 진행한다. 이 시점부터 신규 Meeting 녹음은 canonical `recordings` / `recording_staging` / `recording_containers`에 기록한다.

전환 배포 중 누락을 막기 위해 다음 중 하나를 명시적으로 선택한다.

- old table read fallback을 유지하고, canonical에 없는 기존 row만 old table에서 읽는다.
- 또는 짧은 전환 기간 동안 old/new dual-write를 유지한다.

### Step 3: Legacy Meeting recording cleanup, no backfill

기존 `meeting_recordings`를 `recordings`로 복사하지 않는다. 기존 녹음을 유지해야 하는 요구가 없으므로 backfill/migration 복잡도를 제거한다.

- old Meeting recording data는 운영 결정에 따라 삭제하거나 archived legacy data로 남긴다.
- 신규 canonical recording과 old Meeting recording을 섞어 보여주는 read fallback을 만들지 않는다.
- Meeting write cutover 이후 old write path가 더 이상 호출되지 않는지 확인한다.

### Step 4: Remove old write path

기존 `MeetingRecording` / `MeetingRecordingStaging`에 대한 신규 write를 중단한다. 필요하면 read compatibility만 임시 유지한다.

## Implementation Stages

### PR 1 - Baseline and backend canonical model

- 이 문서를 추가한다.
- 현재 Meeting 녹음의 저장/playback/순번/상태 분리 동작을 회귀 테스트로 고정한다.
- `domains/recording/models.py`, schema, migration 추가.
- `recording.service` shell, owner-private 권한 helper, container ACL helper 추가.
- `/recording/recordings/{recording_id}/media` 계약과 Meeting wrapper media 계약 추가.
- API registry에 recording router 등록.

검증:

- migration upgrade
- same-origin media stream
- owner-private Recording list
- container ACL 기반 attached recording 조회
- 기존 meeting recording tests가 아직 기존 path로 green

### PR 2 - Recording service extraction and Meeting write cutover

- `meeting/recordings.py`의 공용 로직을 `recording/service.py`로 이동.
- Meeting route는 wrapper로 유지.
- 신규 Meeting recording write는 canonical Recording tables로 전환.
- canonical에 없는 기존 Meeting recording은 read fallback으로 유지하거나, 선택한 dual-write 전략을 적용.
- 기존 `test_meeting_recordings.py`를 공용 service 경유 기준으로 갱신.
- 새 `test_recording_service.py` 추가.

검증:

- staging idempotency
- chunk idempotency/checksum
- complete promotion
- raw audio preservation on enqueue failure
- playback
- retry
- delete cleanup
- meeting wrapper의 녹음 순번(`sequence_no`)과 시작시각 기반 object key
- Meeting별 single-recorder lock이 `RecordingStaging.initial_container_*` 기준으로 동작

### PR 3 - Recording app save management

- Recording app module 추가.
- direct import 저장 API 추가.
- Quick Record 화면 구현.
- 내 녹음 목록, playback, 삭제 관리 구현.
- transcript/raw transcript doc/minutes doc 상태는 pending으로 표시하고 worker enqueue는 하지 않는다.

검증:

- Recording 앱에서 녹음 시작/중지 후 canonical row와 MinIO object 생성
- owner-private list
- same-origin media playback
- delete 후 목록에서 제거
- OpenAPI client regenerated

### PR 4 - Worker pipeline commonization

- `recording.transcribe` 추가.
- `recording.create_raw_transcript_doc` 추가.
- `recording.create_minutes_doc` 추가.
- Meeting insight extraction은 meeting container 후속 job으로 분리.
- 기존 `meeting.*` task는 compatibility wrapper 또는 transition task로 유지한다.
- ASR 모델은 이 단계에서 최종 선택한다. Qwen/Qwen3-ASR-1.7B는 후보로 두되, DeepInfra 제공 여부와 API 계약을 확인한 뒤 연결한다.

검증:

- transcript doc 생성
- minutes doc 생성
- failed queue 상태에서도 원본 보존
- 기존 meeting insight tests green

### PR 5 - Web shared recorder boundary

- `apps/web/src/app-modules/recording/` 추가.
- app registry, manifest, routes, sidebar 추가.
- `recording-api.ts` 추가.
- `recording-db.ts`, `useChunkedRecorder`, `useRecordingRecovery`를 Meeting에서 Recording module로 이동.
- Meeting 화면은 Recording public API를 사용하도록 변경.
- 기존 Meeting IndexedDB recovery data를 새 module에서 계속 읽을 수 있게 호환 유지.

검증:

- web architecture boundary check
- Meeting detail에서 기존 녹음 UX 회귀 없음
- 기존 IndexedDB recovery session 복구

### PR 6 - Recording app UX

- Recording detail 구현.
- IndexedDB chunk 저장 및 recovery panel 구현.
- Attach flow 구현.
- Meeting 화면 recorder를 Recording public API로 이동.

검증:

- 모바일 viewport에서 Quick Record 진입
- 녹음 시작/종료
- reload 후 recovery
- 회의/태스크 attach

### PR 7 - Search/RAG and polish

- 전사/회의록 docs를 검색/RAG 대상으로 sync.
- Recording 자체 검색 projection 추가.
- 실패 상태, retry UX, empty state, i18n 정리.

검증:

- `pnpm generate:api-client`
- `pnpm check:api-contract`
- `pnpm check:api-architecture`
- `pnpm check:web-architecture`
- 필요한 경우 `pnpm nx e2e-shell web`

## Test Plan

### Backend

- staging 생성 idempotency
- chunk upload idempotency
- 같은 seq 다른 payload conflict
- 누락 chunk finalize rejection
- complete 후 Recording 생성과 MinIO 저장 확인
- enqueue 실패 시 raw audio 보존
- playback permission
- playback/media permission은 owner 또는 accessible container object 기준
- retry는 failed recording에만 허용
- delete 시 MinIO object cleanup
- container attach 권한
- container detach 권한
- owner-private Recording list/detail
- container filter 조회는 target object 권한을 따르는지 확인
- meeting wrapper endpoint가 Recording service를 호출하는지 확인
- backfill idempotency와 old-table catch-up

### Worker

- ASR 성공 시 transcript_text 저장
- raw transcript doc 생성
- minutes doc 생성
- minutes doc이 원문 순서를 유지하는지 검증
- LLM 결과가 비어 있거나 검증 실패 시 fallback
- meeting container가 있으면 meeting insight extraction 후속 실행

### Web

- IndexedDB session 저장
- local chunk 복구
- upload resume
- Quick Record start/stop
- Meeting 화면이 공용 recorder hook을 사용
- mobile viewport에서 버튼/텍스트 overflow 없음

## Open Decisions

- PWA install prompt와 홈 화면 바로가기 UX를 v1에 포함할지 여부.
- 원문 전사 doc과 회의록 doc을 Recording detail에서 항상 자동 생성할지, 또는 전사 완료 후 사용자가 생성 버튼을 누르게 할지 여부. 기본값은 자동 생성.
- Meeting에 연결되지 않은 일반 녹음의 minutes doc 제목 규칙. 기본값은 `회의록: {YYYY-MM-DD HH:mm 녹음}`.
- 장시간 녹음의 size limit과 chunk retention 정책. 기본값은 기존 meeting recording 설정을 그대로 사용한다.
- ASR 후보 모델. Qwen/Qwen3-ASR-1.7B는 후보지만, DeepInfra 제공 여부와 운영 비용/latency를 확인한 뒤 결정한다.

## Explicit Non-goals for v1

- 네이티브 iOS/Android 백그라운드 녹음 보장.
- 오프라인 상태에서 무제한 장시간 녹음 보장.
- 자동 회의 attach.
- 화자 diarization 정확도 보장.
- 법적 녹음 동의 워크플로 자동화.
- 기존 Meeting 녹음 backfill.
- 저장/관리 단계에서 Qwen3-ASR 또는 다른 ASR 파이프라인을 즉시 연결.
