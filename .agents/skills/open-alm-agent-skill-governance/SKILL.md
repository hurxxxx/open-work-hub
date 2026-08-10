---
name: open-alm-agent-skill-governance
description: Maintain Open ALM project skills, trigger metadata, stale workflow removal, and skill harness validation. Use when adding, changing, auditing, or removing .agents/skills entries. Do not use for ordinary work that only consumes an existing skill.
---

# Open ALM Agent Skill Governance

## Rules

- Project skills live under `.agents/skills`.
- Do not add project skills under `.codex/skills`.
- Keep each skill focused on one operational capability.
- Every description must identify the concrete task outcome that triggers the
  skill. A file path, domain word, or incidental implementation detail is not a
  sufficient trigger.
- Add a `Do not use for` boundary when adjacent skills or ordinary
  implementation could otherwise match.
- Referencing another skill is routing guidance, not an instruction to load it.
  Add another skill only when its own task outcome is in scope.
- Root `agents.md` owns common skill-selection and parallel-work policy. Do not
  repeat it in individual skills.
- Keep `SKILL.md` below 8 KiB and limited to routing, invariants, and the shortest
  useful workflow. Move optional detail to a directly linked reference or a
  deterministic script.
- Retired workflows must be removed from skills and docs in the same change.

## Workflow

```bash
pnpm check:skills
```

Review description overlap before adding a new skill. Prefer sharpening an
existing owner over creating a second workflow for the same outcome.
