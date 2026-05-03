# 07. Live Meeting Cockpit — 회의 라이브 자동화

**유형**: 실행 계획 (전체 비전 청사진, Phase 1–5 분할 실행 예정)
**선행**: `06-recording-app-implementation.md` (canonical recording 파이프라인)
**상태**: 청사진 승인. 실행은 Phase 단위 별도 PR.

---

## 1. Context

현재 recording 앱은 **회의 종료 후에만** 가치를 준다.

- `MediaRecorder.start(1000)` 이 1초 청크를 만들지만, 실제로는 stop 시점에 합쳐서 한 덩어리 Blob 으로 업로드 (`apps/web/src/app-modules/recording/views/RecordingView.tsx:241`).
- ASR (DeepInfra/Cohere/Whisper/Qwen, `apps/api/src/aidoo_api/core/asr.py`) 은 모두 **배치 — 전체 파일 → 전체 텍스트**.
- 정리 파이프라인은 Celery chain `transcribe → raw_doc → summarize → verify → minutes_doc` (`apps/worker/src/aidoo_worker/tasks/recording.py`) 으로 회의가 끝난 뒤에야 작동.

목표는 **회의 중에 살아 움직이는 보조석 (Live Meeting Cockpit)**:

1. **라이브 전사** — 청크가 누적되는 즉시 짧은 윈도우로 ASR 굴려 화면에 흘림 (10–30초 지연 목표).
2. **라이브 노트 정리** — 속기 X. 토픽/결정사항/액션아이템 구조로 LLM 이 점진 갱신. Granola 의 "사용자 메모 + AI 보강" 컨셉을 라이브로 끌어올림.
3. **보조 카드 패널** — 굴러가는 전사를 LLM 분류기로 읽고 "검색 의도" 가 잡히면 자동으로 (a) 웹 검색 (b) 사내 문서 검색 카드를 사이드 패널에 띄움.

### 시장 리서치 (컨셉 융합 근거)

| 서비스 | 라이브 전사 | 라이브 노트 정리 | 인-미팅 웹검색 | 인-미팅 문서검색 |
|---|---|---|---|---|
| Otter | ✓ | 종료 후 요약 + 채팅 | ✗ | ✗ |
| Fireflies | ✓ (요약 15–20분 지연) | 종료 후 | ✗ | ✗ |
| Granola | 디바이스 로컬 STT, 봇 없음 | "사용자 메모 → AI 보강" (종료 후) | ✗ | ✗ |
| Fathom / Read AI | ✓ | 종료 후 | ✗ | 부분 (Read AI cross-system search, 사후) |
| MS 365 Copilot | ✓ | △ | ✗ | ✓ Graph+Semantic Index (사후) |
| **SalesCopilot (논문)** | ✓ | — | — | **✓ 라이브 질문 감지 → DB 검색 → 카드** |

**시장의 빈자리**: 인-미팅 라이브 웹/문서 검색을 동시에 사이드 카드로 띄우는 도구가 없음. SalesCopilot 논문이 가장 가까운 아키텍처 선례.

### 사용자 결정 (확정)

- **범위**: 전체 비전을 단일 청사진에 담고, 실행은 Phase 단위 PR 분할.
- **지연 목표**: 10–30초 윈도우 (신규 ASR 벤더 X, 기존 배치를 잘게 굴림).
- **트리거**: 암묵적 LLM 분류기 (호출어 X) + 수동 입력 박스 (escape hatch).

---

## 2. Architecture / Principles

### 원칙

- **기존 인프라 최대 재사용** — Qdrant, OpenSearch, BlockNote+Yjs, SSE-Starlette, 4종 ASR 백엔드, Celery, MinIO 청크 업로드 API 모두 그대로.
- **기존 post-meeting 파이프라인은 손대지 않음** — `mode` 컬럼으로 분기. 라이브 세션도 종료 시 합친 오디오로 기존 배치 체인을 다시 돌려 최종 transcript/minutes_doc 생성 (라이브 ASR 정확도 < 배치).
- **Granola 하이브리드** — 사용자가 동시에 수기 메모 가능 (Yjs CRDT). LLM 패치는 별도 트랜잭션으로 들어옴.
- **Cost guardrail** — LLM 호출 디바운스 (intent 15s, notes 20s, dedupe-hash 90s 윈도우).
- **Privacy guardrail** — 워크스페이스 설정 `live_external_search_enabled` 기본 off (전사가 외부로 나가는 점 명시 동의).

### 한눈에

