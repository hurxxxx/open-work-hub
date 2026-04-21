# 26. 에디터와 실시간 협업 — BlockNote + Yjs

> **한 줄 요약.** 현대 협업 에디터의 정석은 "**블록 기반 에디터**(BlockNote) + **CRDT**(Yjs) + **WebSocket 릴레이**"다. 이 프로젝트가 바로 그 조합으로 Notion/Confluence 급의 실시간 편집을 구현한다.

---

## 1. 문서 에디터의 난이도 — 생각보다 끔찍하다

"편집기 만들어"라고 하면 쉬워 보입니다. 하지만 실제로는 소프트웨어에서 가장 어려운 분야 중 하나입니다. 고려해야 할 것:

- **IME 처리** (한국어·일본어 조합 입력)
- **copy/paste의 지옥** (Word, 웹, 구글독스에서 복사해 올 때 각기 다른 HTML)
- **undo/redo** (여러 명이 편집 중일 때 undo는 누구의 것?)
- **실시간 공동 편집** (서로 같은 자리에 커서를 놓으면?)
- **접근성**, **모바일 키보드**, **드래그앤드롭**, **이미지 업로드**, **마크다운**, **수식**, ...

이 모든 것을 직접 만드는 건 **미친 짓**입니다. 그래서 오픈소스 에디터를 쓰는 것이 상식입니다.

---

## 2. 에디터 라이브러리의 세대

### 2.1 1세대 — contentEditable 직접 다루기

옛날에는 브라우저의 `contentEditable` 속성을 직접 써서 만들었습니다. 브라우저마다 동작이 다르고 버그 지옥.

### 2.2 2세대 — 구조화된 문서 모델

- **Quill** (2013) — 기본 에디터.
- **Draft.js** (2016, Facebook) — 유지보수 중단.
- **Slate** (2016) — 유연, 커스텀 강함.
- **ProseMirror** (2017) — 이론적 토대가 탄탄. 많은 에디터의 "엔진" 역할.
- **Lexical** (2022, Meta) — Draft.js의 후계.
- **TipTap** — ProseMirror 위의 편리한 래퍼.

### 2.3 3세대 — 블록 기반

Notion이 대중화한 "블록"이란 단위로 문서를 관리. 각 블록은 독립적이어서 드래그 이동·접기 등이 자유롭습니다.

- **BlockNote** (우리 선택) — ProseMirror + Yjs 기반. Notion-like UX.
- **Novel**, **Plate** — 비슷한 접근.
- **Milkdown** — 마크다운 지향 편집기.

우리 프로젝트의 초기 문서(`docs/product/ai_portal.md`)에서는 "wiki는 milkdown 기반"이라고 적혀 있었는데, 실제 구현은 **BlockNote**로 정착했습니다. 이유는 아마도 Notion식 UX(블록 드래그, 슬래시 메뉴)가 **협업 환경에 더 자연스럽기** 때문입니다.

---

## 3. BlockNote — 우리 에디터의 엔진

### 3.1 BlockNote란

**BlockNote** 는 2023년부터 급성장한 React 기반 Notion-like 블록 에디터입니다. 내부적으로 **ProseMirror** 를 쓰고, **Yjs** 와 즉시 통합됩니다.

주요 특징:
- 슬래시(`/`) 메뉴로 블록 삽입
- 드래그로 블록 이동
- 마크다운 스러운 입력 (`# 헤더`, `- 리스트` 자동 변환)
- 테이블·이미지·체크박스 블록
- **협업 기본 지원** (Yjs)

### 3.2 이 프로젝트의 BlockNote 패키지

`package.json`에서 확인:
- `@blocknote/core` — 핵심 엔진
- `@blocknote/react` — React 바인딩
- `@blocknote/mantine` — Mantine 테마 버전(우리 UI와 자연스럽게 맞음)

### 3.3 사용 감각 (간단한 예)

```tsx
import { useCreateBlockNote } from '@blocknote/react';
import { BlockNoteView } from '@blocknote/mantine';

function DocEditor({ docId }) {
  const editor = useCreateBlockNote({
    // 서버 저장/로드, 협업 설정 등 옵션
  });
  return <BlockNoteView editor={editor} />;
}
```

우리 코드에서는 여기에 **Yjs 프로비전** 과 **ypy-websocket 서버 연결** 이 붙습니다.

---

## 4. CRDT — 실시간 공동 편집의 수학

### 4.1 왜 CRDT인가

여러 명이 **동시에** 문서를 고치면 무슨 일이 생길까요?

