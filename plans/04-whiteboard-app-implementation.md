# Whiteboard App Implementation Plan

> 문서 성격: Docs와 동등한 first-class entity로서 **Whiteboard 앱**을 추가하는 실행 계획.
> 범위: Excalidraw 기반 화이트보드/다이어그램 캔버스를 자체 도메인으로 신설하고, Docs와 동일한 방식으로 PMS 등 컨테이너에 부착될 수 있도록 한다.

## Context

현재 시스템은 `domains/docs/`가 텍스트 문서를 first-class entity로 다루며 `NativeDocContainer`를 통해 PMS, Meeting 등 임의의 컨테이너에 부착된다. PMS UI에서는 "Docs" 탭으로 노출되어 워크스페이스/태스크 단위로 문서가 관리된다.

새로운 요구는 **자유 캔버스(화이트보드 + 다이어그램 + 메모)**를 같은 방식으로 다루는 것이다. 사용자는 PMS의 워크스페이스/태스크 안에서 "Whiteboard" 탭을 통해 화이트보드 목록을 보고, 개별 화이트보드를 열고, 댓글·공유·검색을 Docs와 동일한 멘탈 모델로 사용해야 한다.

**왜 Docs 안의 부가 기능이 아니라 별도 앱인가**
- PMS 탭 자리에 Docs와 동등하게 노출되어야 함 (사용자가 "화이트보드 모음"을 직접 다루는 1급 객체로 인식)
- 화이트보드는 페이지 트리/블록 구조가 아니라 단일 무한 캔버스 — Docs의 `NativeDocPage` 모델과 의미가 다름
- Excalidraw 씬(JSON)은 Docs의 `content_blocks`와 호환되지 않음 (스키마, 직렬화, Yjs 바인딩 모두 다름)
- 검색·RAG·공유 같은 인프라는 공유하되, 본체는 분리하는 것이 코드 단순성과 향후 일반화 양쪽에 유리

**선택한 라이브러리**
- **Excalidraw** (`@excalidraw/excalidraw`, MIT) — 상업적 사용 자유, 임베드 친화적, Yjs 통합 사례 풍부
- tldraw 검토 결과 proprietary 라이센스로 production 사용 시 별도 commercial 라이센스 필요 → 현 단계에서는 부적합

**용어**
- 도메인/엔티티 이름: `Whiteboard` (단수). 사용자 UI 라벨도 "Whiteboard / 화이트보드".
- "캔버스(scene)"는 화이트보드 내부의 그리기 영역을 가리키는 기술 용어로만 사용 (Excalidraw scene JSON과 매칭).

## 2026-05-02 Current Status

최근 구현 커밋 기준으로 Whiteboard는 first-class workspace app, hub/editor UX, 기본 협업 흐름까지 반영되어 있다.

- 완료/대부분 완료: backend whiteboard 도메인 skeleton/CRUD/container/access, web app shell 등록, Whiteboard hub/editor, Excalidraw scene 저장/로드, Yjs 기반 협업 경로, 기본 share/export/item preference 표면.
- 부분 완료: PMS와의 컨테이너 연결은 기반이 있으나, PMS 태스크 상세의 명시적 `Whiteboard` 탭과 태스크 컨텍스트 복귀 UX는 아직 완료 기준으로 보지 않는다.
- 남은 핵심 작업: RAG/search sync, 비로그인 link share read-only 진입, PMS task detail Whiteboard tab, 서버 측 export/thumbnail, Playwright E2E.
- 검증 주의: `uv run python -m pytest tests/test_whiteboard_*.py`는 로컬 Docker daemon 권한 문제로 `postgres:18` pull 단계에서 막힐 수 있다. 코드 실패로 단정하지 말고 Docker 접근 권한을 먼저 확인한다.

## Architecture / Principles

### 1. Docs 도메인과 평행 구조 (parallel mirror)

`domains/whiteboard/`를 `domains/docs/`와 동일한 모듈 구성으로 신설한다.

