---
name: aidoo-i18n
description: Use when adding, reviewing, or fixing localization in agentic-biz-hub, including hardcoded UI copy, translation resource keys, dynamic messages, shared UI package labels, and i18n guard validation.
---

# AIDOO i18n

Use this skill for localization work in this repo.

## Rules

- User-facing copy must come from `apps/web/src/platform/i18n/resources.ts`.
- Add both `ko-KR` and `en-US` values in the same change.
- Use interpolation for dynamic copy: `t('key', { count, name })`.
- Do not concatenate translated sentence fragments unless the resource itself owns the whole sentence.
- For plural/count messages, use i18next plural keys where English needs singular/plural.
- In `packages/ui`, do not add Korean or English fallback copy. Accept copy through props such as `messages`, `closeLabel`, `emptyState`, `placeholder`, or `ariaLabel`.
- Developer-only errors, logs, identifiers, enum values, product names, acronyms, regex ranges, comments, tests, and user/generated content usually do not need translation.

## Workflow

1. Search for hardcoded UI copy:
   ```bash
   pnpm check:i18n
   rg -n "[가-힣]" apps/web/src packages/ui/src \
     -g '!**/*.spec.*' -g '!**/*.test.*' \
     -g '!apps/web/src/platform/i18n/resources.ts' \
     -g '!apps/web/src/app-modules/learning/model/**' \
     -g '!apps/web/src/platform/api/openapi.generated.d.ts'
   ```

2. Classify findings:
   - Fix visible labels, buttons, headings, descriptions, placeholders, aria labels, toast/modal text, validation text, and user-facing fallback errors.
   - Leave non-user-facing code comments, type signatures, IDs, acronyms, regexes, logs, and developer-only invariant errors.

3. Convert copy:
   - Add resource keys under the owning app namespace.
   - Replace literals with `t(...)`.
   - For shared UI components, add or reuse props so app code passes localized copy.

4. Validate:
   ```bash
   pnpm check:i18n
   pnpm nx typecheck web --skip-nx-cache
   pnpm nx lint web --skip-nx-cache
   pnpm nx test web --skip-nx-cache
   git diff --check
   ```

## Notes

- API user-facing messages should use the API i18n helpers and pass `pnpm check:api-i18n`.
- Existing scanner false positives are acceptable only when they clearly match the exception list above.
