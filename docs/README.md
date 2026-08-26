# Open Work Hub Docs

Use the narrowest owner doc. Code and tests are final for implemented behavior.

| Area | Start |
| --- | --- |
| Agent routing/validation/MR | [agents/domain.md](agents/domain.md) |
| App registration/RBAC/bootstrap | [domains/app-platform/README.md](domains/app-platform/README.md) |
| AI Gateway/model routing | [domains/ai/gateway.md](domains/ai/gateway.md) |
| Retrieval/RAG | [domains/retrieval/README.md](domains/retrieval/README.md), [domains/rag/README.md](domains/rag/README.md) |
| Organization/directory | [domains/organization/README.md](domains/organization/README.md) |
| Platform integrations/API keys | [domains/integrations/README.md](domains/integrations/README.md) |
| Runtime/release | [domains/release/README.md](domains/release/README.md) |
| UI/product rules | [product/README.md](product/README.md) |

| Path | Owner |
| --- | --- |
| `domains/` | cross-app technical contracts/runbooks |
| `apps/` | one app's behavior/contracts |
| `agents/` | AI coding-agent routing and checks |
| `product/` | product-wide UI/data rules |
| `../adr/` | accepted architecture decisions |

GitLab `origin` is canonical for this site. GitHub `upstream` is source-only.
Issue/MR rules: [Issue Tracker](agents/issue-tracker.md), [Vibe Harness](agents/vibe-coding-harness.md).

Do not add parallel current-truth trees, raw logs, progress dumps, or large generated artifacts.
