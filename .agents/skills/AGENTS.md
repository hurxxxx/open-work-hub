# Project Skill Rules

- One skill owns one repeatable project outcome. General writing style or ordinary coding behavior is not a project skill.
- Frontmatter `description` states the outcome, includes `Use when`, and names a negative boundary when a neighboring workflow could match.
- A skill mention is not a chain trigger; load another skill only when the user names it or its own description independently matches.
- Keep common authorization and safety in root `AGENTS.md`; do not repeat it in each skill.
- Keep `SKILL.md` imperative and short. Put only conditional detail in references and deterministic repeated work in scripts.
- Project skills live only in `.agents/skills`; do not fork them under `.claude` or `.codex`.
- Run bundled script syntax/fixture checks, `pnpm check:skills`, `pnpm test:skill-harness`, and `git diff --check`.
