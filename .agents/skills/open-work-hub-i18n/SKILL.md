---
name: open-work-hub-i18n
description: Review and fix Open Work Hub localization contracts. Use when changing translation keys/catalogs, adding rendered user-facing copy, or diagnosing locale parity and dynamic-message failures. Do not use for prose-only docs, developer logs, identifiers, or content that is not rendered by the product.
---

# Open Work Hub i18n

## Rules

- Web product copy is owned by `apps/web/src/platform/i18n/resources.ts` unless an existing app-owned extension point explicitly says otherwise.
- Add `ko-KR` and `en-US` values in the same change and keep placeholder/interpolation variables aligned.
- Use interpolation for dynamic copy and let one key own a full sentence; do not assemble translated sentence fragments.
- In `packages/ui`, accept copy through props instead of adding product-language fallback strings.
- Developer-only errors, logs, enum values, comments, tests, generated content, and example fixtures normally do not require product translations.
- API messages follow the catalog and checker under `apps/api`; do not suppress a finding by weakening the checker.

## Workflow

```bash
pnpm check:i18n
rg -n "[가-힣]" apps/web/src packages/ui/src \
  -g '!**/*.spec.*' -g '!**/*.test.*' \
  -g '!apps/web/src/platform/i18n/resources.ts' \
  -g '!apps/web/src/platform/api/openapi.generated.d.ts'
```

Review visible labels, headings, buttons, placeholders, aria labels, toasts, validation text, and user-facing fallback errors. Then run the focused affected checks; for broad web catalog changes use:

```bash
pnpm check:i18n
pnpm nx typecheck web --skip-nx-cache
pnpm nx lint web --skip-nx-cache
pnpm nx test web --skip-nx-cache
```