```
Browser ── MediaRecorder.start(1000) ── ChunkUploader ──► PUT /staging/{id}/chunks/{seq}
   │                                                                │
   │  SSE  ◄── /recording/live/{rid}/events                         │
   │  Yjs  ◄── y-websocket room "live-notes:{rid}"                  │
   │                                                                ▼
LiveMeetingCockpit (3-pane)                                FastAPI (chunk receiver)
  ├ LiveTranscriptPane     (left, rolling segments)              │ enqueue when window ready
  ├ LiveNotesPane          (center, BlockNote+Yjs)               ▼
  └ LiveCardStackPane      (right, web/doc/manual cards)   Celery worker
       └ ManualQueryInput                                  ┌────────────────────────┐
                                                          │ live_transcribe_chunk  │
                                                          │   (windowed ASR)       │
                                                          └────┬───────────────────┘
                                                               │ publish transcript.delta
                                                               ├──► live_notes_tick (every ~20s, debounced)
                                                               │      → Yjs patch into live notes doc
                                                               └──► intent_tick (every ~15s, debounced)
                                                                      → LiveCard pending → web/doc task
                                                                      → publish card.created/updated
```

### 이벤트 토픽 (Redis pub/sub `live:{recording_id}` → SSE)

- `transcript.delta` `{segments: [{start_ms, end_ms, text}]}`
- `notes.updated` `{native_doc_id}` (Yjs 룸 클라이언트용 핑)
- `card.created` / `card.updated` / `card.dismissed` `{card}`
- `intent.detected` `{intent, query, confidence}` (텔레메트리)
- `live.status` `{phase, latency_ms}`

---

## 3. 구현 단계

### Phase 분할 (PR 단위 자연 경계)

| Phase | 산출물 | 출시 가치 |
|---|---|---|
| **1. 라이브 전사** | 마이그레이션 (Recording/Staging/LiveTranscriptSegment), `/live/start`, 청크 업로더 훅, `live_transcribe_chunk`, SSE 채널 + `transcript.delta`, `LiveTranscriptPane` (단일 컬럼) | "녹음하면서 실시간 자막" |
| **2. 라이브 노트** | `LiveNotesState`, `live_notes_tick`, Yjs 워커 통합, `LiveNotesPane`, 2컬럼 레이아웃 | Granola-라이브 동급 |
| **3. 의도+웹카드** | `live_intent.py`, `core/web_search.py` + Tavily, `LiveCard` 테이블, 웹 카드 작업, `LiveCardStackPane` + `WebSearchCard` + `ManualQueryCard` + 수동 입력 | **시장 차별점** |
| **4. 사내 문서 카드** | `live_doc_search.py`, `DocSearchCard`, Qdrant+OpenSearch RRF 융합 | 풀 비전 완성 |
| **5. 폴리싱** | 화자 라벨, 컨센트 UX, 텔레메트리, 사후 카드 회의록, Brave 폴백 | 운영 품질 |

### 데이터 모델 변경 (`apps/api/src/aidoo_api/domains/recording/models.py`)

기존 확장:
- **`Recording`** + `mode: str default "post"` (`post`|`live`), `live_notes_doc_id: str | None` (FK NativeDoc), `live_started_at`, `live_ended_at`, `live_transcript_status`, `live_notes_status`.
- **`RecordingStaging`** + `mode: str default "post"`, `live_window_count: int default 0`, `last_window_processed_seq: int default -1`.

신규 테이블:
- **`LiveTranscriptSegment`** — `id, recording_id (FK, idx), window_seq, media_offset_ms, end_offset_ms, text, asr_backend, confidence, created_at`. 인덱스 `(recording_id, media_offset_ms)`.
- **`LiveNotesState`** — `id, recording_id (FK unique), state_json (JSONB), last_tick_at, last_processed_offset_ms, version`.
- **`LiveIntentEvent`** — `id, recording_id, kind, query, confidence, rationale, dedupe_hash, created_at`. 인덱스 `(recording_id, dedupe_hash, created_at)`.
- **`LiveCard`** — `id, recording_id (FK, idx), kind (web_search|doc_search|manual), status (pending|ready|failed|dismissed), query, payload_json, source_intent_event_id (nullable FK), created_at, updated_at, dismissed_at, dismissed_by_id`.

마이그레이션: `apps/api/migrations/versions/<ts>_live_meeting_cockpit.py`.

### 백엔드 신규 파일

- `apps/api/src/aidoo_api/core/web_search.py`
  `WebSearchBackend` Protocol (`core/asr.py` 패턴 미러), `TavilyBackend`, `BraveBackend`, `get_web_search_backend()` (settings 의 `web_search_primary` / `web_search_fallback` 참조).
