# UI Components Reference

Open ALM web UI는 새 화면을 만들기 전에 기존 공용 컴포넌트와 app-scoped 재사용
컴포넌트를 먼저 확인한다. 공용화는 실제로 여러 앱에서 재사용될 때만 하고, 한 앱의
업무 흐름에 묶인 컴포넌트는 해당 `app-modules/<appId>/` 안에 둔다.
이 문서는 UI 재사용 보조 지침이다. 개발 구조/추상화 판단이 충돌하면 `llm-friendly-development.md`를 우선한다.

## Before Building UI

1. 현재 화면과 비슷한 앱의 구현을 먼저 검색한다.
2. `apps/web/src/components`, `apps/web/src/platform`, 필요한 경우 관련
   `apps/web/src/app-modules/<appId>/public-api.ts`를 확인한다.
3. 이미 있는 picker, tree, calendar, date, access notice, sidebar 패턴을 재사용한다.
4. 새 공용 컴포넌트는 두 개 이상의 앱에서 같은 interface로 쓸 때만
   `components` 또는 `platform`으로 올린다.
5. UI copy는 caller가 i18n label을 전달하거나 각 앱 namespace에 둔다.

## Shared Components

| Component                    | Path                                                      | Use for                                                                                                                                                                                                                                |
| ---------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SubSidebar`                 | `apps/web/src/components/layout/SubSidebar.tsx`           | 앱별 왼쪽 보조 사이드바 프레임, collapse/resize, create menu, 카테고리 nav. 앱은 `manifest`/sidebar config로 연결하고 프레임을 복제하지 않는다.                                                                                        |
| `AppBar*`                    | `apps/web/src/components/layout/`                         | 전역 앱바, workspace switcher, notification button, app pin/more menu. Shell chrome만 다룬다.                                                                                                                                          |
| `NotificationPanel`          | `apps/web/src/components/layout/NotificationPanel.tsx`    | 전역 알림 패널과 notification action projection.                                                                                                                                                                                       |
| `UnifiedCalendar`            | `apps/web/src/components/calendar/UnifiedCalendar.tsx`    | Planner/Meeting 같은 일정 UI. FullCalendar wrapper, host-owned toolbar, drag/drop/resize payload, KST/Korean holiday styling을 제공한다.                                                                                               |
| `DateInput`, `DateTimeInput` | `apps/web/src/components/date/DateInput.tsx`              | 날짜/일시 입력. 사용자 date format, locale 표시, native picker bridge를 처리한다.                                                                                                                                                      |
| `UserDateTime`               | `apps/web/src/components/date/UserDateTime.tsx`           | API timestamp 등 사용자에게 보이는 절대/상대 날짜시간 표시. `useAuth().user.time_zone`, `locale`, `date_format`을 적용한다. 화면에서 `new Date(...).toLocaleString()`/직접 `Intl.DateTimeFormat`을 쓰지 않는다.                        |
| `NoAccessNotice`             | `apps/web/src/components/common/NoAccessNotice.tsx`       | 권한은 없지만 기능 표면은 보이는 picker/modal 안의 표준 접근 제한 안내. API 호출 자체는 upstream에서 gate한다.                                                                                                                         |
| `ResourcePickerDialog`       | `apps/web/src/components/picker/ResourcePickerDialog.tsx` | 문서/회의/태스크/화이트보드 같은 resource 선택 모달의 공통 chrome. Dialog shell, access notice slot, error notice, search input, loading/empty/list/submitting 상태를 제공하고, data loading/filtering과 row 내용은 caller가 소유한다. |
| `FormDialog`, `FormFieldRow` | `apps/web/src/components/form/FormDialog.tsx`             | 생성/편집 폼 모달의 공통 shell, action footer, label/required/optional chrome. 제출 가능 여부, API 호출, i18n copy, field-specific validation은 caller가 소유한다.                                                                     |
| `FullscreenImageDialog`      | `apps/web/src/components/media/FullscreenImageDialog.tsx` | 앱 공통 전체 화면 이미지/lightbox dialog. Portal, Escape close, body scroll lock, black fullscreen surface, title/header/close action, action slot, centered image rendering을 제공한다.                                               |

## Package UI Primitives

| Component                                     | Path                                             | Use for                                                                                                                                   |
| --------------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `Button`, `Dialog`, `DropdownMenu`, `Tooltip` | `packages/ui/src/lib/primitives/`                | 기본 action, modal, menu, tooltip primitive. 앱별 modal/action chrome을 새로 만들기 전에 우선 사용한다.                                   |
| `InlineNotice`                                | `packages/ui/src/lib/feedback/inline-notice.tsx` | inline success/info/warning/danger notice. error alert는 수동 danger border/background div 대신 `role="alert"`와 함께 이 컴포넌트를 쓴다. |
| `SearchField`, `Input`, `Select`              | `packages/ui/src/lib/primitives/`                | 표준 검색/입력/select primitive. 앱 token 스타일과 맞는 경우 직접 input/select chrome을 복제하지 않는다.                                  |
| `EmptyState`, `Skeleton`, `DataTable`         | `packages/ui/src/lib/data-display/`              | 비어 있음, loading placeholder, 표준 table 표시. 앱 전용 empty hero/copy가 아니라면 우선 재사용한다.                                      |

## Platform UI Helpers

| Module                       | Path                                                        | Use for                                                                                                                                                                                    |
| ---------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `UserSearchMultiSelect`      | `apps/web/src/platform/users/UserSearchMultiSelect.tsx`     | 사용자/참석자/멤버 다중 선택. 검색 input, selected chips, locked user, candidate trailing slot, optional `inputId`를 제공한다.                                                             |
| `useRemoteUserSearchSession` | `apps/web/src/platform/users/remote-user-search-session.ts` | 원격 사용자 검색 상태, debounce/loader/status를 관리한다.                                                                                                                                  |
| `user-option-picker-model`   | `apps/web/src/platform/users/user-option-picker-model.ts`   | 사용자 표시명, 부서명, meta parts, 후보 필터링/선택 projection.                                                                                                                            |
| `workspace-utils`            | `apps/web/src/platform/workspaces/workspace-utils.ts`       | workspace app path, API path rewrite, shell workspace slug 계산.                                                                                                                           |
| `browser-download`           | `apps/web/src/platform/browser/browser-download.ts`         | 브라우저 다운로드 동작을 테스트 가능한 helper로 분리할 때 사용한다.                                                                                                                        |
| `formatByteSize`             | `apps/web/src/platform/format/byte-size.ts`                 | 파일 크기 표시. B/KB/MB/GB/TB threshold, compact digits, locale/trailing-zero 옵션을 한 곳에서 처리한다.                                                                                   |
| `native-date-input`          | `apps/web/src/platform/time/native-date-input.ts`           | native date/datetime-local input 값(`YYYY-MM-DD`, `YYYY-MM-DDTHH:mm`) formatting, parsing, day shift, ISO 변환을 처리한다.                                                                 |
| `picker-model`               | `apps/web/src/platform/pickers/picker-model.ts`             | resource picker의 공통 state/reducer/projection. load/query/error/submitting lifecycle과 exclude/query/limit projection을 제공하고, app별 loader와 row rendering은 caller가 소유한다.      |
| `resource-picker-session`    | `apps/web/src/platform/pickers/resource-picker-session.ts`  | `ResourcePickerDialog` caller의 load/query/submit/close hook wiring. picker별 API loader, error copy, selection payload, row rendering은 caller가 제공하고 hook은 lifecycle glue만 맡는다. |

## Tree And Picker Patterns

| Component/model     | Path                                                                        | Notes                                                                                                                                                                                                                                         |
| ------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Files sidebar tree  | `apps/web/src/app-modules/files/sidebar-folders.tsx`                        | `@pierre/trees/react`의 `FileTree`/`useFileTree`를 사용하는 folder path tree. `buildFolderTreeModel`이 id/path 양방향 map과 path rendering 가능 여부를 만든다. folder name에 `/`가 있거나 path 충돌이 있으면 `FolderTreeRow` fallback을 쓴다. |
| Files folder model  | `apps/web/src/app-modules/files/folder-tree-model.ts`                       | flat folder list를 정렬된 nested tree와 `paths`로 변환한다. 파일/폴더 sidebar 작업은 이 model을 우선 재사용한다.                                                                                                                              |
| PMS space tree      | `apps/web/src/app-modules/pms/sidebar/SpaceTree.tsx`, `space-tree-model.ts` | PMS space 아래 list/folder/doc를 렌더링하고 `@dnd-kit` reorder를 처리한다. PMS sidebar 안에서 재사용하고, 일반 tree로 승격하지 않는다.                                                                                                        |
| Docs page tree node | `apps/web/src/app-modules/docs/views/DocsPageTreeNode.tsx`                  | Docs page tree row. selection, expand, delete, drag/drop zone 표시를 처리한다. Docs tree 작업은 `DocsViewParts` export와 함께 재사용한다.                                                                                                     |
| Docs picker         | `apps/web/src/app-modules/docs/public-api.ts`, `DocsHubPickerModal.tsx`     | 문서를 다른 앱에서 선택할 때 쓰는 lazy public API. Image Wizard, Meeting, PMS가 adapter로 연결한다. 새 doc picker를 만들지 않는다.                                                                                                            |
| Docs viewer         | `apps/web/src/app-modules/docs/public-api.ts`, `DocsViewerModal.tsx`        | 다른 앱에서 docs page를 읽기 모달로 보여줄 때 사용한다.                                                                                                                                                                                       |

## App-Scoped Reuse Patterns

| Component/model              | Path                                                                     | Notes                                                                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PmsCenteredStateBlock`      | `apps/web/src/app-modules/pms/views/PmsCenteredStateBlock.tsx`           | PMS 화면 안의 중앙 정렬 loading/error/empty presentation. API load state와 list rendering은 각 화면 controller가 소유한다.                                                        |
| `DocsHtmlPageContentSurface` | `apps/web/src/app-modules/docs/views/docs-html-page-content-surface.tsx` | Docs HTML page의 edit/preview 분기. `DocsHtmlEditorPanel`/`DocsHtmlPagePanel` 선택, label/action 연결을 한 곳에서 처리하고 content save/upload/open workflow는 caller가 소유한다. |
| `SpaceOrderEditorModal` rows | `apps/web/src/app-modules/pms/sidebar/SpaceOrderEditorModal.tsx`         | PMS space order modal 내부의 list/doc row, move buttons, empty block local parts. reorder/save 계약은 `space-order-editor-model.ts`를 우선 사용한다.                              |

## Reuse Rules

- `components/`: app과 무관한 UI primitive/composite만 둔다.
- `platform/`: 인증, workspace, 사용자 검색, API client처럼 여러 앱이 쓰는 runtime UI helper를 둔다.
- `app-modules/<appId>/public-api.ts`: 특정 앱 기능을 다른 앱에 안전하게 노출할 때만 사용한다.
- app-specific component를 다른 앱에서 직접 deep import하지 않는다. 필요하면 public API를 만든다.
- `@pierre/trees`, `FullCalendar`, `@dnd-kit` 같은 외부 UI engine은 이미 감싼 wrapper/model이 있으면 wrapper를 통해 사용한다.
- 색상/typography는 `bg-app-*`, `text-app-*`, `border-app-*`, `app-text-*` 토큰을 우선 사용한다.
- 새 UI는 `pnpm nx typecheck web`과 `pnpm check:web-architecture`로 검증한다. 공용 model을 바꾸면 해당 `*.spec.ts(x)`를 같이 갱신한다.
