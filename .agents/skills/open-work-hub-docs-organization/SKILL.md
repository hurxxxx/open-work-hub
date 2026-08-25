---
name: open-work-hub-docs-organization
description: Organize Open Work Hub documentation ownership, navigation, and source-of-truth links. Use when moving, creating, deleting, reorganizing, or resolving the owner/location of project docs. Do not use for simple reading, summarization, or an in-place edit to an already-owned document.
---

# Open Work Hub Docs Organization

## Classify Before Moving

Read `docs/README.md` and `docs/agents/domain.md`, then use the narrowest current owner:

- `docs/domains/<domain>/`: cross-cutting technical contracts and runbooks.
- `docs/apps/<app-id>/`: behavior and design owned by one current app.
- `docs/product/`: stable cross-app product behavior and UI/data rules.
- `docs/agents/`: agent operating, context-routing, and validation guidance.
- root `adr/`: durable, non-obvious architecture decisions and their trade-offs.

Do not create a parallel current-truth tree, nested ADR directories, parallel glossaries, progress snapshots, or historical audit dumps. Keep large generated artifacts and raw QA output outside tracked docs; preserve durable conclusions in the owner document.

## Move Checklist

1. Check worktree safety with `git status --short --branch`.
2. Search references with `rg -n "<old-filename>|<old-path>" docs README.md AGENTS.md apps packages`.
3. Move only files in scope and preserve unrelated user changes.
4. Update the destination index and `docs/README.md` when navigation changes.
5. Use relative Markdown links and link to one owner instead of copying decisions.
6. Re-run the old-path search, then run `git diff --check`.
7. If skills changed too, run `python3 scripts/check-skill-harness.py`.

When a document touches an app and a domain, keep detailed behavior with the narrower owner and link from the broader contract.
