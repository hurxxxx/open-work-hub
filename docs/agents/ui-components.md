# UI Components Reference

Open Work Hub Web UI는 새 화면을 만들기 전에 기존 공용 컴포넌트와 app-scoped 재사용
컴포넌트를 먼저 확인한다. 공용화는 실제로 여러 앱에서 재사용될 때만 하고, 한 앱의 업무 흐름에
묶인 컴포넌트는 해당 `apps/web/src/app-modules/<appId>/` 안에 둔다. 이 문서는 UI 재사용
보조 지침이며 개발 구조·추상화 판단이 충돌하면 `llm-friendly-development.md`를 우선한다.

아래 경로는 현재 저장소에 실제로 존재하는 항목만 기록한다. 컴포넌트를 이동하거나 제거하면
이 문서와 해당 import/test를 같은 변경에서 갱신한다.

## Before Building UI

1. 현재 화면과 비슷한 앱의 구현을 먼저 검색한다.
2. `apps/web/src/components`, `apps/web/src/platform`, `packages/ui/src/lib`와 필요한 경우 관련
   `apps/web/src/app-modules/<appId>/public-api.ts`를 확인한다.
3. 이미 있는 picker, tree, calendar, date/time, access notice, sidebar 패턴을 재사용한다.
4. 새 공용 컴포넌트는 두 개 이상의 앱에서 같은 interface로 쓸 때만 `components` 또는
   `platform`으로 올린다.
5. UI copy는 caller가 i18n label을 전달하거나 각 앱 namespace에 둔다.
6. [UI Design Principles](../product/ui-design-principles.md)의 enterprise layout, mobile shell과
   semantic token 기준을 확인한다.

## Shared Components

| Component | Path | Use for |
| --- | --- | --- |
| `SubSidebar` | `apps/web/src/components/layout/SubSidebar.tsx` | 앱별 왼쪽 보조 사이드바 프레임, collapse/resize, create menu와 category nav. 앱은 manifest/sidebar config로 연결하고 프레임을 복제하지 않는다. |
| `AppBar*` | `apps/web/src/components/layout/` | 전역 앱바, workspace switcher, notification, app pin/more menu와 mobile shell chrome. |
| `NotificationPanel` | `apps/web/src/components/layout/NotificationPanel.tsx` | 전역 알림 패널과 notification action projection. |
| `UnifiedCalendar` | `apps/web/src/components/calendar/UnifiedCalendar.tsx` | Planner/Meeting 같은 일정 UI. FullCalendar wrapper, host-owned toolbar, drag/drop/resize payload와 휴일 styling을 제공한다. |
| `DateInput`, `DateTimeInput` | `apps/web/src/components/date/DateInput.tsx` | 날짜·일시 입력. 사용자 date format, locale 표시와 native picker bridge를 처리한다. |
| `UserDateTime` | `apps/web/src/components/date/UserDateTime.tsx` | API timestamp 등 사용자에게 보이는 절대·상대 날짜시간 표시. 화면에서 `new Date(...).toLocaleString()` 또는 직접 `Intl.DateTimeFormat`을 복제하지 않는다. |
| `NoAccessNotice` | `apps/web/src/components/common/NoAccessNotice.tsx` | 권한은 없지만 기능 표면은 보이는 picker/modal의 표준 접근 제한 안내. API 호출 자체는 upstream에서 gate한다. |
| `ResourcePickerDialog` | `apps/web/src/components/picker/ResourcePickerDialog.tsx` | 문서·회의·task·whiteboard resource 선택 모달의 공통 chrome. Data loading/filtering과 row 내용은 caller가 소유한다. |
| `FormDialog`, `FormFieldRow` | `apps/web/src/components/form/FormDialog.tsx` | 생성·편집 폼 모달의 shell, action footer와 label/required/optional chrome. API, i18n과 field validation은 caller가 소유한다. |
| `FullscreenImageDialog` | `apps/web/src/components/media/FullscreenImageDialog.tsx` | 앱 공통 전체 화면 이미지/lightbox dialog. Portal, Escape close, body scroll lock, header/action slot과 이미지 surface를 제공한다. |

