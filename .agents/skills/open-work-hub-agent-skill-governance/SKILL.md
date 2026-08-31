---
name: open-work-hub-agent-skill-governance
description: Maintain Open Work Hub project skills, trigger metadata, supporting resources, and skill-harness checks. Use when adding, changing, auditing, renaming, or removing `.agents/skills` entries. Do not use for ordinary work that only consumes an existing skill.
---

# Skill Governance

## Rules

- Project skills live only under `.agents/skills`.
- `.claude/skills` links to the canonical directory; run `pnpm setup:claude-skills` instead of copying skills.
- Description must discriminate trigger, include `Use when`, and state boundary when adjacent skills overlap.
- Skill reference is routing, not scope expansion.
- `AGENTS.md` owns common rules; do not repeat them in every skill.
- `SKILL.md` contains only workflow/invariants/resource routing.
- Names are lowercase/digits/hyphens, under 64 chars, and match frontmatter.

## Checks

```bash
python3 scripts/check-skill-harness.py
python3 -m unittest scripts.tests.test_skill_harness
pnpm test:claude-skills
git diff --check
```

Run changed bundled scripts with syntax/help/fixture/dry-run path.