- `apps/api/src/aidoo_api/domains/recording/live_doc_search.py`
  `search_internal_docs(workspace, user, query)` — 기존 `RagQueryService.query()` (Qdrant) + `query_workspace_keyword_search()` (OpenSearch BM25) 호출 후 RRF (k=60) 융합, 상위 5 hit 반환 (ACL 적용).
- `apps/worker/src/aidoo_worker/tasks/live_recording.py`
  `live_transcribe_chunk(staging_id, window_seq)` — MinIO 에서 마지막 N 청크 합쳐 임시 파일로 만들고 `get_asr_backend().transcribe()` 호출. 12s 윈도우, 2s 오버랩. 오버랩 영역은 단어 단위 토큰 diff 로 dedup. `LiveTranscriptSegment` 저장, `transcript.delta` publish, 조건부로 `live_notes_tick` / `intent_tick` 체이닝.
- `apps/worker/src/aidoo_worker/tasks/live_notes.py`
  `live_notes_tick(recording_id)` — Redis SETNX (20s TTL) 디바운스. `LiveNotesState.state_json` + 최근 윈도우를 LLM (`local` 풀, 신규 task `live_notes`) 에 전달, JSON 패치 (`add_topic`, `append_to_topic`, `add_decision`, `add_action_item`, `edit_*`) 받아 state 갱신, BlockNote 블록 트랜잭션으로 투영하여 Yjs 룸에 적용.
- `apps/worker/src/aidoo_worker/tasks/live_intent.py`
  `intent_tick(recording_id)` — Redis SETNX (15s TTL). 마지막 ~45초 텍스트로 LLM 분류 (신규 task `live_intent`): `{intent, query, confidence, rationale}`. confidence < 0.55 드롭. 동일 `dedupe_hash` 90초 내 재발생 드롭. 통과 시 `LiveCard(status="pending")` insert + 카드 작업 체이닝.
- `apps/worker/src/aidoo_worker/tasks/live_cards.py`
  `web_search_card_task` — Tavily 호출, LLM (`live_card_summarize`) 으로 ~3문장 요약 + 출처 리스트, payload 저장, `card.updated` publish. 8s 타임아웃 → `failed`.
  `doc_search_card_task` — `live_doc_search.search_internal_docs()` 호출, 동일 패턴.
  `manual_query_card_task` — 사용자 직접 질의. URL/시사적 키워드 → 웹, 사내 용어 → 문서, 모호 → 둘 다.
- `apps/worker/src/aidoo_worker/yjs_client.py`
  워커가 Yjs 룸에 클라이언트로 접속하는 얇은 래퍼. `pycrdt-websocket` 사용. 의존성은 worker 만 추가.

### 신규 라우트 (`apps/api/src/aidoo_api/domains/recording/router.py` 확장)

- `POST /api/v1/recording/recordings/live/start` → `RecordingStaging(mode="live")` 생성, `live_notes_doc_id` 용 빈 NativeDoc 생성, 양쪽 ID 반환.
- `POST /api/v1/recording/recordings/live/{recording_id}/finish` → 합친 오디오를 기존 `importRecording` 플로우로 전달, 배치 파이프라인 트리거.
- `GET /api/v1/recording/recordings/{recording_id}/live/events` → `EventSourceResponse` (Redis pub/sub `live:{recording_id}` 구독). 기존 `apps/api/src/aidoo_api/domains/ai/router.py:766` 패턴 카피.
- `POST /api/v1/recording/recordings/{recording_id}/live/cards/manual` → 수동 카드 생성.
- `POST /api/v1/recording/recordings/{recording_id}/live/cards/{card_id}/dismiss`
- `GET /api/v1/recording/recordings/{recording_id}/live/cards` → 새로고침 시 카드 하이드레이트.
- 기존 `PUT /api/v1/recording/recordings/staging/{stagingId}/chunks/{seq}` 핸들러에 `if staging.mode == "live" and seq % WINDOW_SIZE == 0: enqueue live_transcribe_chunk` 분기 추가.

### 백엔드 재사용 (수정 없음)

