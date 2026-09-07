# Web Agent Rules

- Start with current UI code/tests plus `docs/agents/ui-components.md` and `docs/product/ui-design-principles.md` when UI behavior changes.
- Keep app surfaces under `apps/web/src/app-modules/<appId>/`; cross-app access uses manifest, `public-api.ts`, or bootstrap DTO only.
- Search existing app, shared components, platform helpers, and `packages/ui` before adding UI abstractions.
- Keep authoritative/shared state on the server; browser state may hold only ephemeral presentation state.
- User-facing copy adds aligned `ko-KR` and `en-US`; preserve interpolation variables and accessible names.
- Copy lives in `apps/web/src/platform/i18n/resources.ts` unless an app extension owns it. Use full-sentence keys, pass localized copy into `packages/ui`, and run `pnpm check:i18n` for rendered copy/catalog changes. Logs, identifiers, and fixtures do not automatically require translation.
- Use generated API contracts and existing workspace/time/feedback primitives; never hand-edit generated artifacts.
- Validate keyboard/focus, loading/empty/error/unavailable, narrow viewport, and stale-response behavior for changed flows.
- Run focused Vitest first, then `pnpm check:web-architecture` and `pnpm nx typecheck web`.