```
domains/whiteboard/
  __init__.py
  models.py          # Whiteboard, WhiteboardContainer, *Share, CollabDocument
  service.py
  router.py
  access_grants.py   # docs.access_grants 패턴 mirror
  collab.py          # Yjs realtime (Excalidraw scene)
  collab_codec.py    # Excalidraw scene <-> Yjs doc 변환
  rag_sync.py        # 화이트보드 텍스트 요소 -> RAG
  registry.py
  tools.py
```

근거: 두 도메인이 무엇을 공유하고 무엇이 다른지가 모델 단계에서 명시적으로 보이는 편이, 초기에 추상화하느라 의미를 흐리는 것보다 유지보수에 유리하다. **세 번째 비슷한 도메인이 생기는 시점에 공통 베이스로 일반화**하는 것을 차후 결정으로 남긴다.

### 2. Container 링킹은 Docs와 동일 패턴

`WhiteboardContainer`는 `NativeDocContainer`와 동일한 컬럼 구조 (`container_app`, `container_type`, `container_id`, `is_primary`, `sort_order`)를 갖는다. PMS 라우터는 `(container_app="pms", container_type="task" | "workspace", container_id=<id>)`로 화이트보드 목록을 조회한다.

근거: PMS 측에서 Docs와 Whiteboard를 동일한 방식으로 질의·노출할 수 있다. 향후 컨테이너 추상화를 일반화할 때도 마이그레이션이 단순하다.

### 3. 단일 캔버스, 페이지 없음

Phase 1은 화이트보드 1개 = `Whiteboard` 1개 = Excalidraw scene 1개. `NativeDocPage`에 해당하는 다중 페이지/프레임 모델은 도입하지 않는다. Excalidraw의 frame 기능이 필요해지면 후속 phase에서 추가한다.

근거: 화이트보드 사용 패턴은 보통 단일 무한 캔버스이고, Excalidraw 자체도 단일 씬을 기본 단위로 한다. 페이지 트리는 YAGNI.

### 4. Storage: scene JSON in DB

화이트보드 본체는 `Whiteboard.scene` (JSON) 컬럼으로 저장한다. Excalidraw 씬은 elements 배열 + appState로 구성되며 일반적인 다이어그램은 KB~수백 KB 수준이다. 매우 큰 화이트보드는 향후 별도 blob storage로 이전한다.

PNG/SVG 스냅샷은 클라이언트에서 export 시점에 생성하여 `media` 도메인을 통해 별도 저장한다. (Phase 1에서는 export 다운로드만 지원, 서버 측 썸네일은 후속.)

### 5. Realtime collab는 기존 Yjs 인프라 재사용

`docs/collab.py`와 `DocsCollabDocument`가 Yjs 기반 실시간 동기화를 이미 구현. Whiteboard도 동일 방식으로:
- `WhiteboardCollabDocument` 테이블 (room_key, yjs_state, snapshot_scene, last_snapshot_at)
- Excalidraw scene 직렬화/역직렬화는 `collab_codec.py`에서 처리

근거: 기존 WebSocket/Yjs 라우팅, 권한 체크, 스냅샷 정책을 그대로 적용하면 안정성·일관성 확보.

### 6. RAG는 텍스트 요소만 인덱싱

Excalidraw 화이트보드 안의 `text` 타입 element만 추출하여 RAG에 sync. 도형/스티키노트의 라벨도 텍스트 element로 표현되므로 검색 커버리지는 충분하다. 이미지는 OCR 도메인을 후속에서 연동.

### 7. 권한·공유는 Docs 패턴 mirror

- `WhiteboardUserShare` (user_id, access_level: read|comment|edit)
- `WhiteboardLinkShare` (token, access_level)
- `WhiteboardMeetingAccess`는 Phase 1 범위 외 (docs와 동등한 meeting 통합은 후속)

### 8. AI 통합 자리는 비워두지만 Phase 1에서는 stub만

