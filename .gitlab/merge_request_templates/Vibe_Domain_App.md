<!-- ai-do:vibe-app-contract:v1 -->

# Vibe Domain App

Keep this description below 2,700 characters. Link logs; explain N/A checks.

## Contract Map

- Outcome/non-goals; scaffold/Core MR: <!-- ai-do:field:contract-outcome --> REPLACE_ME
- App/owner/route/entitlement; data/store/RBAC: <!-- ai-do:field:contract-boundaries --> REPLACE_ME
- API/UI/i18n/a11y; file/network/budgets: <!-- ai-do:field:contract-interfaces --> REPLACE_ME
- AI workloads/data policy/output caps; worker/Linux; migration/compatibility: <!-- ai-do:field:contract-runtime --> REPLACE_ME
- Workspace search (`none — reason` or `workspace — required evidence`): <!-- ai-do:field:workspace-keyword-search --> REPLACE_ME

- [ ] <!-- ai-do:check:scaffold --> Scaffold/Core MR ready.
- [ ] <!-- ai-do:check:app-owned-surface --> App-only diff; no guard bypass.
- [ ] <!-- ai-do:check:lane --> One exact `dev` lane.

## Data, Authorization, And Safety

- [ ] <!-- ai-do:check:authorization --> Server auth/RBAC negative tests.
- [ ] <!-- ai-do:check:transaction --> Transaction/retry/concurrency/cleanup.
- [ ] <!-- ai-do:check:file-network --> File/URL security and caps.
- [ ] <!-- ai-do:check:ai --> Function-level registered LLM workloads/common Interface/local+external output caps (default 32K/64K)/both
  budgets/audit/external-data/approval; workload route is the sole route selector, AI security does not reroute, and there is no provider/core direct call or guard bypass, or N/A.
- [ ] <!-- ai-do:check:worker --> Worker import/queue/retry/Linux.
- [ ] <!-- ai-do:check:compatibility --> Data/routes/workflows compatible.
- [ ] <!-- ai-do:check:workspace-keyword-search --> Registry/ACL/index evidence complete, or `none` has a reason.

Evidence or N/A reasons: <!-- ai-do:field:safety-evidence --> REPLACE_ME

## Verification Evidence

- Pipeline diff-base SHA: <!-- ai-do:field:target-state --> REPLACE_ME
- Source SHA: <!-- ai-do:field:source-sha --> REPLACE_ME
- Checks/CI links and negative scenarios: <!-- ai-do:field:verification --> REPLACE_ME

- [ ] <!-- ai-do:check:merge-result --> Latest diff/merge result reviewed.
- [ ] <!-- ai-do:check:scope-clean --> Scope clean; no manual/policy workaround.
- [ ] <!-- ai-do:check:affected-checks --> Affected checks ran on source SHA.

## Independent Review

- [ ] <!-- ai-do:check:independent-review --> `/review` or MR review skill ran.
- [ ] <!-- ai-do:check:review-freshness --> SHA/base change revalidated/re-reviewed.
- [ ] <!-- ai-do:check:remaining-risks --> Blockers cleared; risks below.

Remaining risks / intentionally unverified: <!-- ai-do:field:remaining-risks --> REPLACE_ME
