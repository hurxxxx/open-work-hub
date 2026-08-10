# ADR Format

AI-DO ADRs live in the repository-root `adr/` directory. Use the next available four-digit number and a descriptive slug, for example `0005-workspace-audit-retention.md`.

Do not create nested or context-local ADR directories.

## Template

```md
# ADR NNNN: Short decision title

- Status: Proposed | Accepted | Deprecated | Superseded by ADR NNNN
- Date: YYYY-MM-DD

## Context

Describe the decision pressure, constraints, and relevant alternatives.

## Decision

State the chosen contract precisely.

## Consequences

Record the important positive and negative effects.
```

Add `Non-Goals` or `Follow-up` only when they prevent a likely misunderstanding.

## When to offer an ADR

All three conditions must hold:

1. The decision is costly to reverse.
2. A future maintainer would not infer the rationale from code and owner docs.
3. The decision resolves a real trade-off between plausible alternatives.

Before creating one, inspect existing files in `adr/` to avoid duplicating or contradicting an accepted decision.
