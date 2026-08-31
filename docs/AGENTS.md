# Documentation Agent Rules

- Read `docs/README.md` and `docs/agents/domain.md` before creating, moving, deleting, or reassigning documentation.
- Update the single current owner; link instead of copying facts into a second current-truth document.
- Keep commands, contracts, invariants, owner links, and exceptions that prevent wrong implementation.
- Remove narrative history, progress reports, duplicated tool rules, and future TODOs unless the user explicitly requests them.
- Root `adr/` contains accepted cross-domain decisions; do not create nested ADR trees.
- Verify referenced paths and commands against the current tree; run `git diff --check` and `pnpm check:skills` when agent guidance changes.
