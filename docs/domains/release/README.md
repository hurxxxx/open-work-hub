# Release Domain

- Dev infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Prod infra: `ops/compose/open-work-hub-prod.infra.yml`.
- Common entrypoint: `scripts/infra-stack.sh`.
- Do not document server/user/systemd/internal-network-specific deployment in repo source.
- GitLab `origin/main` is production source after approved `dev -> main` release MR.
- This repo currently owns Compose infrastructure only, not full app deploy automation.