## Package UI Primitives

| Component | Path | Use for |
| --- | --- | --- |
| `Button`, `Dialog`, `DropdownMenu`, `Tooltip` | `packages/ui/src/lib/primitives/` | 기본 action, modal, menu와 tooltip. 앱별 chrome을 새로 만들기 전에 우선 사용한다. |
| `InlineNotice` | `packages/ui/src/lib/feedback/inline-notice.tsx` | Inline success/info/warning/danger notice. Error alert는 수동 danger div 대신 `role="alert"`와 함께 사용한다. |
| `FeedbackProvider`, `useFeedback` | `packages/ui/src/lib/feedback/feedback-provider.tsx` | 화면 전환 뒤에도 유지되는 전역 success/info/warning/error 피드백. 앱에서 별도 toast provider나 viewport를 만들지 않는다. |
| `FormMessage`, `StatusSlot`, `ContextNote` | `packages/ui/src/lib/feedback/` | 각각 고정 높이 form validation, 비동기 상태 slot, 권한·범위·운영 맥락 안내. 저장 결과는 전역 feedback, 입력 오류는 form message로 구분한다. |
| `SearchField`, `Input`, `Select` | `packages/ui/src/lib/primitives/` | 표준 검색·입력·select. 앱 token 스타일과 맞는 경우 chrome을 복제하지 않는다. |
| `ContentState` | `packages/ui/src/lib/data-display/content-state.tsx` | loading, empty, error, unavailable의 안정된 화면 상태와 선택적 재시도 action. 동일 영역에서 상태별 높이 변화를 줄인다. |
| `EmptyState`, `Skeleton`, `DataTable` | `packages/ui/src/lib/data-display/` | 비어 있음, loading placeholder와 표준 table. 앱 전용 empty hero/copy가 아니라면 우선 재사용한다. |
| `DetailDrawer` | `packages/ui/src/lib/layout/detail-drawer.tsx` | 상세 side drawer. 열기 전 focus를 기억하고 닫을 때 연결된 trigger로 복귀시키므로 caller가 별도 focus 복구를 복제하지 않는다. |

## Platform UI Helpers

| Module | Path | Use for |
| --- | --- | --- |
| `UserSearchMultiSelect` | `apps/web/src/platform/users/UserSearchMultiSelect.tsx` | 사용자·참석자·멤버 다중 선택. 검색 input, selected chips, locked user와 candidate trailing slot을 제공한다. |
| `useRemoteUserSearchSession` | `apps/web/src/platform/users/remote-user-search-session.ts` | 원격 사용자 검색 상태, debounce, loader와 status 관리. |
| `user-option-picker-model` | `apps/web/src/platform/users/user-option-picker-model.ts` | 사용자 표시명, 부서명, meta parts와 후보 filter/selection projection. |
| `workspace-utils` | `apps/web/src/platform/workspaces/workspace-utils.ts` | Workspace app path, API path rewrite와 shell workspace slug 계산. |
| `browser-download` | `apps/web/src/platform/browser/browser-download.ts` | 브라우저 다운로드 동작을 테스트 가능한 helper로 분리할 때 사용한다. |
| `formatByteSize` | `apps/web/src/platform/format/byte-size.ts` | 파일 크기 표시. B/KB/MB/GB/TB threshold, compact digits, locale와 trailing-zero 옵션 처리. |
| `native-date-input` | `apps/web/src/platform/time/native-date-input.ts` | Native date/datetime-local 값 formatting, parsing, day shift와 ISO 변환. |
| `picker-model` | `apps/web/src/platform/pickers/picker-model.ts` | Resource picker 공통 state/reducer/projection. Loader와 row rendering은 caller가 소유한다. |
| `resource-picker-session` | `apps/web/src/platform/pickers/resource-picker-session.ts` | `ResourcePickerDialog` caller의 load/query/submit/close hook wiring. API loader, copy, payload와 row는 caller가 제공한다. |