- `apps/api/src/aidoo_api/core/asr.py` `get_asr_backend().transcribe()`
- `apps/api/src/aidoo_api/core/llm.py` `complete_chat()` + `LlmTaskContext` (단, `get_supported_llm_tasks()` 에 `live_notes`, `live_intent`, `live_card_summarize` 3 task 추가)
- `apps/api/src/aidoo_api/domains/rag/query_service.py:RagQueryService.query()`
- `apps/api/src/aidoo_api/domains/search/service.py:query_workspace_keyword_search()`
- `apps/api/src/aidoo_api/domains/docs/rag_sync.py:enqueue_native_doc_rag_sync()` (세션 종료 시 라이브 노트 doc 인덱싱)
- 세션 종료 시: `apps/worker/src/aidoo_worker/tasks/recording.py` 의 기존 chain `transcribe_recording → analyze_transcript → verify_transcript_summary → create_minutes_doc` 그대로 재사용

### 프론트엔드 신규 파일 (`apps/web/src/app-modules/recording/`)

- `views/LiveMeetingCockpit.tsx` — 3-pane Mantine `Grid` (3/6/3 데스크톱, 모바일 탭). MediaRecorder 라이프사이클, 청크 업로더, SSE 연결, Yjs provider 소유.
- `views/live/LiveTranscriptPane.tsx` — 가상화된 롤링 세그먼트 목록 (Mantine `ScrollArea`).
- `views/live/LiveNotesPane.tsx` — 기존 BlockNote 에디터 임베드, Yjs 룸 `live-notes:{recording_id}` 연결. 기본 read-only, "직접 편집" 토글 (Granola 하이브리드). 와이어링 패턴은 `apps/web/src/app-modules/whiteboard/views/WhiteboardEditorSurface.tsx:1103` 의 WebsocketProvider 참조.
- `views/live/LiveCardStackPane.tsx` — 카드 스택 (최신 위로) + 하단 고정 수동 입력.
- `views/live/cards/{WebSearchCard,DocSearchCard,ManualQueryCard,PendingCard}.tsx`
- `views/live/useLiveCockpitStream.ts` — `EventSource` 래퍼 훅 (재연결/백오프). `{transcriptSegments, cards, status}` 노출.
- `views/live/useChunkUploader.ts` — `MediaRecorder.ondataavailable` 스트림을 `seq` 추적하며 PUT, 재시도+백오프, 업로드 지연 메트릭 노출.
- `api/live-recording-api.ts` — `startLiveSession`, `finishLiveSession`, `submitManualQuery`, `dismissCard`, `eventsUrl`, `hydrateCards`.

### 프론트엔드 기존 파일 변경

- `views/RecordingView.tsx` — 기존 빠른 녹음 버튼 옆에 "라이브 코크핏 시작" 버튼 추가 (`POST /live/start` → `/recording/live/:recordingId` 네비게이션).
- 라우팅 진입점 — `/recording/live/:id` 추가.
- `platform/i18n/resources.ts` — 신규 라벨 추가.

---

## 4. Verification

### End-to-End 매뉴얼 테스트

1. **청크+ASR**: 라이브 세션 시작, 30초 발화. ~12초 후 좌측 첫 세그먼트 표시. DB 에 `LiveTranscriptSegment` 가 `media_offset_ms` 0, 10000, 20000 으로 들어왔는지 확인.
2. **라이브 노트**: 두 토픽 도입하는 60초 모놀로그. ~25초 후 중앙 패널에 첫 헤딩, 60초까지 두 토픽 모두 구조화. `LiveNotesState.state_json` 확인 + Yjs doc 갱신 확인.
3. **웹 검색 카드**: "도쿄 인구가 지금 얼마지?" 발화. ~20초 내 `WebSearchCard` 등장. `live_intent_events` + `live_cards` 행 확인.
4. **문서 카드**: "Q3 가격 정책" 제목 doc 미리 생성. "우리 Q3 가격 정책 할인 어떻게 되어 있지?" 발화. ~20초 내 `DocSearchCard` 에 그 doc 1순위 노출.
5. **수동 카드**: 수동 입력 "베를린 날씨" → 즉시 `ManualQueryCard` 결과.
6. **Dismiss**: 카드 dismiss → 행 `status="dismissed"`, 사라짐, SSE 이벤트 관찰.
7. **재연결**: 네트워크 10초 차단. 업로더가 청크 재시도, SSE 자동 재연결. 복구 시 카드는 DB 하이드레이트, 중복 없음.
8. **세션 종료**: 종료 → 배치 파이프라인 실행 → `Recording.transcript_text` 채워짐, minutes_doc 생성, 라이브 노트 doc 그대로 attach.
9. **지연 텔레메트리**: `live.status` p50 < 14s, p95 < 25s.
10. **컨센트 게이트**: `live_external_search_enabled=false` 시 의도는 발화하지만 카드 생성 short-circuit + 배너 노출, 외부 호출 로그 없음.

