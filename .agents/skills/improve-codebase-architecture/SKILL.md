---
name: improve-codebase-architecture
description: Find deepening opportunities in Open Work Hub using current code, tests, owning domain/app documentation, and accepted decisions in root adr/. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a codebase more testable and AI-navigable.
---

# Improve Codebase Architecture

Find deepening opportunities: smaller interfaces hiding more behavior.

## Sources

1. Current code/tests.
2. `AGENTS.md`.
3. `docs/README.md`.
4. Relevant owner docs under `docs/domains`, `docs/apps`, `docs/product`.
5. Root `adr/`.

Use vocabulary from [LANGUAGE.md](LANGUAGE.md). Use dependency/test guidance from [DEEPENING.md](DEEPENING.md). Use [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md) only after user picks a candidate.

## Explore

- where one concept requires many files
- shallow modules/pass-throughs
- extracted pure functions whose call sites still hide bugs
- leaky seams
- hard-to-test behavior
- ADR conflicts worth reopening

Apply deletion test before proposing.

## Output

Numbered candidates only:

- files/modules
- problem
- proposed change
- benefit in leverage/locality/testability
- ADR conflict if any

Do not design new interfaces until user selects a candidate.