Excalidraw에는 Text-to-diagram, Wireframe-to-code 같은 AI 기능이 있으나 OpenAI 키 직접 입력 방식이다. 이 프로젝트는 자체 AI 라우팅(`domains/ai/`)을 갖고 있으므로 **별도 PR**에서 다음을 통합한다 — 본 플랜은 hook 지점만 명시한다:
- `POST /api/whiteboards/{id}/ai/diagram-from-text` → 내부 LLM 라우팅 → Mermaid → Excalidraw
- 화이트보드 selection을 컨텍스트로 한 chat 사이드패널 (agent runtime의 evidence packet에 화이트보드 텍스트 요소 추가)

Phase 1에서는 Excalidraw 빌트인 AI 기능은 비활성화한다.

## Implementation Stages

### PR 1 — Backend whiteboard 도메인 skeleton + 모델

**파일**
- `apps/api/src/ai_do_api/domains/whiteboard/__init__.py` (신규)
- `apps/api/src/ai_do_api/domains/whiteboard/models.py` (신규)
  - `Whiteboard` (id, workspace_id, owner_id, title, source_app/kind/ref, generation_kind, scene JSON, created/updated/trashed_at)
  - `WhiteboardContainer` (NativeDocContainer mirror)
  - `WhiteboardUserShare`, `WhiteboardLinkShare`
  - `WhiteboardCollabDocument`
  - `WhiteboardUserItemPref`
- `apps/api/src/ai_do_api/domains/whiteboard/service.py` (신규) — CRUD + container link
- `apps/api/src/ai_do_api/domains/whiteboard/router.py` (신규)
  - `POST /api/whiteboards` — 생성 (workspace_id, title, container 옵션)
  - `GET /api/whiteboards/{id}` — 조회 (scene JSON 포함)
  - `PATCH /api/whiteboards/{id}` — 메타/scene 업데이트
  - `DELETE /api/whiteboards/{id}` — trash
  - `GET /api/whiteboards?container_app=&container_type=&container_id=` — 컨테이너별 목록
- `apps/api/src/ai_do_api/domains/whiteboard/access_grants.py` (신규) — docs 패턴 mirror
- `apps/api/src/ai_do_api/domains/whiteboard/registry.py` — app shell registration
- `apps/api/alembic/versions/<rev>_add_whiteboard_domain.py` (신규) — additive 마이그레이션
- `apps/api/src/ai_do_api/main.py` 또는 router aggregator — `whiteboard_router` 등록
- `apps/api/tests/test_whiteboard_crud.py` (신규)
- `apps/api/tests/test_whiteboard_container_link.py` (신규)
- `apps/api/tests/test_whiteboard_access.py` (신규)

**검증**
- `uv run pytest tests/test_whiteboard_*.py`
- 기존 docs 테스트 그린 유지 (회귀 없음)
- alembic upgrade/downgrade 양방향 동작

### PR 2 — Frontend Whiteboard 도메인 + Excalidraw 임베드 (단독 페이지)

**의존성**
- `pnpm add @excalidraw/excalidraw` (apps/web)

**파일**
- `apps/web/src/domains/whiteboard/` (신규)
  - `api.ts` — REST 클라이언트 (PR 1 라우터에 매핑)
  - `types.ts` — Whiteboard, scene 타입
  - `components/WhiteboardView.tsx` — Excalidraw 컴포넌트 래퍼, scene load/save, autosave debounce
  - `components/WhiteboardList.tsx` — 화이트보드 목록 (Docs list mirror)
  - `pages/WhiteboardPage.tsx` — `/whiteboards/:id` 라우트
  - `pages/WhiteboardHomePage.tsx` — `/whiteboards` 워크스페이스 단위 목록
- `apps/web/src/App.tsx` 또는 라우터 설정 — `/whiteboards`, `/whiteboards/:id` 라우트 추가
- `apps/web/src/app-shell.ts` — 좌측 네비/홈 셸에 Whiteboard 엔트리 등록
- `apps/web/e2e/whiteboard.spec.ts` (신규) — 생성→그리기→저장→재로드 골든패스

