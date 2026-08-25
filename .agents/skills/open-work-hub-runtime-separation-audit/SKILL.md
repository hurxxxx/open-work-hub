---
name: open-work-hub-runtime-separation-audit
description: Audit Open Work Hub development and production runtime separation across env profiles, ports, Compose projects, containers, and checkout guards. Use when separation itself is requested or a change alters runtime identity, topology, ports, buckets, or production guards. Do not use automatically for every env or Compose edit.
---

# Open Work Hub Runtime Separation Audit

Add `open-work-hub-env-management` only when the task also changes ignored env files or GitHub secret metadata.

## Static Audit

```bash
pnpm check:env-contract
pnpm check:path-hardcoding
git diff -- ops/compose scripts/dev-env.sh scripts/dev-infra.sh scripts/infra-stack.sh .env.example
```

Confirm:

- Dev uses `open-work-hub-dev` Compose/container/volume/network names and the local PostgreSQL service.
- Prod uses `open-work-hub-prod` Compose/container/volume/network names and has no production PostgreSQL service in the current Compose file.
- Different defaults for shared host ports, buckets, Redis, MinIO, OpenSearch, and Qdrant do not collide.
- `scripts/infra-stack.sh` rejects production commands outside a checkout named `prod`.
- `dev.sh` and `scripts/dev-infra.sh` reject development operations from a `prod` checkout.
- Dev login/minimal seed settings cannot become production defaults.

## Live Audit

Run only in the relevant checkout with Docker available:

```bash
pnpm infra:dev:status
```

Run `pnpm infra:prod:status` only from the dedicated `prod` checkout. Report service names, health, bound ports, and redacted profile/key metadata; never print `.env` values.

The repository has no live full-application separation checker and no full production deploy. Do not claim API identity or application deployment separation without separately verified runtime evidence.
