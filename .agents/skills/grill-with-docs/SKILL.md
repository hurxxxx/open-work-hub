---
name: grill-with-docs
description: Stress-test a plan against AI-DO's current code, tests, owning documentation, and accepted ADRs. Use when the user wants to challenge a plan, sharpen terminology, or record confirmed decisions.
---

# Grill With Docs

Interview the user one decision at a time until the plan and its constraints are explicit. Give a recommended answer with each question. If the answer can be established from the repository, inspect the repository instead of asking.

## Establish the current contract

Read sources in this order:

1. Current code and tests for the affected behavior.
2. Repository instructions in `agents.md` and any nearer instruction file.
3. `docs/current/` for cross-project status and operating context.
4. The owning document under `docs/domains/` or `docs/apps/`.
5. Accepted decisions under the repository-root `adr/` directory.

Use `docs/product/` for product intent, `docs/reference/` for background material, and `docs/archive/` only as history. Archived or dated documents do not override current code or owner documentation.

Do not create parallel glossary files or nested ADR directories. AI-DO records domain language in the relevant current/domain/app document and architecture decisions in root `adr/`.

## During the session

- Challenge statements that conflict with current code, tests, owner documentation, or an accepted ADR.
- Replace vague or overloaded terms with the terminology already used by the owning domain.
- Use concrete scenarios and edge cases to expose hidden constraints.
- Distinguish current behavior, an approved decision, and a proposal. Never present a proposal as implemented.
- When sources disagree, report the conflict and identify which source should be corrected before treating the answer as settled.

Only edit documentation when the user's request explicitly includes documentation changes. For review-only requests, return proposed wording and file references without writing files.

When an agreed term or current contract should be documented, update the existing owning document. Do not create a parallel glossary or progress snapshot.

## ADR threshold

Offer a new ADR only when all three conditions hold:

1. The decision is costly to reverse.
2. The choice would be surprising without its rationale.
3. Genuine alternatives were considered.

Use [ADR-FORMAT.md](./ADR-FORMAT.md). If the decision is operational, temporary, or already visible from code and owner docs, update the owner document instead.
