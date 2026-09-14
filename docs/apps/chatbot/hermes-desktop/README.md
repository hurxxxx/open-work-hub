# 챗봇 UI 운영·유지보수

Hermes Desktop의 대화·도구 내역·결과 패널 구성을 OWH 챗봇에 적용한 앱 소유 문서다. 런타임 설치, 컨텍스트 압축, 모델·도구 정책, 파일 보관·용량·마이그레이션은 [Hermes 런타임 문서](../../../domains/ai/hermes.md)가 관리한다.

## 제공 기능

| 영역 | 동작 |
| --- | --- |
| 대화 탐색 | 공통 서브사이드바에 새 대화·최근/고정/보관 대화·제목 검색을 배치한다. 대화 메뉴에서 고정·보관·이름 변경·삭제를 처리한다. 검색은 불러온 제목 범위이며 더 보기로 범위를 늘린다. |
| 실행 표시 | 한 질문 뒤의 native assistant 도구 단계들을 한 답변으로 표시한다. 도구 내역은 답변 안에서 기본 접기이며 도구 오류·승인 거절·결과 미확인을 구분해 보존한다. 개별 시도의 오류 개수는 전체 실행 실패를 뜻하지 않는다. 진행 표시는 현재 실행이 종료되면 사라진다. |
| 전송·복원 | 기존 서버 실행을 관찰하고 sequence 중복을 제거한다. 중지는 서버 종료 이벤트까지 기다리며 실패하면 재시도할 수 있다. 연결 실패를 새 동기 실행으로 자동 재전송하지 않는다. |
| 승인 | 승인 참조·소유 대화·기존 승인 정책을 보존한다. 중복 클릭과 대화 전환 후 늦은 응답은 새 대화의 상태를 변경하지 않는다. |
| 입력·읽기 | 한국어 IME 조합 Enter를 전송으로 처리하지 않는다. Shift+Enter 줄바꿈, 질문 편집·재응답, 복사, 읽기 위치와 하단 이동을 지원한다. native 편집·재응답은 기존 새 세션 분기 동작을 따른다. |
| 결과 패널 | 넓은 화면에서는 대화 옆에, 1024px 미만에서는 공용 모달에 표시한다. 데스크톱은 폭 확대·브라우저 전체 화면·복귀를 지원하며 미리보기를 다시 마운트하지 않는다. 닫기·Escape·포커스 복귀와 기존 graph/custom renderer를 유지한다. |
| 파일 | 진행 중인 실행 수와 현재 대화 파일 수를 구분한다. 입력창 첨부, 파일 목록, 미리보기·소스·다운로드, 저장 버전 선택, 생성 작업 출력 조회를 제공한다. 실행 중 업로드는 차단한다. |
| 생성 결과 | 접힌 실행·파일 목록 밖에 HTML·SVG·이미지·Markdown 미리보기 카드를 표시한다. 카드는 서버에 기록된 정확한 저장 버전을 연다. |

전체 이력·본문 검색, 버전 간 diff·결과 편집, Office 전용 뷰어, 전체 결과 갤러리, 메시지 대기열, 컨텍스트 상세 수치·수동 압축, 자식 에이전트 개별 제어·음성은 현재 제공 범위에 포함되지 않는다. 해당 기능에는 별도 서버/뷰어 계약이 필요하다. Desktop의 Electron·호스트 터미널·Git·개인 provider 설정·YOLO는 웹에 이식하지 않는다.

## 임베딩과 상태 소유권

- 기본 `chatbot.root`는 `conversationListPlacement: 'shell'`로 등록한다. 다른 앱에 임베딩하는 `ChatbotExperienceConfig`의 기본값은 `inline`이므로 소유 앱 메뉴와 대화 스코프를 보존한다.
- sidebar 확장점과 포털은 DOM 배치만 담당한다. 목록과 실행 controller는 각각 하나이며 모바일 메뉴 선택 시 공통 `onNavigate`로 닫는다.
- `@assistant-ui/react`의 공개 `ExternalStoreRuntime`에 OWH turn/live 상태를 투영한다. 전송·중지·편집·재시도는 기존 controller를 호출한다. 모델 선택, 실행 전송, 승인, 영속 저장의 별도 소유자를 만들지 않는다.
- 현재 의존성은 `@assistant-ui/react 0.15.18`이다. 실제 설치 기준은 [package.json](../../../../package.json)과 lockfile이며 `pnpm install --frozen-lockfile`을 사용한다. 버전을 바꿀 때 `ChatThreadRuntime.spec.tsx`의 메시지 ID 교체와 thread 복원 검사를 유지한다.
- native와 `durable_background` 복원, 앱별 custom renderer·기존 report/analysis 교체 의미는 각 소유 계약을 따른다. [AI Execution](../../../domains/ai/execution.md), [AI Write Policy](../../../domains/ai/write-policy.md).

