---
name: open-work-hub-i18n
description: Review and fix Open Work Hub localization contracts. Use when changing translation keys/catalogs, adding rendered user-facing copy, or diagnosing locale parity and dynamic-message failures. Do not use for prose-only docs, developer logs, identifiers, or content that is not rendered by the product.
---

# i18n

- Web copy lives in `apps/web/src/platform/i18n/resources.ts` unless app extension point says otherwise.
- Add `ko-KR` and `en-US` together; keep interpolation variables aligned.
- One key owns a full sentence. Do not assemble sentence fragments.
- `packages/ui` receives copy through props.
- Developer logs/comments/tests/fixtures/generated text normally do not need product translations.

```bash
pnpm check:i18n
rg -n "[가-힣]" apps/web/src packages/ui/src -g '!**/*.spec.*' -g '!**/*.test.*' -g '!apps/web/src/platform/i18n/resources.ts' -g '!apps/web/src/platform/api/openapi.generated.d.ts'
pnpm nx typecheck web --skip-nx-cache
```
