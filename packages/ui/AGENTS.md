# Shared UI Agent Rules

- Keep components reusable across apps; accept localized copy through props rather than importing app catalogs.
- Preserve accessible names, keyboard/focus behavior, loading/error states, and existing public types.
- Rendered caller copy must keep `ko-KR`/`en-US` and interpolation aligned. Follow `apps/web/AGENTS.md` when changing web callers; run `pnpm check:i18n` for copy changes.
- Use focused component tests for changed behavior and the owning package's existing typecheck. Do not add app-specific state or permissions to shared UI.