## 파일 참조와 미리보기

`/apps/chatbot?c=<conversation>`이 대화 식별자다. 기존 `a=<artifact>` 링크를 보존하며 파일은 `f=<logical-file>&v=<revision>`으로 연다. `v`가 없을 때만 접근 가능한 최신 저장 버전을 선택한다. 열린 파일 패널도 4초 간격으로 버전 목록을 갱신하며 새 버전은 ‘최신 버전 보기’로 선택한다. 선택한 과거 버전을 자동으로 교체하지 않는다. 선택 버전의 접근 가능 여부도 별도로 4초마다 재검증하며, 만료·권한 철회·조회 실패 시 기존 프리뷰와 다운로드를 해제한다. 첫 페이지에 없다는 이유만으로 만료를 판단하지 않는다. 명시된 버전이 만료되거나 다른 대화/파일에 속하면 최신 파일로 대체하지 않고 접근 불가를 표시한다.

파일명이나 Markdown 링크에서 결과 소유권을 추측하지 않는다. 버전은 서버가 기록한 대화와 생성 run에 연결된다. 현재 고정 native Runs API에는 개별 메시지 연결 ID가 없어 **특정 답변의 파일 카드·원본 답변 점프는 제공하지 않는다.** 대신 대화 파일에서 정확한 생성 작업의 출력을 확인한다. 업로드와 기존 파일의 마이그레이션 스냅샷은 생성 작업 정보가 없는 파일로 표시한다.

결과 카드는 최근 저장 버전 100개에서 현재 파일 ID·해시와 일치하는 최신 버전 중 생성 run이 있는 미리보기 형식만 표시한다. 업로드·중간 JSON/코드·그 밖의 파일은 전체 대화 파일 목록에서 연다. 더 오래된 결과가 있으면 해당 목록을 안내한다. 제목·내용·파일명으로 특정 답변과 연결하지 않는다.

자동 열기는 대화 화면에서 명시적으로 켜는 임시 설정이며 기본값은 끔이다. 최초 실행 목록 이후 새로 확인하거나 진행 중에 관찰한 실행이 `completed`가 된 경우에만 한 번 연다. 기존 결과 패널·작성 중 입력·다른 활성 실행·숨겨진 탭을 방해하지 않고, 실패·중지된 실행이나 새로고침한 과거 이력을 자동으로 열지 않는다. 서버 파일·revision·실행 상태는 4초 간격으로 조회하며, 대화/사용자 전환 후 이전 응답과 조회 실패 시 결과를 숨긴다.

| 형식 | 미리보기 경계 |
| --- | --- |
| PNG·JPEG·GIF·WebP | 최대 10 MiB, 인증된 바이트를 임시 object URL로 표시하고 전환/닫기 때 해제 |
| HTML·SVG·Markdown·텍스트·코드 | 최대 2 MiB. HTML은 인증된 저장 버전의 로컬 JS/CSS/이미지를 `esbuild-wasm 0.28.1`로 묶은 뒤 `allow-scripts`만 허용한 opaque-origin iframe과 CSP로 외부 리소스/fetch를 제한한다. 의존 파일은 각 2 MiB, 총 10 MiB·100개로 제한한다. 순환 import와 import-map 접두사를 지원한다. 누락 파일·스크립트/CSP 오류는 미리보기 실패로 표시하며 소스 탭은 유지한다. SVG는 기존 정화기를 사용한다. |
| 기타 형식 또는 크기 초과 | 미리보기 대신 인증된 다운로드 제공 |

