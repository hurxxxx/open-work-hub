---
name: open-work-hub-agent-skill-governance
description: Maintain Open Work Hub project skills, trigger metadata, supporting resources, and skill-harness checks. Use when adding, changing, auditing, renaming, or removing `.agents/skills` entries. Do not use for ordinary work that only consumes an existing skill.
---

# Open Work Hub Agent Skill Governance

## Rules

- Project skills live under `.agents/skills`; do not duplicate them under tool-specific directories.
- Keep each description precise enough to select the skill from the user's requested outcome. Add a `Do not use for` boundary when an adjacent skill or ordinary implementation could otherwise match.
- A referenced skill is routing guidance, not permission to expand the task. Load it only when its own trigger matches.
- Root `AGENTS.md` owns common safety, routing, and collaboration rules. Do not repeat them in every skill.
- Keep `SKILL.md` focused on essential workflow and invariants. Put conditional detail in a directly linked reference and deterministic repeated work in `scripts/`.
- Preserve useful metadata and resources when updating an imported skill. Remove stale project-specific workflows and references in the same change.
- Folder and frontmatter names use lowercase letters, digits, and hyphens and must match exactly.

## Workflow

1. Inspect neighboring skill descriptions for overlap before adding a new skill.
2. Prefer sharpening an existing owner over creating two skills for the same outcome.
3. Run the repository harness:

   ```bash
   python3 scripts/check-skill-harness.py
   python3 -m unittest scripts.tests.test_skill_harness
   ```

4. Run every changed bundled script with a safe syntax/help/dry-run path as applicable.
5. Review `git diff --check` and confirm no generated cache or secret file entered the diff.
