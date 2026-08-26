# Release Domain

- Dev infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Prod infra: `ops/compose/open-work-hub-prod.infra.yml`.
- Common entrypoint: `scripts/infra-stack.sh`.
- CI contract: `.gitlab-ci.yml` and `ops/ci/ci-first.gitlab-ci.yml`.
- Prefer shared physical infra plus isolated data namespaces when services support it: PostgreSQL database/schema, MinIO bucket/prefix, OpenSearch index prefix, Qdrant collection prefix, Redis DB/key prefix, queue name/group.
- Use env-named service instances only for incompatible lifecycle, security, capacity, or blast-radius requirements. `prod` checkout/branch is an operational guard, not a naming rule for every container.
- Release validation: GitLab MR `dev -> main` runs non-Codex `release_validation`.
- Contract package publish: `contracts-v*` tag publishes `@open-work-hub/contracts`.
- Do not document server/user/systemd/internal-network-specific deployment in repo source.
- GitLab `origin/main` is production source after approved `dev -> main` release MR.
- This repo currently owns Compose infrastructure only, not full app deploy automation.
