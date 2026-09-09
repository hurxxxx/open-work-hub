# Runtime Separation Audit

Read [env-files.md](env-files.md) only when ignored env files or GitLab CI variable metadata are affected.

```bash
pnpm check:env-contract
pnpm check:path-hardcoding
git diff -- ops/compose scripts/dev-env.sh scripts/dev-infra.sh scripts/infra-stack.sh .env.example
```

Confirm:

- Dev names/ports/buckets use `open-work-hub-dev`.
- Verify production identity against the release owner and current Compose contract; shared site-named services are valid.
- Site-scoped production PostgreSQL keeps the `open-work-hub-postgres` identity; do not rename it to an environment identity without an isolation reason.
- Dev/prod host ports, Redis, MinIO, OpenSearch, Qdrant do not collide.
- The production app and privacy-filter ports do not collide with dev or infra ports. The privacy-filter endpoint stays on loopback, and proxy trust lists exact IPs rather than a wildcard.
- `scripts/infra-stack.sh` blocks prod commands outside `prod` checkout.
- `scripts/prod-app.sh` blocks production app mutation outside a clean `prod` checkout at `origin/main`.
- `dev.sh`/`scripts/dev-infra.sh` block dev commands from `prod`.
- Dev login/minimal seed cannot become prod default.

Live status: `pnpm infra:dev:status`; prod status only from `prod`. Report names/health/ports/redacted metadata only.
