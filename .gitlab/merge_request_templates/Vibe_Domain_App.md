<!-- open-work-hub:vibe-app-contract:v1 -->

# Vibe Domain App

Keep this description below 2,700 characters. Link logs; explain N/A checks.

## Contract Map

- Outcome/non-goals; scaffold/Core MR: <!-- open-work-hub:field:contract-outcome --> REPLACE_ME
- App/owner/route/entitlement; data/store/RBAC: <!-- open-work-hub:field:contract-boundaries --> REPLACE_ME
- API/UI/i18n/a11y; file/network/budgets: <!-- open-work-hub:field:contract-interfaces --> REPLACE_ME
- AI workloads/data policy/output caps; worker/Linux; migration/compatibility: <!-- open-work-hub:field:contract-runtime --> REPLACE_ME
- Workspace search (`none - reason` or `workspace - required evidence`): <!-- open-work-hub:field:workspace-keyword-search --> REPLACE_ME

- [ ] <!-- open-work-hub:check:scaffold --> Scaffold/Core MR ready.
- [ ] <!-- open-work-hub:check:app-owned-surface --> App-only diff; no guard bypass.
- [ ] <!-- open-work-hub:check:target --> Feature MR targets GitLab `dev`.

## Data, Authorization, And Safety

- [ ] <!-- open-work-hub:check:authorization --> Server auth/RBAC negative tests.
- [ ] <!-- open-work-hub:check:transaction --> Transaction/retry/concurrency/cleanup.
- [ ] <!-- open-work-hub:check:file-network --> File/URL security and caps.
- [ ] <!-- open-work-hub:check:ai --> Registered LLM workloads/common interface/output caps/budgets/audit/external-data/approval; workload route is the sole route selector and there is no provider direct call or guard bypass, or N/A.
- [ ] <!-- open-work-hub:check:worker --> Worker import/queue/retry/Linux.
- [ ] <!-- open-work-hub:check:compatibility --> Data/routes/workflows compatible.
- [ ] <!-- open-work-hub:check:workspace-keyword-search --> Registry/ACL/index evidence complete, or `none` has a reason.

Evidence or N/A reasons: <!-- open-work-hub:field:safety-evidence --> REPLACE_ME

## Verification Evidence

- Pipeline diff-base SHA: <!-- open-work-hub:field:target-state --> REPLACE_ME
- Source SHA: <!-- open-work-hub:field:source-sha --> REPLACE_ME
- Checks/CI links and negative scenarios: <!-- open-work-hub:field:verification --> REPLACE_ME

- [ ] <!-- open-work-hub:check:merge-result --> Latest diff/merge result reviewed.
- [ ] <!-- open-work-hub:check:scope-clean --> Scope clean; no manual/policy workaround.
- [ ] <!-- open-work-hub:check:affected-checks --> Affected checks ran on source SHA.

## Independent Review

- [ ] <!-- open-work-hub:check:independent-review --> MR review skill or approved reviewer ran.
- [ ] <!-- open-work-hub:check:review-freshness --> SHA/base change revalidated/re-reviewed.
- [ ] <!-- open-work-hub:check:remaining-risks --> Blockers cleared; risks below.

Remaining risks / intentionally unverified: <!-- open-work-hub:field:remaining-risks --> REPLACE_ME
