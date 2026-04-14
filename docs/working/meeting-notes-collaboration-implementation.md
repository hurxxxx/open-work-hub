# Meeting Notes Collaboration Implementation

작성일: 2026-04-14

## 목적

이 문서는 `meeting notes` 를 포함한 Docs 실시간 협업 구현의 현재 구조와 운영 규칙을 남긴다. 나중에 이 영역을 다시 수정할 때 같은 회귀를 반복하지 않도록, 구현 개요보다 `깨지기 쉬운 지점` 과 `디버깅 기준` 을 함께 정리한다.

## 범위

- 포함:
  - native docs
  - meeting notes
  - PMS space docs
- 제외:
  - task description/comments
  - 그 외 `BlockEditor` 사용처

현재 편집 진입점:

- [MeetingWorkspaceView.tsx](../../apps/web/src/components/views/MeetingView/MeetingWorkspaceView.tsx)
- [DocsView.tsx](../../apps/web/src/components/views/DocsView.tsx)
- [SpaceDocsView.tsx](../../apps/web/src/components/views/PMSView/SpaceDocsView.tsx)
- 공용 에디터: [collaborative-block-editor.tsx](../../packages/ui/src/lib/editor/collaborative-block-editor.tsx)

## 전체 구조

실시간 협업은 `BlockNote + Yjs + y-websocket + FastAPI websocket` 조합이다.

데이터 흐름:

1. 클라이언트가 `GET /docs/collab/pages/{page_ref}/session` 으로 room 정보와 현재 `yjs_state` / snapshot blocks 를 받는다.
2. 프런트는 `Y.Doc` 을 만들고, `yjs_state` 가 있으면 apply 한다.
3. 프런트는 `WebsocketProvider(serverUrl, roomKey, ydoc, { params: { token } })` 로 연결한다.
4. `useCreateBlockNote({ collaboration })` 에 `fragment`, `provider`, `user` 를 넘겨 BlockNote 를 협업 모드로 띄운다.
5. 사용자가 편집하면 Yjs update 는 websocket 으로 즉시 동기화된다.
6. 별도로 2초 debounce 후 `PUT /docs/collab/pages/{page_ref}/snapshot` 으로 snapshot 과 `yjs_state` 를 저장한다.

중요:

- `snapshot PUT` 은 영속화 경로다.
- `websocket sync` 는 실시간 전파 경로다.
- `snapshot` 이 잘 저장된다고 해서 `실시간 sync` 가 정상이라는 뜻은 아니다.

## 백엔드 구조

핵심 파일:

- [collab.py](../../apps/api/src/aidoo_api/domains/docs/collab.py)
- [router.py](../../apps/api/src/aidoo_api/domains/docs/router.py)
- [models.py](../../apps/api/src/aidoo_api/domains/docs/models.py)
- migration: [9d26f5a7c1b4_add_docs_collab_documents.py](../../apps/api/alembic/versions/9d26f5a7c1b4_add_docs_collab_documents.py)

핵심 개념:

- `page_ref`
  - `native_doc_page__{id}`
  - `pms_space_doc_page__{id}`
- `room_key`
  - `native_doc_page:{id}`
  - `pms_space_doc_page:{id}`
- 영속 테이블: `docs_collab_documents`
  - `room_key`
  - `source_type`
  - `source_page_id`
  - `yjs_state`
  - `snapshot_content_blocks`
  - `last_snapshot_at`

핵심 엔드포인트:

- `GET /api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session`
- `PUT /api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/snapshot`
- `WS /api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/ws`

인증:

- 현재 주 경로는 websocket query param token 이다.
- 서버는 [router.py](../../apps/api/src/aidoo_api/domains/docs/router.py) 의 `_resolve_collab_ws_token()` 에서 `query token` 을 우선 받고, 없으면 첫 프레임 auth handshake fallback 을 사용한다.

room lifecycle:

- `DocsCollabHub.get_room()` 이 room 단위 singleton 을 유지한다.
- room 은 `YRoom.start()` background task 로 시작한다.
- room 이 비면 `cleanup_room()` 이 stop 한다.

closed socket 처리:

- ypy-websocket fan-out 중에는 이미 끊긴 client 로 send 가 자연스럽게 발생할 수 있다.
- [collab.py](../../apps/api/src/aidoo_api/domains/docs/collab.py) 의 `FastAPIYjsWebsocket.send/close` 는 `WebSocketDisconnect`, `ClientDisconnected` 를 정상 teardown 으로 흡수한다.

## 프런트 구조

핵심 파일:

- [collaborative-block-editor.tsx](../../packages/ui/src/lib/editor/collaborative-block-editor.tsx)
- [docs-api.ts](../../apps/web/src/domains/docs/docs-api.ts)

현재 구현 규칙:

