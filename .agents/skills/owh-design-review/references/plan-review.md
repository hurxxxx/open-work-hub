# Grill With Docs

## Evidence Sources

This is a context-selection list, not authority precedence; applicable AGENTS.md rules remain authoritative.

1. Current code/tests.
2. `AGENTS.md`.
3. `docs/README.md`.
4. Owning `docs/domains`, `docs/apps`, or `docs/product` file.
5. Accepted root `adr/`.

## Session

- Ask about consequential unresolved decisions and include a recommendation; do not repeat decisions already made.
- Replace vague terms with owning-domain terminology.
- Distinguish implemented behavior, accepted decision, and proposal.
- Challenge conflicts with code/tests/docs/ADRs.
- If sources conflict, identify the source to correct before treating answer as settled.
- Edit docs only when requested. Update existing owner docs, not parallel glossaries/snapshots.

## ADR

Offer ADR only when decision is costly to reverse, rationale is not inferable, and alternatives are real. Use [ADR-FORMAT.md](../ADR-FORMAT.md).
