---
name: write-a-skill
description: Create or update an agent skill with precise discovery metadata, scoped instructions, and only the supporting resources the workflow needs. Use when the user asks to create, write, restructure, or audit a skill. Do not use for ordinary implementation that merely follows an existing skill.
---

# Write a Skill

## Design Principles

- Assume the agent is capable. Include only non-obvious guidance that changes decisions, prevents real risk, or makes repeated work reliable.
- Preserve the user's scope and authorization. A skill routes work; it does not grant permission for unrelated files, external writes, deployments, or destructive actions.
- Make discovery cheap: the frontmatter `description` states what outcome the skill supports, concrete triggers, and a boundary when neighboring skills could misroute.
- Keep the entrypoint focused. Move substantial conditional details into directly linked references and deterministic repeated operations into scripts.
- Do not add empty resource directories, duplicated quick references, installation notes, or speculative examples.

## Structure

```text
skill-name/
├── SKILL.md
├── references/   # only when conditional maintained detail is needed
├── scripts/      # only for useful repeatable automation
└── assets/       # only when files are copied into task output
```

Names use lowercase letters, digits, and hyphens, stay below 64 characters, and match the folder. Frontmatter requires `name` and a discriminating `description` containing `Use when`.

## Workflow

1. Infer clear requirements from the request and repository before asking questions. Ask only when a missing choice materially changes the skill.
2. Inspect adjacent skills and callers so an update preserves useful metadata/resources and does not create overlapping ownership.
3. Write essential purpose, constraints, workflow, and resource routing in `SKILL.md`.
4. Add scripts only when deterministic execution improves repeated reliability; validate every new or changed script with a safe help, syntax, fixture, or dry-run path.
5. Validate project skills with:

   ```bash
   python3 scripts/check-skill-harness.py
   python3 -m unittest scripts.tests.test_skill_harness
   ```

6. Review descriptions for selection quality, verify every relative reference resolves, and run `git diff --check`.