```
A: "안녕" 뒤에 "하세요" 삽입
B: "안녕" 뒤에 "!!" 삽입
```

둘의 변경이 서버에서 만났을 때 어떤 게 맞을까요? 순서대로 적용하면 A 먼저면 "안녕하세요!!", B 먼저면 "안녕!!하세요". 만약 B가 이미 "!!"를 넣은 걸 보고 A가 그 뒤에 "하세요"를 넣었다고 생각했다면 의도가 달라집니다.

이 문제를 푸는 두 가지 접근:

1. **OT(Operational Transform)** — 구글 독스가 쓴 방식. 서버가 조작의 순서를 변환해 정합성 유지. 구현이 매우 까다롭다.
2. **CRDT(Conflict-free Replicated Data Type)** — **"충돌 자체가 일어나지 않도록 자료구조를 설계"**. 수학적으로 "모든 변경을 어떤 순서로 적용해도 같은 결과"가 되게 함. 구현이 (상대적으로) 쉬움.

### 4.2 Yjs

**Yjs** 는 Kevin Jahns가 만든 JavaScript용 CRDT 라이브러리입니다. 2020년대 CRDT 구현의 대표주자. BlockNote 외에도 TipTap, Lexical, ProseMirror 등과 광범위하게 통합됩니다.

핵심 자료구조:
- `Y.Doc` — 공유 문서
- `Y.Text` — 공유 문자열
- `Y.Array`, `Y.Map` — 공유 배열·맵
- `Y.XmlFragment` — 리치 텍스트용

### 4.3 Yjs의 작동 요약

1. 각 사용자는 **로컬**에서 자유롭게 편집.
2. 편집은 "연산(update)" 덩어리로 캡슐화되어 WebSocket 등을 통해 **다른 사용자 + 서버** 에게 브로드캐스트.
3. 모든 쪽이 받은 연산을 자기 Y.Doc에 적용. CRDT 성질 덕에 **어떤 순서로 받아도 결과 동일**.
4. 각 사용자의 **커서 위치·선택 범위** 도 `awareness` 기능으로 공유(색깔 커서가 움직이는 것).

오프라인에서 편집한 것도 나중에 연결되면 자동 병합됩니다.

---

## 5. WebSocket 릴레이 — y-websocket과 ypy-websocket

### 5.1 클라이언트 측: `y-websocket`

브라우저에서 돌아가는 JavaScript 라이브러리. 서버와 WebSocket 연결을 유지하며 Yjs 업데이트를 주고받습니다.

```ts
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';

const doc = new Y.Doc();
const provider = new WebsocketProvider(
  'wss://portal.doowon.co/yjs',
  `doc-${docId}`,
  doc
);
```

### 5.2 서버 측: `ypy-websocket` (Python 구현)

`apps/api` 의존성에 `ypy-websocket`, `y-py`가 있습니다. 즉 **파이썬으로 쓴 Yjs 릴레이 서버**를 FastAPI 안에서 직접 운영합니다.

왜 Python에서 돌리는가?

- FastAPI와 같은 프로세스에서 관리하면 **인증·권한**을 공유하기 쉬움.
- 별도 Node 서버를 띄우지 않아 **운영이 단순**.
- `ypy-websocket` + `y-py` 조합이 2024년 이후 꽤 성숙.

### 5.3 흐름도

```
[유저 A 브라우저]                         [유저 B 브라우저]
       │ (WebSocket)                              │
       ▼                                          ▼
           ┌──────────────────────────────┐
           │ FastAPI + ypy-websocket      │
           │  - 인증·권한 검사            │
           │  - Y.Doc 상태 서버 측 유지   │
           │  - Redis pub/sub로 멀티 프로세스 확장(옵션)│
           └──────────────────────────────┘
                    │
                    ▼
                PostgreSQL / S3
                (주기적 스냅샷 저장)
```

- 릴레이 서버는 방(room) 단위로 동작. 각 문서 = 하나의 room.
- 사용자 접속/이탈을 관리.
- 주기적으로 DB/MinIO에 스냅샷(현재 Y.Doc 상태)을 저장해 **영속성** 확보.

### 5.4 멀티 인스턴스 문제

API 서버를 여러 개 띄우면(예: `pnpm prodlike:api:1`, `:2`) 서로 다른 서버에 붙은 사용자들 사이에서 동기화가 안 될 수 있습니다. 해법: **Redis pub/sub**로 서버끼리 업데이트를 중계. `.env.example` 에 `DOOWON_COLLAB_RELAY_URL=redis://...` 같은 설정이 있을 수 있습니다.

---

