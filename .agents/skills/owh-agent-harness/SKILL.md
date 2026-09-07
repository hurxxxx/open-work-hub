---
name: owh-agent-harness
description: Use when maintaining project instructions, skills, Codex lifecycle hooks/evals, or GitLab Codex review automation. Excludes ordinary coding and reviewing a particular MR.
---

# Agent Harness

Keep common rules in root AGENTS.md and reusable skills in .agents/skills; .claude/skills links to that directory.
Use the [harness owner](../../../docs/agents/vibe-coding-harness.md) for instruction design, hook contracts, evidence, and checks.

- Skills/instructions: specify discriminating triggers, the requested outcome, and conditional resources. Preserve boundaries while removing duplicate rules.
- Local Codex hooks: use official event schemas and narrow deterministic handlers; test actual allow/block behavior, failures, and overhead. Never infer authorization from prompt text.
- GitLab review automation: read [ci-review.md](references/ci-review.md). MR-source guidance and hooks are review input, never trusted runtime policy.

For substantial skill changes, compare representative independent executions using the same tasks/model and deterministic outcome checks. Measure trigger, compliance, boundary, tokens, and time separately. Metadata checks do not prove behavior.

Run `pnpm check:skills`, `pnpm test:skill-harness`, `pnpm test:claude-skills`, and `git diff --check`; add `pnpm test:codex-hooks` for hooks/evals and `pnpm ci:harness` for shared harness changes. Exercise changed bundled scripts with syntax/help/fixtures.