## Tree And Picker Patterns

| Component/model | Path | Notes |
| --- | --- | --- |
| Files sidebar tree | `apps/web/src/app-modules/files/sidebar-folders.tsx` | `@pierre/trees/react`의 `FileTree`/`useFileTree`를 사용하는 folder path tree. Path 충돌이나 이름에 `/`가 있으면 row fallback을 사용한다. |
| Files folder model | `apps/web/src/app-modules/files/folder-tree-model.ts` | Flat folder list를 정렬된 nested tree와 path map으로 변환한다. Files sidebar 작업에서 우선 재사용한다. |
| PMS space tree | `apps/web/src/app-modules/pms/sidebar/SpaceTree.tsx`, `apps/web/src/app-modules/pms/sidebar/space-tree-model.ts` | PMS space 아래 list/folder/doc와 drag/reorder를 처리한다. PMS 안에서 재사용하고 일반 tree로 성급히 승격하지 않는다. |
| Docs page tree node | `apps/web/src/app-modules/docs/views/DocsPageTreeNode.tsx` | Docs page row의 selection, expand, delete와 drag/drop zone. Docs tree 작업은 `DocsViewParts` export와 함께 확인한다. |
| Docs picker | `apps/web/src/app-modules/docs/public-api.ts`, `apps/web/src/app-modules/docs/views/DocsHubPickerModal.tsx` | 문서를 다른 앱에서 선택하는 lazy public API. Meeting과 PMS 등 기존 consumer가 사용하며 새 doc picker를 복제하지 않는다. |
| Docs viewer | `apps/web/src/app-modules/docs/public-api.ts`, `apps/web/src/app-modules/docs/views/DocsViewerModal.tsx` | 다른 앱에서 Docs page를 viewer/modal로 보여 주는 lazy public API. Recording과 다른 기존 consumer가 사용한다. |

## App-Scoped Reuse Patterns

| Component/model | Path | Notes |
| --- | --- | --- |
| `PmsCenteredStateBlock` | `apps/web/src/app-modules/pms/views/PmsCenteredStateBlock.tsx` | PMS 화면 안의 중앙 정렬 loading/error/empty presentation. API load state와 list rendering은 화면 controller가 소유한다. |
| `DocsHtmlPageContentSurface` | `apps/web/src/app-modules/docs/views/docs-html-page-content-surface.tsx` | Docs HTML page의 edit/preview 분기. Save/upload/open workflow는 caller가 소유한다. |
| `SpaceOrderEditorModal` rows | `apps/web/src/app-modules/pms/sidebar/SpaceOrderEditorModal.tsx` | PMS space order modal의 local row/move/empty parts. Reorder/save 계약은 `apps/web/src/app-modules/pms/sidebar/space-order-editor-model.ts`를 우선 사용한다. |

## Reuse Rules

- `components/`: 앱과 무관한 UI primitive/composite만 둔다.
- `platform/`: 인증, workspace, 사용자 검색, API client처럼 여러 앱이 쓰는 runtime UI helper를 둔다.
- `app-modules/<appId>/public-api.ts`: 특정 앱 기능을 다른 앱에 안전하게 노출할 때만 사용한다.
- App-specific component를 다른 앱에서 deep import하지 않는다. 실제 cross-app consumer가 있으면 public
  API를 만들고, 없다면 app-local로 유지한다.
- `@pierre/trees`, FullCalendar, `@dnd-kit` 같은 외부 UI engine은 이미 감싼 wrapper/model이 있으면
  그 경계를 통해 사용한다.
- 색상과 typography는 `bg-app-*`, `text-app-*`, `border-app-*`, `app-text-*` semantic token을
  우선 사용한다.
- 새 UI는 `pnpm check:web-architecture`와 `pnpm nx typecheck web`으로 검증한다. 공용 model을
  바꾸면 해당 `*.spec.ts(x)` focused test를 함께 갱신한다.
