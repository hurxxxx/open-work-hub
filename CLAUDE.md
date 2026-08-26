# Claude Code Instructions

@AGENTS.md

`AGENTS.md` is canonical. This file only bridges Claude Code behavior.

## Skills

- Project skills live in `.agents/skills/<name>/SKILL.md`.
- `.claude/skills` must symlink `../.agents/skills`; never copy skill files.

```bash
test -L .claude/skills && test "$(readlink .claude/skills)" = ../.agents/skills
```

## GitLab MR Flow

- GitLab `origin` is canonical; GitHub `upstream` is source-only.
- Feature MR target: `dev`. Release MR target: `main` from `dev`.
- Before MR ready: implement, run focused checks, run native `/review` when available.
- If `/review` is unavailable, use `.agents/skills/open-work-hub-mr-review-validation/SKILL.md` and state fallback use.
- Do not claim future MR publisher, Codex runner, or release validation CI before scripts exist.
- Do not mutate GitLab state unless explicitly requested.

## Evidence

- Bind evidence to latest source SHA and target merge result.
- Re-run affected checks/review after source change or target change that alters merged surface.
- Exclude secrets, credentialed remotes, `.env`, raw prompts, operations data, and customer data from prompts, comments, artifacts, and diffs.
