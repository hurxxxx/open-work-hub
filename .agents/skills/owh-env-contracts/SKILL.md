---
name: owh-env-contracts
description: Use when changing or auditing typed env contracts, installing ignored env files, or auditing dev/prod runtime separation. Excludes incidental env mentions, service operations, secret rotation, and unrequested GitLab changes.
---

# Environment Contracts

Choose only the affected contract:
- Keys/settings/ignored files: read [env-files.md](references/env-files.md).
- Runtime identity, ports, storage namespaces, or checkout guards: read [separation.md](references/separation.md).

Use typed OPEN_WORK_HUB_* settings; browser-visible VITE_OPEN_WORK_HUB_* values cannot contain secrets.
Report keys, counts, file modes, checksums, and redacted status. Env installation does not authorize restarting services.
Production checkout is an execution guard, not a requirement to rename every shared physical service; use [release ownership](../../../docs/domains/release/README.md) for the current topology contract.

Run `pnpm check:env-contract` and `pnpm check:path-hardcoding`; verify modified helpers with fixtures.
