---
name: grill-with-docs
description: Stress-test a plan against Open Work Hub's current code, tests, owning documentation, and accepted ADRs. Use when the user wants to challenge a plan, sharpen terminology, or record confirmed decisions.
---

# Grill With Docs

## Sources

1. Current code/tests.
2. `AGENTS.md`.
3. `docs/README.md`.
4. Owning `docs/domains`, `docs/apps`, or `docs/product` file.
5. Accepted root `adr/`.

## Session

- Ask one decision question at a time and include a recommended answer.
- Replace vague terms with owning-domain terminology.
- Distinguish implemented behavior, accepted decision, and proposal.
- Challenge conflicts with code/tests/docs/ADRs.
- If sources conflict, identify the source to correct before treating answer as settled.
- Edit docs only when requested. Update existing owner docs, not parallel glossaries/snapshots.

## ADR

Offer ADR only when decision is costly to reverse, rationale is not inferable, and alternatives are real. Use [ADR-FORMAT.md](./ADR-FORMAT.md).
