# Phase 2 — Agent Event Envelope + Streaming Chat UI

## Context

### 왜 지금 하는가
- Phase 1으로 정책/감사/워크스페이스 격리는 들어갔지만, 사용자 경험은 여전히 동기식 `/ai/chat` 한 번 왕복이다. 긴 응답(회의 요약 재질문, 보고서 초안)에서 체감 지연이 커서 내부 도그푸딩이 막혀 있다.
- Phase 3(tool calling)·Phase 4(write/approval) 도입 시 프론트 상태 모델을 또 갈아엎지 않으려면, **agent-aware event envelope 계약을 구현 전에 먼저 확정**해야 한다. 지금 envelope 없이 스트리밍만 붙이면 P3에서 tool_call·approval 타입이 들어올 때 훅/컴포넌트가 다시 찢어진다.
- mlx-lm은 OpenAI-compatible `chat.completions` 스트리밍을 이미 지원한다. OpenRouter도 동일 계약. 지금 provider-agnostic adapter를 만들 타이밍이다.

### 현재 코드 기준 사실
- [apps/api/src/aidoo_api/domains/ai/router.py:114-129](../apps/api/src/aidoo_api/domains/ai/router.py#L114-L129): `/ai/chat`은 `complete_chat` 한 번 호출 후 JSON 반환. 스트리밍 진입점·SSE 라이브러리 모두 없음.
- [apps/api/src/aidoo_api/core/llm.py:499-609](../apps/api/src/aidoo_api/core/llm.py#L499-L609): `complete_chat(...)`은 항상 non-stream `client.chat.completions.create(**payload)`. `stream=True` 분기 없음.
- [apps/web/src/components/views/AIView.tsx:241-309](../apps/web/src/components/views/AIView.tsx#L241-L309): 챗 전송이 `fetch` 1회 + `setTurns` 1회로 끝. `useChatStream` 훅도, delta 파서도, Thinking 패널도 없음.
- [apps/api/src/aidoo_api/domains/docs/collab.py](../apps/api/src/aidoo_api/domains/docs/collab.py)·[docs/router.py](../apps/api/src/aidoo_api/domains/docs/router.py)에 WebSocket 구축 경험은 있음 → lifespan/shutdown 패턴 참고 가능.
- `reasoning_effort`는 request 파라미터에만 존재한다. mlx-lm 쪽은 `extra_body.think`, external은 `extra_body.reasoning.effort`로 분기된다([llm.py:644-654](../apps/api/src/aidoo_api/core/llm.py#L644-L654)). 스트리밍에서 thinking delta를 분리해 내보내려면 provider별 응답 구조 차이를 흡수하는 adapter가 필요.
- 로드맵 Phase 2 블록: [`plans/00-ai-platform-roadmap.md`](./00-ai-platform-roadmap.md) (Phase 2 섹션).

### 목표
- **AgentEventEnvelope 계약**(pydantic 모델)을 먼저 확정하고 단위 테스트로 고정한다. tool/approval 타입은 이번 Phase에서 **발행하지 않되 타입은 정의해 둔다**.
- `POST /api/v1/ai/chat/stream`을 추가하여 `content_delta`·`reasoning_delta`·`usage`·`done`·`error`를 SSE로 흘린다. 기존 `/ai/chat` 동기 엔드포인트는 회귀 없이 유지.
- provider-agnostic adapter(`core/llm_adapters.py`)로 local(mlx-lm) / external(OpenRouter) delta를 같은 envelope로 정규화한다.
- 프론트 `useChatStream` 훅 + ChatThread / ThinkingPanel / MessageBubble 컴포넌트로 실시간 렌더 + 취소 지원.
- **Phase 1 정책/감사 경계 유지**: 스트리밍 경로도 `LlmTaskContext` 빌드 → `choose_pool` → audit 커밋을 통과한다. PII 강제 local, no cross-pool fallback은 스트리밍에도 그대로 적용된다.

### 범위
- API `ai` 도메인의 스트리밍 엔드포인트, envelope 모델, adapter
- 웹 챗 뷰 재작성 + 공유 훅·컴포넌트
- 디자인 세션 결과물(DESIGN.md) 반영 — P3 ToolCallCard·P4 ApprovalModal 프레이밍까지 선행
- SSE 의존성(`sse-starlette`) 추가

### 비범위
- tool calling 실행 파이프라인(P3)
- ApprovalModal 실제 승인 플로우(P4)
- 히스토리 영속화(P3 또는 별도 플랜) — 이번엔 기존 클라이언트 in-memory 대화 모델을 유지
- 관리자 UI·Admin 탭(P6)
- RAG / ACL projection(P5)
- ASR 전환

### 예상 작업 기간
- 구현 + 테스트 + 디자인 반영까지 `3~4일` (디자인 세션 별도 반나절)

## Architecture / Principles

### 핵심 원칙
1. **Envelope-first**: SSE wire format은 `{type, seq, data}` 고정. 타입이 새로 생길 때 기존 consumer가 unknown-type을 무시하면 되는 방식. seq는 모노톤 증가해 취소/재접속 시 디버깅이 가능.
2. **정책/감사는 동기 경로와 동일**: 스트리밍 라우트도 `complete_chat_stream(...)` wrapper 하나만 쓰고, wrapper가 `choose_pool`·`audit`·`timeout`을 책임진다. 라우트에서 provider SDK를 직접 만지지 않는다.
3. **Thinking/Content 분리는 adapter 책임**: mlx-lm은 `choice.delta.reasoning_content`, OpenRouter는 provider별로 `choice.delta.reasoning` 또는 `choice.delta.content` + meta 토큰으로 내려온다. 라우트·프론트는 이 차이를 보지 않는다.
4. **취소는 disconnect-driven**: 서버는 client disconnect을 감지해 provider generator를 닫고 audit에 `status="cancelled"`를 남긴다. 별도 cancel 엔드포인트는 만들지 않는다.
5. **No cross-pool fallback** — Phase 1 원칙 유지. 스트리밍 중 provider error가 나면 `error` envelope + audit error + 503으로 끝내고 대체 풀로 넘기지 않는다.
6. **Raw prompt/content는 audit에 저장하지 않는다** — 스트리밍에서도 동일. delta 누적은 서버 메모리에만, usage/latency/status만 커밋.

### 새 개념

#### `AgentEventEnvelope` (pydantic `Annotated[Union, Discriminator("type")]`)
공통 필드: `seq: int`, `type: Literal[...]`, `timestamp_ms: int`.

이번 Phase 발행 대상:
- `content_delta` — `{text: str}`
- `reasoning_delta` — `{text: str}`
- `usage` — `{prompt_tokens, completion_tokens, total_tokens}`
- `done` — `{finish_reason: Literal["stop","length","cancelled","error"], audit_id: str | None}`
- `error` — `{code: str, message: str, retryable: bool}`

타입만 정의하고 발행은 하지 않음(추후 Phase에서 활성화):
- `tool_call_started` — `{call_id, name, args_preview}` (P3)
- `tool_call_args_delta` — `{call_id, delta}` (P3)
- `tool_result` — `{call_id, status, result_preview, error}` (P3)
- `approval_required` — `{approval_id, tool, resource_preview}` (P4)
- `approval_resolved` — `{approval_id, decision}` (P4)

#### `ChatStreamRequest` (route 입력)
`ChatRequest`와 동일 shape에 `stream_reasoning: bool = True`만 추가. 나머지(messages/temperature/max_tokens/reasoning_effort/backend_mode/model)는 재사용.

#### `LlmStreamAdapter` (Protocol)
- `open_stream(client, payload) -> Iterator[StreamChunk]`
- `StreamChunk` = dataclass `{kind: Literal["content","reasoning","usage","done"], text: str | None, usage: dict | None, finish_reason: str | None}`
- 구현체 `MlxLmStreamAdapter`, `OpenRouterStreamAdapter`. `_build_extra_body_for_pool` 결과와 동일한 계약으로 호출.

#### 서버 SSE 프레이밍
- `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- 각 이벤트는 `event: <type>\ndata: <json>\n\n` 형태. `sse-starlette`의 `EventSourceResponse` 사용.
- 25초마다 keepalive comment(`: keepalive`) 전송. 차단된 프록시에서 idle kill 방지.

### 인증·워크스페이스 계약
- `/ai/chat/stream`은 기존 `ai_router` 2중 mount(legacy / `/workspaces/{slug}/ai`)에 **그대로 들어간다**. 즉 `require_current_user` + workspace membership dependency를 동일하게 거친다.
- `LlmTaskContext` 빌더는 `/ai/chat`과 동일한 `_build_task_context(current_user, request)`를 재사용한다(동일 파일의 helper 공유).
- 무인증 401 / 무워크스페이스 403 회귀 테스트를 스트리밍 엔드포인트에도 추가.

### 감사 기록 규칙 (스트리밍 특이사항)
- **단일 audit row per stream**. chunk마다 기록하지 않는다.
- 스트림 종료 시점(정상 done / error / cancelled)에 한 번 `log_llm_call`.
  - `status="ok"` — finish_reason ∈ {stop, length}
  - `status="error"` — provider 또는 adapter 예외
  - `status="cancelled"` — client disconnect로 generator close
- `latency_ms` = first byte → done 기준이 아니라 **기존처럼 요청 시작 → 종료**. 별도 `first_token_ms`는 이번에 추가하지 않고 로드맵의 "운영 모니터링 UI" 단계에서 결정.
- `usage`는 provider가 스트림 말미에 주는 값을 그대로 저장. 일부 provider는 usage를 안 주기도 하므로 missing을 허용(Phase 1과 동일).

## 구현 단계

### 1. 디자인 세션 선행 (코드 전)
담당: 디자이너 or `/design-consultation`
산출물:
- DESIGN.md 초안 업데이트 (챗 뷰 전용). 최소 다음을 포함:
  - Message bubble 타이포/여백/색(토큰 기준)
  - Thinking panel 접힘/펼침 + 상태(“생각 중…”, “완료”) 전환
  - Tool call card 자리(미구현, frame만) — P3 대비
  - Approval modal 자리 — P4 대비
  - 로딩/취소/에러 상태 화면
- 의사결정 로그에 "DESIGN.md 업데이트 완료" 엔트리.

완료 기준: 디자이너 승인된 DESIGN.md가 main에 있거나, 최소 이 Phase 내 PR로 합류.

### 2. AgentEventEnvelope 계약 확정 (구현 전)
수정/신규 파일:
- `apps/api/src/aidoo_api/domains/ai/events.py` 신규 — pydantic envelope 정의 + discriminator
- `apps/api/src/aidoo_api/domains/ai/events_schema.md` 신규 — 간단 예제 JSON + 필드 설명
- `apps/api/tests/test_ai_events.py` 신규 — envelope 직렬화·round-trip·unknown type 무시 테스트

작업:
- `AgentEventEnvelope` Annotated Union + `seq`/`timestamp_ms` 자동 필드
- helper `make_envelope(type, seq, data)` 단일 생성 함수 (직접 dict를 만들지 못하게)
- `Envelope.json_schema()` 스냅샷 테스트로 계약 변화 감지

완료 기준: envelope 스키마 스냅샷 테스트 green. tool/approval 타입도 정의만 존재하고 발행 코드는 없음.

### 3. `core/llm_adapters.py` 신규
수정 파일:
- `apps/api/src/aidoo_api/core/llm_adapters.py` 신규
- `apps/api/src/aidoo_api/core/llm.py` — `complete_chat_stream(...)` 신규 함수 추가(기존 `complete_chat`은 건드리지 않음)

작업:
- `StreamChunk` dataclass + `LlmStreamAdapter` Protocol
- `MlxLmStreamAdapter`, `OpenRouterStreamAdapter` 구현
  - `reasoning_content`(mlx-lm) ↔ `reasoning`(OR) 정규화
  - content delta 빈 문자열/None을 `StreamChunk`로 올리지 않는 필터링
  - 마지막 chunk에서 usage·finish_reason 추출
- `complete_chat_stream(context, db, *, messages, ..., pool_hint)`:
  - `choose_pool` → `get_pool_client(pool)` → adapter lookup
  - `stream=True` 로 OpenAI SDK 호출
  - `Iterator[StreamChunk]` yield
  - 종료 시 audit 1회 커밋(함수 내부 try/finally)
  - client disconnect(`asyncio.CancelledError` or generator close)은 `status="cancelled"` 로 audit
  - provider error는 `OpenAIError` 그대로 raise, audit 커밋 후 re-raise

완료 기준:
- local·external 둘 다 adapter fake로 end-to-end 단위 테스트 가능
- `complete_chat`(non-stream)은 기존 계약 그대로 유지

### 4. `/api/v1/ai/chat/stream` 라우트
수정 파일:
- `apps/api/src/aidoo_api/domains/ai/router.py`
- `apps/api/pyproject.toml` — `sse-starlette` 의존성 추가 (`>=2.1,<3.0`)
- `apps/api/uv.lock` 재생성

작업:
- `ChatStreamRequest` 모델 (`backend_mode`는 `"auto" | "local"`만 허용 — Phase 1과 동일, `openrouter` 400)
- `@router.post("/chat/stream", response_class=EventSourceResponse)` 핸들러
- `complete_chat_stream` iterator를 envelope로 감싸 `async for event in ...: yield event.as_sse()` 형태
- 25초 keepalive: `EventSourceResponse`의 `ping=25`
- provider error → 최종 `error` envelope 발행 후 generator close (HTTP status는 200 유지, 실패는 envelope로 표현)
- client disconnect 시 iterator가 `GeneratorExit`로 닫히고 wrapper가 audit에 cancelled 기록

완료 기준:
- 동일 엔드포인트에 legacy `/api/v1/ai/chat/stream` + slug `/api/v1/workspaces/{slug}/ai/chat/stream` 둘 다 mount
- 무인증 401 / 무워크스페이스 403 회귀 테스트 green
- `backend_mode=openrouter` → 400 회귀 테스트 green

### 5. 프론트 스트리밍 훅 + 컴포넌트
수정/신규 파일:
- `apps/web/src/domains/ai/ai-api.ts` — `streamAiChat(payload, token, { signal })` 헬퍼 + envelope 타입
- `apps/web/src/domains/ai/useChatStream.ts` 신규
- `apps/web/src/components/views/AIView.tsx` — 기존 `handleSubmit`을 훅 사용으로 치환
- `apps/web/src/components/views/ChatThread.tsx` 신규 (추출)
- `apps/web/src/components/views/MessageBubble.tsx` 신규 (추출)
- `apps/web/src/components/views/ThinkingPanel.tsx` 신규
- `apps/web/src/constants` 또는 feature flag로 **stream toggle**(기본 on, fallback off)

작업:
- `fetch(..., { signal })` + `ReadableStream` + `TextDecoderStream` 또는 `eventsource-parser` 패키지 중 하나 선택 (뒤쪽이 SSE 파싱 견고). 결정은 구현 시 벤치마크로 확정.
- `useChatStream` 상태:
  - `contentBuffer: string`
  - `reasoningBuffer: string`
  - `usage: Usage | null`
  - `status: "idle" | "streaming" | "cancelled" | "error" | "done"`
  - `abort()` — AbortController.abort()
- AgentEventEnvelope 타입은 API와 1:1. unknown type은 `console.debug` + 무시.
- 취소 UI: 전송 버튼이 streaming 중 “중단” 버튼으로 바뀜.
- 에러 표시: 기존 `chatError` 자리에 `error` envelope 메시지 노출.

완료 기준:
- `content_delta`/`reasoning_delta` 실시간 렌더. thinking 패널은 기본 접힘, 토글로 펼쳐서 reasoning 누적 확인 가능.
- AbortController → 서버 disconnect → audit `cancelled` 관측.
- 기존 동기 호출 경로(`sendAiChat`)는 **삭제하지 않고** 남겨두어 fallback UI 가능성 유지.

### 6. Phase 3 대비 자리 확보 (코드 변경은 최소)
수정 파일:
- `apps/web/src/components/views/ToolCallCard.tsx` 신규 — 타입만 받아 렌더는 `null` 반환(placeholder)
- `apps/web/src/components/views/ApprovalModal.tsx` 신규 — placeholder

작업: envelope의 tool/approval 이벤트 타입을 훅에서 받아 버퍼에만 쌓아두고 기본 컴포넌트에 전달. 실제 렌더는 비워두되 타입·props·이벤트 라우팅을 고정한다. Phase 3 작업이 **envelope 확장이 아니라 컴포넌트 내부만 채우는 것으로** 끝나는지를 코드 리뷰로 확인.

## Verification

### 단위 테스트
- [apps/api/tests/test_ai_events.py] — envelope 직렬화, discriminator 동작, unknown type 무시
- [apps/api/tests/test_ai_stream.py] 신규 — fake adapter로
  - (a) content/reasoning delta 순서 보존
  - (b) provider error 시 `error` envelope 발행 + audit `status=error`
  - (c) client disconnect simulate(`anyio.move_on_after`) 시 audit `status=cancelled`
  - (d) `backend_mode=openrouter` → 400
  - (e) local_only 정책 + local 실패 → error envelope, external 호출 0회
- [apps/api/tests/test_llm_adapters.py] 신규 — mlx-lm vs OpenRouter raw chunk 픽스처를 envelope로 동일 정규화
- 웹: `apps/web/src/domains/ai/useChatStream.test.ts` — mock SSE로 상태 전이 검증

### 마이그레이션 검증
- 없음 (Phase 2는 스키마 변경 없음). `test_alembic_check_reports_no_model_drift`는 기존 상태 그대로 유지 확인.

### 수동 검증
1. local pool 정상, policy=`local_only`에서 `/ai/chat/stream` → 토큰 스트림 + thinking 패널 업데이트.
2. 네트워크 탭에서 SSE `content_delta`/`reasoning_delta`/`done` 프레임 직접 확인.
3. 스트리밍 도중 “중단” 클릭 → 서버 로그 `cancelled`, audit row `status=cancelled`.
4. provider error 재현(local pool URL 오프라인) → `error` envelope + UI 에러 배지.
5. `backend_mode=openrouter` 강제 요청 → UI가 적절히 fallback하거나 400 표시.
6. 기존 `/ai/chat` 동기 호출은 회귀 없이 정상 동작.
7. `/readyz`·`/ai/health`는 Phase 1 계약 그대로.

### 성능 체크 (가벼운 스모크)
- local mlx-lm 기준 first content_delta 200ms 이내(사전 prefill 포함) 확인.
- 1024 토큰 응답 끝까지 keepalive 25s 내에서 끊김 없이 수신.
- 단순 부하 5 concurrent stream에서 audit 누락 0건 확인(local 한정).

## 결정 로그

### 이번 Phase에서 확정
- Envelope wire format은 SSE + `{type, seq, data, timestamp_ms}` 고정.
- tool/approval 타입은 정의만 하고 발행 X. Phase 3/4에서 envelope 확장이 아닌 **발행 활성화 + UI 컴포넌트 구현**만으로 완료되어야 한다.
- 스트리밍 audit은 stream 종료 시 1회 커밋. per-chunk 기록 안 함.
- 취소 엔드포인트 별도 추가 X. disconnect-driven.
- local 실패 시 external 재시도 없음(Phase 1 원칙 유지).
- `reasoning_effort=none`은 thinking delta 발행 X (`stream_reasoning=false`와 동일 효과로 처리).

### 구현 중 열어둘 결정
- SSE 파싱 라이브러리(`eventsource-parser` vs raw `TextDecoderStream`). 벤치마크 후 결정.
- `done` envelope의 `audit_id` 채움 여부 — audit row id를 내려 디버깅 편의를 주되, 관리자만 유의미하므로 권한별 마스킹 필요할 수도. 결정은 PR 단계.
- 프론트 thinking 패널 기본 접힘/펼침. 디자인 세션 결과에 따름.
- `first_token_ms` 측정 & 저장 여부 — 운영 모니터링 UI(P6) 시점에 재검토.
- Envelope에 `meta: {policy, chosen_pool, forced_local, pii_hits}`를 포함해 동기 응답처럼 풀/정책 배지를 렌더할지 여부. 기본은 **`done` envelope의 meta 필드에 포함**으로 가되 PR에서 최종 확정.

## 롤백 계획

### 코드 롤백
- `/ai/chat/stream` 라우트 + `events.py` + `llm_adapters.py` + stream 호출부 revert.
- 프론트 `useChatStream` 훅·컴포넌트 revert, 기존 동기 `sendAiChat` 경로는 남아 있으므로 UI는 바로 이전 모드로 동작.
- `sse-starlette` 의존성 제거.

### DB 롤백
- 스키마 변경 없음 → 없음.

### 설정 롤백
- 없음 (feature flag만 off로).

### 운영 롤백 기준
- SSE 프록시/LB 호환 이슈로 상당수 사용자에게 끊김 발생
- audit 누락·중복으로 컴플라이언스 이슈
- stream 중단 후 서버 generator가 누수되어 메모리/커넥션 고갈

### 롤백 후 상태
- 동기 `/ai/chat`만 사용. Phase 1 계약은 그대로 유지되므로 정책/감사/격리에는 영향 없음. 원인 해결 후 Phase 2 재적용.