### 단위 테스트 우선순위

- ASR 윈도우 dedup 알고리즘 (오버랩 영역 토큰 diff)
- intent_tick 디바운스 (15s SETNX + dedupe_hash 90s)
- RRF (k=60) 융합 결과 순위 안정성
- Yjs 패치 적용 후 BlockNote 블록 무결성

---

## 5. 결정 로그

### 완료된 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| ASR | 기존 `core/asr.py` 백엔드 + 12s 슬라이딩 윈도우 (2s 오버랩) | 신규 벤더 도입 X (사용자 결정), 10–30s 지연 목표 충족 |
| 라이브 노트 동기화 | Yjs CRDT (worker 가 Yjs 클라이언트로 참여) | 사용자 동시 편집 가능 (Granola 하이브리드), 기존 BlockNote 스택 재사용 |
| 노트 갱신 방식 | LLM 이 JSON 패치 출력 → BlockNote 블록 투영 | 전체 재작성 대비 안정/속도/비용 우위 |
| 의도 트리거 | 암묵적 LLM 분류기 + 수동 입력 (escape hatch) | 사용자 결정. 호출어 X. 디바운스로 스팸 방지 |
| 카드 저장소 | Postgres `live_cards` 테이블 | 새로고침 후 유지, 사후 회의록 참조, Recording 어그리거트 일관 |
| SSE 전송 | `EventSourceResponse` (`domains/ai/router.py:766` 패턴 카피) | 인프라 추가 X |
| 웹 검색 프로바이더 | Tavily 1차 + Brave 폴백 | LLM 그라운딩 특화, answer+sources 구조가 카드와 정합 |
| 사내 문서 검색 | Qdrant 벡터 + OpenSearch BM25 → RRF (k=60) | 기존 두 인프라 모두 재사용 |
| 컨센트 | 워크스페이스 설정 `live_external_search_enabled` (기본 off) | 전사 외부 송출 명시 동의 |
| 세션 종료 처리 | 합친 오디오로 기존 배치 파이프라인 재실행 | 라이브 ASR 정확도 < 배치. 최종본은 배치로 |

### 차후 결정 (Phase 진입 시)

1. **ASR 윈도우 dedup 토크나이저** — 한국어/영어 혼합 텍스트, sentence-transformers vs whitespace+어절. **Phase 1 구현 중**.
2. **호출어 우회 경로** — "검색해줘"/"찾아봐" 명시 키워드 시 디바운스 건너뛰고 즉시 카드 생성 여부. **Phase 3**.
3. **Yjs 워커 접속 방식** — `pycrdt-websocket` Python 라이브러리 안정성 vs Node 사이드카. **Phase 2 시작 전**.
4. **수동 카드 라우팅** — 휴리스틱 vs LLM 라우터. **Phase 3**.
5. **컨센트 모델 세분화** — 워크스페이스 단위로 충분한지, 미팅별 toggle 필요한지. **Phase 5**.
6. **라이브 노트 doc ↔ minutes_doc 관계** — 종료 후 minutes_doc 이 대체 vs 별개. **Phase 5**.

---

## 6. 롤백 계획

### Phase 1 (라이브 전사) 롤백

- `mode` 컬럼 default `"post"` 라 기존 녹음은 영향 없음.
- `LiveMeetingCockpit` 진입 버튼만 제거하면 사용자가 라이브 모드에 접근할 수 없음.
- DB 마이그레이션 down: 신규 컬럼/테이블 drop. `Recording.mode == "live"` 행이 있다면 batch 파이프라인 재실행으로 정상 후처리 가능.

### Phase 2 (라이브 노트) 롤백

- `LiveNotesPane` 미마운트 + worker `live_notes_tick` 비활성화. `LiveNotesState` 테이블/노트 doc 잔존은 무해 (사용자에게 노출 안 됨).

### Phase 3–4 (카드) 롤백

- `LiveCardStackPane` 미마운트 + worker `intent_tick` / 카드 task 비활성화. 외부 검색 API 호출 즉시 중단.
- `live_external_search_enabled` 워크스페이스 설정 일괄 false 로 강제 가능.

### 비상 차단

- Redis pub/sub 채널 `live:*` 구독자 강제 종료 → 클라이언트는 SSE retry 후 끊김 알림.
- 워커 큐 `live_*` 태스크 routing key 임시 차단 → 큐만 비우면 즉시 멈춤.
- 외부 API 키 회수 (Tavily/Brave) → 카드 task 가 `failed` 로 폴백.
