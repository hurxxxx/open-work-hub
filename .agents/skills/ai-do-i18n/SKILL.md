---
name: ai-do-i18n
description: Review and fix AI-DO localization contracts. Use when changing translation keys/catalogs, adding user-facing copy that must be localized, or diagnosing locale parity/dynamic-message failures. Do not use for prose-only docs or copy that is not rendered by the product.
---

# AI-DO i18n

## Rules

- User-facing web copy must come from `apps/web/src/platform/i18n/resources.ts`.
- That central resource file is currently a protected Core Platform composition
  surface. An `lane::app-sandbox` change must not edit it. If the existing scaffold
  does not already provide the required key and current code has no tested
  app-owned resource extension, stop and return a Core Enablement brief instead of
  widening the lane or bypassing the guard.
- Add both `ko-KR` and `en-US` values in the same change.
- Use interpolation for dynamic copy: `t('key', { count, name })`.
- Do not concatenate translated sentence fragments unless the resource owns the whole sentence.
- In `packages/ui`, accept copy through props; do not add Korean or English fallback copy.
- Developer-only errors, logs, identifiers, enum values, comments, tests, and generated content usually do not need translation.

## Workflow

```bash
pnpm check:i18n
rg -n "[가-힣]" apps/web/src packages/ui/src \
  -g '!**/*.spec.*' -g '!**/*.test.*' \
  -g '!apps/web/src/platform/i18n/resources.ts' \
  -g '!apps/web/src/app-modules/learning/model/**' \
  -g '!apps/web/src/platform/api/openapi.generated.d.ts'
```

Fix visible labels, headings, buttons, placeholders, aria labels, toasts, validation text, and user-facing fallback errors.

Validate with:

```bash
pnpm check:i18n
pnpm nx typecheck web --skip-nx-cache
pnpm nx lint web --skip-nx-cache
pnpm nx test web --skip-nx-cache
```
