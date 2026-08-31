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
- Keep `.env` aligned with `.env.example`; production preflight rejects dev login/seed flags, an unsafe attachment-signing key, an untrusted proxy wildcard, non-public or shared app/Bento origins, and host-port collisions.
- Route each public hostname directly from the external HTTPS proxy to its declared service port. `OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS` lists only the exact external proxy IPs. Bind Bento to loopback for a local proxy or the exact private proxy-facing interface IP; production rejects wildcard, public-IP, and hostname bindings.
- The app image contains the web build, API, worker, migrations, and collaboration codec at one source revision. The Compose runtime starts the privacy filter, API, worker, and scheduler with restart policies and health checks.
- The image build embeds the validated `OPEN_WORK_HUB_BENTO_SERVER_URL` in the static web bundle; changing that public origin requires a new app image.
- `pnpm app:prod:deploy` builds and verifies the revision image, applies migrations, replaces the app runtime, then requires direct and public health identity plus readiness, revision, bootstrap, and login-shell checks.
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