**범위 제외 (PR 4로 이연)**
- Realtime 협업
- 다중 사용자 커서

**검증**
- 단독 페이지에서 화이트보드 생성 → 도형/텍스트 추가 → 새로고침 시 복원
- E2E: Playwright로 Excalidraw 인터랙션 (drag, type) 검증
- 디자인 검토: 좌측 네비/홈 셸의 Docs/Whiteboard 엔트리가 시각적으로 동등하게 노출되는지

### PR 3 — PMS Whiteboard 탭 통합

**파일**
- `apps/api/src/ai_do_api/domains/pms/router.py` 또는 service — 태스크/워크스페이스 컨테이너의 화이트보드 카운트/목록 endpoint 추가 (또는 기존 컨테이너 children API에 `whiteboard` 카드 타입 추가)
- `apps/web/src/domains/pms/` 내 PMS 상세 페이지 — "Whiteboard" 탭 추가, `WhiteboardList`를 `container_app="pms"` 필터로 임베드
- `apps/web/src/domains/pms/` 내 "Docs" 탭 컴포넌트와 시각적 패리티 유지 (탭 헤더, 빈 상태, 생성 CTA)
- `apps/web/e2e/pms-whiteboard-tab.spec.ts` (신규) — PMS 태스크에서 Whiteboard 탭 → 화이트보드 생성 → 화이트보드 열기

**검증**
- PMS 태스크 상세에서 Docs 탭과 Whiteboard 탭이 동일한 UX 패턴 (생성 버튼, 목록, 빈 상태)
- 화이트보드 생성 시 `WhiteboardContainer`에 (container_app="pms", container_type="task", container_id=<task_id>) 자동 부착
- 태스크 삭제 시 화이트보드 컨테이너 링크 처리 정책 결정 (orphan vs cascade) — **결정 로그에 기록**

### PR 4 — Realtime collab (Yjs)

**파일**
- `apps/api/src/ai_do_api/domains/whiteboard/collab.py` (신규) — Yjs WebSocket 라우팅 (docs/collab.py 패턴 mirror)
- `apps/api/src/ai_do_api/domains/whiteboard/collab_codec.py` (신규) — Excalidraw scene ↔ Yjs doc 변환
- `apps/api/src/ai_do_api/domains/whiteboard/router.py` — `GET /api/whiteboards/{id}/collab` WebSocket 핸들러 등록
- `apps/web/src/domains/whiteboard/components/WhiteboardView.tsx` — Yjs provider + Excalidraw 바인딩
- `apps/web/src/domains/whiteboard/lib/yjs-binding.ts` (신규) — Excalidraw `onChange` ↔ Y.Map 동기화
- `apps/api/tests/test_whiteboard_collab.py` (신규)

**검증**
- 두 브라우저 탭에서 동시 편집 → 양쪽에 반영
- 끊김 → 재연결 시 마지막 snapshot에서 복구
- Yjs state binary 저장 사이즈 모니터링 (스냅샷 정책)

### PR 5 — Sharing (user/link shares) + 권한

**파일**
- `apps/api/src/ai_do_api/domains/whiteboard/router.py` — share 엔드포인트
  - `POST /api/whiteboards/{id}/shares/users`
  - `POST /api/whiteboards/{id}/shares/link`
  - `GET /api/whiteboards/shared/{token}` — 공개 링크 view
- `apps/web/src/domains/whiteboard/components/ShareDialog.tsx` (신규) — Docs ShareDialog 패턴 mirror
- `apps/api/tests/test_whiteboard_sharing.py` (신규)

**검증**
- read/comment/edit 권한별 라우팅 차단
- 링크 토큰 회전, 비활성화 동작
- 비로그인 사용자가 link share 토큰으로 read-only 접근 가능

### PR 6 — RAG sync + export + item prefs

