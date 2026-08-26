---
name: open-work-hub-runtime-separation-audit
description: Audit Open Work Hub development and production runtime separation across env profiles, ports, Compose projects, containers, and checkout guards. Use when separation itself is requested or a change alters runtime identity, topology, ports, buckets, or production guards. Do not use automatically for every env or Compose edit.
---

# Runtime Separation Audit

Use env-management too only when ignored env files or GitLab CI variable metadata change.

```bash
pnpm check:env-contract
pnpm check:path-hardcoding
git diff -- ops/compose scripts/dev-env.sh scripts/dev-infra.sh scripts/infra-stack.sh .env.example
```

Confirm:

- Dev names/ports/buckets use `open-work-hub-dev`.
- Prod names/ports/buckets use `open-work-hub-prod`.
- Prod Compose has no PostgreSQL service.
- Dev/prod host ports, Redis, MinIO, OpenSearch, Qdrant do not collide.
- `scripts/infra-stack.sh` blocks prod commands outside `prod` checkout.
- `dev.sh`/`scripts/dev-infra.sh` block dev commands from `prod`.
- Dev login/minimal seed cannot become prod default.

Live status: `pnpm infra:dev:status`; prod status only from `prod`. Report names/health/ports/redacted metadata only.