HTML 의존 파일은 선택한 HTML 버전의 스냅샷 시점에 저장된 버전으로 조회하며 다른 대화·미래 버전·만료/권한 없는 파일로 대체하지 않는다. JS/CSS만 수정해도 런타임 체크포인트가 새 HTML 프리뷰 버전을 발행하므로 변경된 결과와 이전 결과를 구분할 수 있다. 런타임의 오프라인 Chromium 검사는 [정적 프리뷰 실행 계약](../../../domains/ai/hermes.md#static-preview-execution)을 따른다.

미리보기는 메타데이터와 실제 수신 크기를 검사하고 15초 제한·redirect 거부·전환 취소를 적용한다. 다운로드와 revision 조회는 매번 서버 권한·만료 검사를 통과해야 한다. 과거 버전 보관으로 사용량이 늘 수 있으므로 정리·보관 기간·세션 한도와 롤백은 [파일 런타임 계약](../../../domains/ai/hermes.md#execution-workspace-and-files)을 따른다.

## 도구 오류 해석

Hermes는 도구 결과를 받은 뒤 새 호출을 선택해 작업을 계속할 수 있다. 중간 Python 예외나 정책 차단 이후 결과 파일이 생성돼도 원래 오류 이력을 성공으로 덮어쓰지 않는다. 무인 API의 `execute_code` 샌드박스 허용, native 파일 안전 경로와 중단·복구 검증은 [런타임 문서](../../../domains/ai/hermes.md#execution-workspace-and-files)가 관리한다.

## 유지보수 위치

| 변경 대상 | 진입점 |
| --- | --- |
| 기본 화면·임베딩·서브사이드바 | [ChatbotView.tsx](../../../../apps/web/src/app-modules/chatbot/views/ChatbotView.tsx), [sidebar.tsx](../../../../apps/web/src/app-modules/chatbot/sidebar.tsx) |
| assistant-ui·도구 묶음·스크롤 | [ChatThreadRuntime.tsx](../../../../apps/web/src/app-modules/chatbot/views/chat/ChatThreadRuntime.tsx), [ChatThread.tsx](../../../../apps/web/src/app-modules/chatbot/views/chat/ChatThread.tsx) |
| 전송·중지·native history | [useChatStream.ts](../../../../apps/web/src/app-modules/chatbot/api/useChatStream.ts), [conversations-api.ts](../../../../apps/web/src/app-modules/chatbot/api/conversations-api.ts) |
| 생성 결과·파일 UI | [HermesGeneratedResults.tsx](../../../../apps/web/src/app-modules/chatbot/views/chat/HermesGeneratedResults.tsx), [ChatResultSurface.tsx](../../../../apps/web/src/app-modules/chatbot/views/chat/ChatResultSurface.tsx), [HermesFilePanel.tsx](../../../../apps/web/src/app-modules/chatbot/views/chat/HermesFilePanel.tsx) |
| 파일 저장·revision·API | [files.py](../../../../apps/api/src/open_work_hub_api/domains/hermes/files.py), [file_router.py](../../../../apps/api/src/open_work_hub_api/domains/hermes/file_router.py) |

참고한 Desktop 소스는 [고정 커밋의 chat 구성](https://github.com/NousResearch/hermes-agent/tree/98a3324821c64b78c13d5d0f105508da0ab71cee/apps/desktop/src/app/chat)과 [thread 구성](https://github.com/NousResearch/hermes-agent/tree/98a3324821c64b78c13d5d0f105508da0ab71cee/apps/desktop/src/components/assistant-ui/thread)이다. 연결 방식은 [공식 ExternalStoreRuntime API](https://www.assistant-ui.com/docs/runtimes/custom/external-store)를 사용한다.

## 회귀 검사

저장소 루트에서 실행한다. UI 테스트는 production `NODE_ENV`를 상속하지 않는다.

```bash
env -u NODE_ENV pnpm exec vitest run --root apps/web src/app-modules/chatbot
pnpm nx typecheck web
env -u NODE_ENV pnpm exec tsc -p apps/web/tsconfig.spec.json --noEmit
pnpm check:web-architecture
pnpm check:i18n
(cd apps/api && uv run --python 3.12 --group dev pytest tests/test_hermes_runtime.py tests/test_hermes_integration.py tests/test_hermes_migration.py -q --tb=short)
pnpm check:api-contract
pnpm check:api-architecture
pnpm check:alembic-graph
```

이번 결과 카드·확대 보완과 브라우저 검증은 데스크톱 범위이며 모바일 개선은 제외한다. 기존 모바일 동작에 대한 회귀 테스트는 유지한다.

파일 런타임을 변경하면 [런타임 검증 목록](../../../domains/ai/hermes.md#runtime-change-validation)도 실행한다. 브라우저에서는 개발용 대화로 다음을 확인한다.

1. 도구를 쓰는 질문 세 번 후 과거 진행 표시가 없고 내역이 각 답변에만 속하는지 확인한다. 중지·새로고침·대화 왕복으로 실행이 중복되지 않아야 한다.
2. 고정·보관·제목 검색·모바일 선택과 임베딩 앱의 메뉴/스코프를 확인한다.
3. 같은 파일을 두 번 생성한 뒤 각 버전의 내용·생성 작업·재접속 링크를 확인한다. 잘못된 revision·만료·권한 철회는 접근 불가로 표시되어야 한다.
4. 데스크톱에서 실제 HTML 생성 → 결과 카드 → 정확한 버전 → 패널 확대·전체 화면·닫기 → 대화 재진입을 확인한다. 자동 열기 동의·작성 중 억제·반복 폴링·새로고침과 오류/승인 거절 구분을 검사한다.
5. 첨부·미지원 파일·HTML/SVG 경계, 키보드 포커스, 한국어/영어·테마를 확인한다.
