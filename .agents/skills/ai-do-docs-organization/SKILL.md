---
name: ai-do-docs-organization
description: Organize AI-DO documentation ownership and source-of-truth links. Use when moving, creating, deleting, reorganizing, or resolving the correct owner/location of project docs. Do not use for simple reading, summarization, or an in-place edit to an already-owned document.
---

# AI-DO Docs Organization

## Quick Start

1. Read `docs/README.md` and `docs/agents/domain.md` before moving docs.
2. Classify the document by ownership:
   - `docs/current/`: cross-project current truth, product status, top-level indexes.
   - `docs/domains/<domain>/`: cross-cutting technical domain details such as RAG, inference, auth, runtime, release.
   - `docs/apps/<app-id>/`: documents scoped to one app/appbar item such as Legacy Issues, Mail, PMS, Docs.
   - `docs/agents/`: agent operating rules, context policy, harness criteria.
   - `docs/product/`: stable product behavior and UI/data rules used by current implementation.
   - `docs/final/`: dated external deliverables; never current truth unless a current owner links one explicitly.
   - `docs/reference/`: setup and repeated reference material.
   - `docs/working/`: temporary in-progress notes only.
   - `docs/archive/`: explicitly retained non-plan reference snapshots; never current truth.
3. Treat `learning/**/*.md` as Learning app course content, not project truth or agent context.
4. Keep raw benchmark files, large generated outputs, screenshots, and historical QA dumps outside tracked docs. Summarize conclusions and point to local artifact paths when useful.
5. After moving docs, update every link with `rg`, then run `pnpm check:skills` if skills changed.

## Classification Rules

- Put only stable, cross-project decisions in `docs/current/`. If a detailed doc belongs to a domain or app, leave a link from the relevant current index instead of duplicating content.
- Put RAG model selection, source scope, chunking, and reindex runbooks under `docs/domains/rag/`.
- Put Inference Gateway and DGX operations under `docs/domains/inference-gateway/`.
- Put release, deployment, rollback, and runtime layout runbooks under `docs/domains/release/` unless they are environment-specific references.
- Put Legacy Issues validation and source ingestion docs under `docs/apps/legacy-issues/`.
- Do not retain completed plans, TODO lists, progress logs, or dated audit inventories as current repository docs. Preserve their conclusions in the owner document and recover the original from Git history only when requested.
- Put externally shared completion/plan artifacts under a dated `docs/final/<purpose-date>/` bundle with a README that states its non-current status.
- When a doc touches both an app and a domain, store the detailed workflow with the narrower owner and link to the broader domain decision.

## Move Checklist

1. Check worktree safety: `git status --short --branch`.
2. Search existing references: `rg -n "<old-filename>|<old-path>" docs README.md agents.md apps`.
3. Use the active agent environment's approved file-editing mechanism for moves and deletions; do not use destructive cleanup commands.
4. Add or update `README.md` indexes in the destination folder.
5. Update `docs/README.md`, `docs/current/ai-hub-transition-index.md`, and `docs/agents/domain.md` when the navigation model changes.
6. Re-run the search for old paths and fix leftovers.
7. Run `git diff --check`.

## Link Style

- Prefer relative Markdown links inside `docs/`.
- From `docs/current` to a domain doc, use paths like `../domains/rag/README.md`.
- From an app doc to a domain doc, use paths like `../../domains/rag/README.md`.
- Do not copy the same decision into several docs. Link to the owner document.
