# Agent Docs Routing

Read only the file that owns the current decision.

| Decision | Owner |
| --- | --- |
| code shape/entrypoints | [llm-friendly-development.md](llm-friendly-development.md) |
| validation depth/MR flow | [vibe-coding-harness.md](vibe-coding-harness.md) |
| UI reuse | [ui-components.md](ui-components.md) |
| shared model vs local assembly | [composable-abstractions.md](composable-abstractions.md) |
| Codex MR review | [local-codex-review.md](local-codex-review.md) |
| GitLab issues | [issue-tracker.md](issue-tracker.md) |
| GitLab labels | [triage-labels.md](triage-labels.md) |

- Start from current code/tests, then owner docs/ADRs.
- Domain/app docs live under `docs/domains/<domain>/` and `docs/apps/<app-id>/`.
- Product UI/data rules live under `docs/product/`.
- GitLab `origin` Issue/MR state is canonical; GitHub `upstream` is source-only.
- Do not create context maps, current snapshots, nested ADRs, progress archives, or raw-output docs.
