@AGENTS.md

# Claude Code Bridge

- Nested `CLAUDE.md` files import their adjacent scoped `AGENTS.md`.
- Project skills are canonical in `.agents/skills`; `.claude/skills` is their symlink or junction. Run `pnpm setup:claude-skills` if the bridge is missing.
- Instructions guide behavior; deterministic restrictions belong in checkers, CI, settings, or hooks.
