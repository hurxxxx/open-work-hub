# Composable Abstractions

Use when similar screens/features tempt a shared framework.

## Rule

- Share policy, state transition, validation, permission, and data flow before sharing whole screens.
- Keep app-local assembly when domain meaning differs.
- Promote only after third use and when rules outnumber exceptions.
- Common model must expose affected screens, owners, identifiers, and tests.
- If config hides branches or gains screen-specific booleans, demote to local assembly.

## Levels

1. Shared element: `Button`, `IconButton`, `DataTable`, `FormField`, `Dialog`, `SearchField`, `EmptyState`.
2. Shared use-case module: pagination, search params, selection, inline edit, submit/toast, import mapping, revision workflow.
3. Domain model/config: only when lifecycle, validation, permissions, and differences are stable data.

## File Shape

```txt
apps/web/src/app-modules/<moduleId>/
  manifest.ts
  routes.ts
  public-api.ts        # only for cross-app consumers
  api/
  views/
  *-model.ts

apps/api/src/open_work_hub_api/domains/<domain>/
  router.py
  schemas.py
  application.py
  service.py
```

- Router/AI tool/worker do not reimplement domain service auth/DB rules.
- Feature modules can be composed visually inside an executable leaf app while owning their local
  manifest/API/view. They are not executable app identities, route owners, or runtime availability
  targets unless promoted into the app contract as a leaf app.
- Cross-app consumption uses `public-api.ts`; no app-local deep import.
- Current examples: Docs picker/viewer public API; PMS tree/reorder remains PMS-local.

## Naming

- Names show owner or implementation style: `fixed-schema`, `configured`, `workflow`.
- Avoid `module`, `misc`, `etc`, `common2`, and category names that imply false ownership.
- Route/nav/dataset/storage IDs have one owner file.

## AI/RAG

Forbidden:

- `if question contains ...`
- per-question synonym/suffix/field/source/customer hacks
- arbitrary evidence-rank patch for one result

Allowed:

- planner schema with `intent`, `keywords`, `field_hints`, `operators`
- generic operators: semantic search, full-text search, related-by-field, group-by-field, aggregate-by-field
- prompt/schema/scoring/evaluation fixture improvements

## Done

- New abstraction removes more duplicated policy than config complexity it adds.
- Public/app-local entrypoints are clear.
- No screen-specific branch in common renderer.
- No question/customer/source-specific AI/RAG branch.
- Identifiers are not duplicated.
- Focused tests/typecheck pass.