- websocket provider 는 `params: { token: authToken }` 방식으로 생성한다.
- `session.yjsState` 가 있으면 그것으로 `Y.Doc` 을 복원한다.
- `session.yjsState` 가 없는 새 문서만 `initialContent` fallback 으로 부팅한다.
- snapshot 저장은 `editor.onChange()` 기준 2초 debounce 다.

주의:

- custom `EventTarget` websocket wrapper 는 다시 도입하지 않는다.
- `y-websocket` 이 기대하는 네이티브 `WebSocket` 수명주기를 건드릴수록 깨질 확률이 높다.

## 2026-04-14 회귀 원인

증상:

- session API 는 `200`
- 에디터는 화면에 보임
- 로컬 입력은 됨
- 다른 탭으로는 실시간 반영이 안 됨

실제 원인:

- [collaborative-block-editor.tsx](../../packages/ui/src/lib/editor/collaborative-block-editor.tsx) 의 cleanup 에서 live `provider.disconnect()` 와 `ydoc.destroy()` 를 즉시 실행하고 있었다.
- 개발 환경의 React `StrictMode` 는 mount 직후 effect cleanup 을 한 번 더 돌린다.
- 그 cleanup 이 실사용 provider 에 적용되면서 provider 가 `shouldConnect=false` 상태로 죽었다.
- 결과적으로 session/snapshot API 는 계속 성공하지만 websocket sync 는 살아나지 않았다.

현재 수정:

- provider lifecycle effect 에서 `provider.connect()` 를 명시적으로 호출한다.
- cleanup 은 `setTimeout(0)` 지연으로 등록한다.
- 다음 setup 이 바로 이어지면 pending cleanup 을 취소한다.

이 규칙은 매우 중요하다.

- `collaboration provider` 와 `Y.Doc` 은 dev `StrictMode` 에서 즉시 파괴하면 안 된다.
- cleanup 을 단순 `return () => destroy()` 로 쓰면 다시 회귀할 가능성이 높다.

## 다시 깨뜨리지 않기 위한 규칙

1. `provider.disconnect()` / `provider.destroy()` / `ydoc.destroy()` 를 effect cleanup 에서 즉시 호출하지 않는다.
2. websocket auth 는 `params token` 주 경로를 유지한다.
3. closed websocket send/close 예외는 정상 종료로 취급한다.
4. `snapshot PUT` 성공을 실시간 sync 성공으로 오해하지 않는다.
5. meeting/docs/pms 진입점 셋 모두 동일한 공용 `CollaborativeBlockEditor` 를 사용하도록 유지한다.
6. `task description/comments` 같은 비문서 에디터에는 이 provider lifecycle 을 섞지 않는다.

## 디버깅 체크리스트

실시간 동기화가 안 될 때는 아래 순서로 본다.

1. `GET /docs/collab/pages/{page_ref}/session` 이 `200` 인지 확인
2. websocket 연결이 실제로 `101/accepted` 되는지 서버 로그 확인
3. 두 탭이 같은 `room_key` 를 쓰는지 확인
4. 한 탭 입력이 다른 탭 `.bn-editor` 텍스트/DOM 에 반영되는지 확인
5. `PUT /snapshot` 만 계속 성공하고 websocket 반영이 없다면 provider lifecycle 문제를 우선 의심
6. backend 로그에 closed websocket send 예외가 연속으로 뜨는지 확인

실전 팁:

- BlockNote 는 accessibility snapshot 만으로 판정하면 헷갈릴 수 있다.
- 최종 판정은 브라우저 실제 화면 또는 `.bn-editor` 텍스트/DOM 기준으로 한다.

## 수동 검증 기준

로컬 기준 URL:

- `http://127.0.0.1:4200/w/hq/meeting/e1a27370-499d-4740-b82a-b3bae5882872`

권장 확인:

- 탭 A 입력이 탭 B 에 즉시 보이는지
- 탭 B 입력이 다시 탭 A 에 즉시 보이는지
- 두 탭 모두 새로고침 후에도 같은 내용으로 복원되는지
- `Open in Docs` 로 연 동일 문서가 meeting route 와 같은 room 을 쓰는지

## 후속 개선 후보

- snapshot materialization 을 client debounce 가 아니라 server-side update 기반으로 옮기기
- websocket auth 를 지금처럼 token param 으로 유지하되, provider-specific auth 표준화 재검토
- multi-instance 운영이 필요해지면 room fan-out / relay 구조 추가

## 참조

- 상태 메모: [PR1-STATUS.md](../../PR1-STATUS.md)
- 계획 문서: [MEETING-APP-PLAN.md](../../MEETING-APP-PLAN.md)
- BlockNote collaboration docs: https://www.blocknotejs.org/docs/features/collaboration
- BlockNote Yjs utilities: https://www.blocknotejs.org/docs/reference/editor/yjs-utilities
- Yjs y-websocket docs: https://docs.yjs.dev/ecosystem/connection-provider/y-websocket
