---
name: open-work-hub-docs-organization
description: Organize Open Work Hub documentation ownership, navigation, and source-of-truth links. Use when moving, creating, deleting, reorganizing, or resolving the owner/location of project docs. Do not use for simple reading, summarization, or an in-place edit to an already-owned document.
---

# Docs Organization

## Owners

- `docs/domains/<domain>/`: cross-app technical contracts/runbooks.
- `docs/apps/<app-id>/`: one app's behavior/contracts.
- `docs/product/`: product-wide UI/data rules.
- `docs/agents/`: AI agent routing/checks.
- root `adr/`: accepted costly architecture decisions.

## Rules

- Read `docs/README.md` and `docs/agents/domain.md`.
- Use narrowest owner; link instead of copying facts.
- No parallel current-truth tree, nested ADR, glossary duplicate, progress snapshot, historical dump, raw QA output.
- Update indexes/references after moves.
- Validate with `git diff --check`; if skills changed, `python3 scripts/check-skill-harness.py`.
