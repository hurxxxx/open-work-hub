# UI Components

Before new UI, search existing app, `apps/web/src/components`, `apps/web/src/platform`, `packages/ui/src/lib`, and app `public-api.ts`.

## Rules

- Reuse existing picker/tree/calendar/date/time/access/sidebar patterns.
- Promote to shared `components/` or `platform/` only after two apps use the same interface.
- Keep app-specific workflow components inside `apps/web/src/app-modules/<appId>/`.
- Cross-app app feature access uses `public-api.ts`; no app-local deep import.
- Product copy lives in i18n resources or caller props.
- User-triggered operation results use global feedback; do not render them as page-local inline notices. Reserve form messages for input validation.
- Use semantic tokens: `bg-app-*`, `text-app-*`, `border-app-*`, `app-text-*`.
- Validate with `pnpm check:web-architecture` and `pnpm nx typecheck web`.

## Shared UI

| Surface                                                        | Use                                                      |
| -------------------------------------------------------------- | -------------------------------------------------------- |
| `SubSidebar`                                                   | app secondary sidebar                                    |
| `AppBar*`, `NotificationPanel`                                 | global shell and notifications                           |
| `UnifiedCalendar`                                              | Planner/Meeting calendar                                 |
| `DateInput`, `DateTimeInput`, `UserDateTime`                   | date/time input/display                                  |
| `NoAccessNotice`                                               | visible unauthorized surface                             |
| `ResourcePickerDialog`                                         | picker chrome; caller owns rows/load                     |
| `FormDialog`, `FormFieldRow`                                   | modal form shell                                         |
| `FullscreenImageDialog`                                        | image/lightbox dialog                                    |
| `packages/ui` primitives                                       | button/dialog/menu/tooltip/input/select/search           |
| `FeedbackProvider`, `FormMessage`, `StatusSlot`, `ContextNote` | global feedback, validation, async status, context notes |
| `ContentState`, `EmptyState`, `Skeleton`, `DataTable`          | loading/empty/error/unavailable/table display            |
| `DetailDrawer`                                                 | side detail surface with focus return                    |

Overlay ordering is owned by the shared [UI layer tokens](../../packages/ui/styles.css):
floating panels and the dock stay below modal overlays; confirmations use the elevated
dialog layer; popovers and feedback stay above dialogs. Use these tokens instead of
local z-index values. Controlled dialogs opened by external actions restore that action
through Radix's autofocus callbacks; `useConfirm` captures it before a pending render
can disable the action.

## Platform Helpers

| Helper                                                                            | Use                                                          |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `UserSearchMultiSelect`, `useRemoteUserSearchSession`, `user-option-picker-model` | user/member picker                                           |
| generated app routes, `app-bootstrap-context`, `app-access`                       | app paths and fail-closed app admission                      |
| `DirectoryPicker`                                                                 | reusable user/company group selection; app-owned ACL editors |
| `browser-download`                                                                | testable browser download                                    |
| `formatByteSize`                                                                  | file-size display                                            |
| `native-date-input`                                                               | date/datetime-local parse/format                             |
| `picker-model`, `resource-picker-session`                                         | picker state/load wiring                                     |

## App-Scoped

- Files folder tree uses Files wrapper/model.
- PMS space tree/reorder stays PMS-local.
- Docs picker/viewer is exposed through Docs `public-api.ts`.
- Keep `PmsCenteredStateBlock`, `DocsHtmlPageContentSurface`, and PMS order rows app-local until a real second consumer exists.
