---
name: write-a-skill
description: Create or update an agent skill with precise discovery metadata, scoped instructions, and only the supporting resources the workflow needs. Use when the user asks to create, write, restructure, or audit a skill. Do not use for ordinary implementation that merely follows an existing skill.
---

# Write A Skill

## Rules

- Include only guidance that changes decisions, prevents risk, or makes repeated work reliable.
- Skill routes work; it does not authorize unrelated files, external writes, deploys, or destructive actions.
- `description` states outcome, triggers, and neighboring-skill boundary; it includes `Use when`.
- `SKILL.md` stays short. Put needed conditional detail in references and repeated deterministic work in scripts.
- No empty resource dirs, duplicate quick refs, install notes, or speculative examples.
- Names are lowercase/digits/hyphens, under 64 chars, and match frontmatter.

## Workflow

1. Infer requirements from request/repo; ask only material questions.
2. Inspect adjacent skills for overlap.
3. Write purpose, constraints, workflow, and resource routing.
4. Validate changed scripts with syntax/help/fixture/dry-run path.
5. Run:

```bash
python3 scripts/check-skill-harness.py
python3 -m unittest scripts.tests.test_skill_harness
git diff --check
```
