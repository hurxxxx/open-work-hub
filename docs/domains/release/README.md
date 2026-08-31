# Release Domain

- Dev infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Prod infra: `ops/compose/open-work-hub-prod.infra.yml`.
- Common entrypoint: `scripts/infra-stack.sh`.
- Immutable production app image: `ops/app/Dockerfile`.
- Production app runtime: `ops/compose/open-work-hub-prod.app.yml`.
- Guarded app entrypoint: `scripts/prod-app.sh`.
- CI contract: `.gitlab-ci.yml` and `ops/ci/ci-first.gitlab-ci.yml`.
- Branch, release, and deployment authorization: root `AGENTS.md`.
- Prefer shared physical infra plus isolated data namespaces when services support it: PostgreSQL database/schema, MinIO bucket/prefix, OpenSearch index prefix, Qdrant collection prefix, Redis DB/key prefix, queue name/group.
- Use env-named service instances only for incompatible lifecycle, security, capacity, or blast-radius requirements. `prod` checkout/branch is an operational guard, not a naming rule for every container.
- Contract package publish: `contracts-v*` tag publishes `@open-work-hub/contracts`.
- Do not document server/user/systemd/internal-network-specific deployment in repo source.
- GitLab `origin/main` is the production source; CI owns release-validation routing.

## Production app contract

- Run app commands only from a clean checkout named `prod` at `origin/main`.
- Keep `.env` aligned with `.env.example`; production preflight rejects dev login/seed flags, an unsafe attachment-signing key, an untrusted proxy wildcard, a non-public origin, and host-port collisions.
- Route the external HTTPS proxy to `OPEN_WORK_HUB_APP_BIND_HOST:OPEN_WORK_HUB_APP_PORT`. When development and production share a legacy ingress port, the Compose-owned edge accepts only the declared development and production hosts, forwards them to their separate upstream ports, and rejects unknown hosts. `OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS` lists only the exact external and loopback edge proxy IPs.
- The app image contains the web build, API, worker, migrations, and collaboration codec at one source revision. The Compose runtime starts the host-aware edge, privacy filter, API, worker, and scheduler with restart policies and health checks.
- `pnpm app:prod:deploy` builds and verifies the revision image, applies migrations, replaces the app runtime, then requires direct, edge-routed, and public health identity plus readiness, revision, bootstrap, and login-shell checks.
- A failed runtime or public smoke restores the previous app image when one exists. Database migrations are not automatically reversed; releases must keep migrations backward-compatible with the previous image.

Read-only checks:

```bash
pnpm app:prod:status
pnpm app:prod:smoke
```

Mutating commands require explicit production scope:

```bash
pnpm app:prod:deploy
pnpm app:prod:rollback
pnpm app:prod:up
```
