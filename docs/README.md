# Open Work Hub Docs

Use the narrowest owner doc. Code and tests are final for implemented behavior.

| Area | Start |
| --- | --- |
| Development installation / 개발 환경 설치 | [INSTALL.md](../INSTALL.md) |
| Agent routing/validation/MR | [agents/domain.md](agents/domain.md) |
| App-specific owner docs | [apps/README.md](apps/README.md) |
| App registration/RBAC/bootstrap | [domains/app-platform/README.md](domains/app-platform/README.md) |
| Indexed source authorization | [domains/source-access/README.md](domains/source-access/README.md) |
| Authenticated content delivery | [domains/content-access/README.md](domains/content-access/README.md) |
| Global notifications | [domains/notifications/README.md](domains/notifications/README.md) |
| AI Gateway/execution/write policy | [domains/ai/README.md](domains/ai/README.md) |
| Inference Gateway | [domains/inference-gateway/README.md](domains/inference-gateway/README.md) |
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

Git workflow and upstream contribution authorization: [root agent rules](../AGENTS.md#git-and-delivery).
Issue/MR rules: [Issue Tracker](agents/issue-tracker.md), [Vibe Harness](agents/vibe-coding-harness.md).

Do not add parallel current-truth trees, raw logs, progress dumps, or large generated artifacts.