## 6. DocsCollabHub — 프로젝트 구현의 중심

백엔드 쪽의 `apps/api/src/aidoo_api/domains/docs/collab.py`(조사 결과) 가 **DocsCollabHub**라는 클래스로 이 전체 릴레이를 관리합니다. 주요 책임:

- WebSocket 연결 수락/정리
- 방(room)별 Yjs 상태 유지
- 업데이트를 같은 방의 다른 클라이언트들에게 방송
- 스냅샷 저장 트리거
- 접속 사용자 awareness 브로드캐스트

비개발자 관점에서 알아야 할 것: **"문서 실시간 협업이 백엔드의 한 모듈로 잘 분리되어 있다"**. 기능 확장(예: 공유 코멘트, 기반 권한 세분화)은 이 모듈을 중심으로 진행됩니다.

---

## 7. 왜 우리는 Notion을 그대로 안 쓰는가

"Notion 쓰면 되지 왜 만드나?"는 자연스러운 의문입니다. 이유:

1. **사내 데이터·AI와의 통합**: 우리 AI 에이전트가 **우리 문서 구조를 읽고 쓰도록** 하려면 우리 에디터여야 함.
2. **권한 모델**: 회사 조직·워크스페이스 체계와 맞춤형.
3. **보안/데이터 주권**: 사내 데이터가 외부 SaaS로 나가지 않음.
4. **미래 확장**: 회의록·PMS와 깊은 통합(예: "회의록에서 블록 드래그로 이슈 생성").

이것이 우리가 "bespoke(맞춤형) 포털"을 만드는 이유입니다.

---

## 8. 대안 비교

| 에디터 라이브러리 | 비고 |
|---|---|
| **BlockNote** | 우리 선택. Notion-like, 협업 기본 |
| TipTap | ProseMirror 기반. 유연하지만 블록 UX는 직접 구현 |
| Lexical (Meta) | 성능 강점. 협업 기본 지원 미약 |
| Slate | 커스텀 자유. 안정성 이슈 여전 |
| Milkdown | 마크다운 중심 |

| CRDT 구현 | 비고 |
|---|---|
| **Yjs** | 우리 선택. JS 생태계 표준 |
| Automerge | 다른 유명 CRDT. 브라우저 성능 약점 |
| Loro | Rust 기반 신예 |

---

## 9. 실전 주의점

### 9.1 스키마 버전 관리

에디터의 블록 스키마가 변경되면 기존 문서가 깨질 수 있음. **마이그레이션 전략**이 필요. BlockNote는 자체 스키마 버전을 관리하지만, 주의 깊게 업데이트.

### 9.2 이미지·파일 블록

업로드는 **MinIO(31장)** 와 연결. 에디터가 S3 URL을 블록에 저장.

### 9.3 오프라인 편집

Yjs는 원래 오프라인 친화적이지만, 우리가 이를 **UI로 노출할지는 별도 결정**. 지금은 온라인 편집 전제.

### 9.4 성능 — 큰 문서

1만 라인 이상의 문서는 Yjs도 느려집니다. 이럴 땐 문서를 **여러 페이지로 쪼개는 UX** 가 현실적.

### 9.5 보안

- 방(room) 접근 권한을 WebSocket 연결 수락 시점에 검증.
- 사용자가 보고 있는 awareness 정보도 권한 범위 내에서만 공유.

---

## 10. 핵심 요약

- 협업 에디터 = **BlockNote(UX) + Yjs(CRDT) + y-websocket(릴레이)**.
- CRDT는 **"충돌이 일어나지 않는 자료구조"**. 수학적으로 정합성 보장.
- 서버는 **ypy-websocket** 기반 FastAPI 모듈(`DocsCollabHub`)이 맡음.
- Notion을 그대로 안 쓰는 이유는 **사내 데이터·AI 통합, 권한, 보안** 때문.
- 스키마 업그레이드·큰 문서 성능·권한 검사가 유지보수의 주요 포인트.

---

## 11. 이해도 체크

1. 공동 편집에서 왜 "그냥 변경을 순서대로 적용하는 것"으로는 부족한지 예시로 설명하세요.
2. CRDT의 핵심 아이디어를 한 문장으로 정리해 보세요.
3. `y-websocket`(클라이언트)과 `ypy-websocket`(서버)의 관계는?
4. API 서버를 여러 대로 늘렸을 때 발생할 수 있는 협업 문제와 해법은?
5. 왜 우리 팀이 사내 문서 편집을 Notion 대신 직접 구현하기로 했는지 세 가지 이상 근거를 들어 보세요.