**파일**
- `apps/api/src/ai_do_api/domains/whiteboard/rag_sync.py` (신규) — text element 추출 → RAG 인덱싱 (docs/rag_sync.py mirror)
- `apps/api/src/ai_do_api/domains/whiteboard/router.py` — `GET /api/whiteboards/{id}/export?format=png|svg` (서버 사이드는 클라이언트가 보낸 export 결과를 media에 저장)
- `apps/web/src/domains/whiteboard/components/WhiteboardView.tsx` — favorite, last_viewed 추적
- `apps/api/tests/test_whiteboard_rag_sync.py` (신규)

**검증**
- 화이트보드에 텍스트 추가/수정/삭제 시 RAG 인덱스 갱신
- 검색 결과에서 화이트보드 hit 시 `/whiteboards/:id`로 이동

## Verification

### 단위·통합 테스트
- `uv run pytest tests/test_whiteboard_*.py` (각 PR 범위)
- `uv run ruff check src/ai_do_api/domains/whiteboard/`
- 기존 docs 테스트 그린 유지

### 수동 검증 (각 PR 완료 시)
- PR 1: API 직접 호출로 CRUD + 컨테이너 링크 확인
- PR 2: 화이트보드 생성 → 도형 추가 → 새로고침 → 재로드
- PR 3: PMS 태스크 상세에서 Whiteboard 탭 → 화이트보드 추가 → 태스크 외부 navigation 후 복귀 시 유지
- PR 4: 두 브라우저로 동시 편집
- PR 5: 외부 사용자 링크 공유로 read-only 접근
- PR 6: 화이트보드 안 텍스트 검색 → 결과에서 진입

### Frontend 시각 패리티
- PMS 탭의 Docs/Whiteboard가 동일한 spacing, 빈 상태 메시지 톤, CTA 패턴
- 좌측 네비의 Whiteboard 엔트리 아이콘/위치 디자인 검토 후 결정

## 결정 로그

### 완료된 결정
- **이름**: Whiteboard / 화이트보드 (Draw 후보 폐기). 사용자 UI 라벨, API 경로, 도메인 모듈명 모두 일관되게 적용.
- **라이브러리 선택**: Excalidraw (MIT). tldraw는 proprietary로 production 라이센스 필요하여 부적합.
- **도메인 분리**: Docs 안 부가 기능이 아니라 `domains/whiteboard/` 별도 도메인으로 신설. PMS 탭 통합 요구와 캔버스/문서의 의미적 차이 때문.
- **Phase 1 범위**: 단일 캔버스 모델 (페이지 없음). 다중 페이지/frame은 후속.
- **Realtime 인프라**: 기존 Yjs 패턴 재사용. 새 프로토콜 도입 없음.

### 차후 결정 (PR 진행 중 명시 필요)
- 태스크 삭제 시 부착된 화이트보드 처리 정책 (orphan / cascade / soft-link)
- 화이트보드 scene 사이즈가 일정 임계 초과 시 blob storage 이전 임계값
- AI 통합 hook 지점 (Mermaid→Excalidraw, selection을 evidence packet에 추가)의 명세 — 별도 PR에서 다룸
- Docs/Whiteboard/(미래) 다른 first-class 컨테이너 개체가 3+개가 되는 시점에 공통 베이스 (`Document` 추상 + 콘텐츠 타입 분기) 일반화 검토

## 롤백 계획

- 각 PR은 additive 마이그레이션과 신규 라우터/도메인 추가로 구성되어 기존 코드 경로에 영향이 없다.
- 문제 발생 시:
  - PR 1: alembic downgrade로 whiteboard 테이블 제거. 라우터 등록 해제.
  - PR 2~3: 프론트엔드 라우트/네비/탭 엔트리 제거. 백엔드는 잔존해도 무영향.
  - PR 4: WebSocket 라우트 제거. Yjs 도큐먼트 테이블은 유지하거나 비워둠.
  - PR 5~6: 해당 엔드포인트와 RAG sync hook 제거.
- 모든 단계에서 docs 도메인은 변경하지 않으므로 기존 기능 회귀 위험은 alembic 마이그레이션 충돌 외에는 없다.
