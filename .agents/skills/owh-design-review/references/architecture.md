# Improve Codebase Architecture

Find deepening opportunities: smaller interfaces hiding more behavior.

## Evidence Sources

This is a context-selection list, not authority precedence; applicable AGENTS.md rules remain authoritative.

1. Current code/tests.
2. `AGENTS.md`.
3. `docs/README.md`.
4. Relevant owner docs under `docs/domains`, `docs/apps`, `docs/product`.
5. Root `adr/`.

Use vocabulary from [LANGUAGE.md](../LANGUAGE.md). Use dependency/test guidance from [DEEPENING.md](../DEEPENING.md). Use [INTERFACE-DESIGN.md](../INTERFACE-DESIGN.md) when the target is selected or specified by the request.

## Explore

- where one concept requires many files
- shallow modules/pass-throughs
- extracted pure functions whose call sites still hide bugs
- leaky seams
- hard-to-test behavior
- ADR conflicts worth reopening

Apply deletion test before proposing.

## Output

For exploration, report candidates with:

- files/modules
- problem
- proposed change
- benefit in leverage/locality/testability
- ADR conflict if any

If interface design for a specified target is already requested, proceed to that design without another candidate-selection question.
