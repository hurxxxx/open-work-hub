<!-- ai-do:core-enablement:v1 -->

# Core Enablement

Keep this description below 2,700 characters. Link logs and owning decisions.

## Enablement Contract

- Outcome/non-goals: <!-- ai-do:field:outcome --> REPLACE_ME
- Protected surfaces/owners; function-level LLM workload ids/Adapter/external-data policy/local+external output caps or N/A: <!-- ai-do:field:protected-surfaces --> REPLACE_ME
- App-owned boundary after merge: <!-- ai-do:field:app-boundary --> REPLACE_ME
- Activation owner/MR/condition: <!-- ai-do:field:activation --> REPLACE_ME
- Compatibility/rollback: <!-- ai-do:field:compatibility --> REPLACE_ME
- Workspace search (`none — reason` or `workspace — required evidence`): <!-- ai-do:field:workspace-keyword-search --> REPLACE_ME

- [ ] <!-- ai-do:check:independent-deployable --> Scaffold is independently deployable.
- [ ] <!-- ai-do:check:hidden-default --> Incomplete app stays hidden/disabled/unscheduled.
- [ ] <!-- ai-do:check:extension-contracts --> Registry/API/RBAC/worker/AI contracts tested;
  every independently configurable LLM function has a registered workload, local/external output caps (default 32K/64K), audit, common Interface, and
  direct-call guard evidence; workload route override is the sole route selector and AI security only allow/mask/block/audits external payloads.
- [ ] <!-- ai-do:check:activation-owner --> Activation ownership is explicit.
- [ ] <!-- ai-do:check:workspace-keyword-search --> Backend registry is authoritative; entitlement, ACL, empty/missing-index, backfill, smoke, and rollback evidence are recorded, or `none` has a reason.

## Verification Evidence

- Pipeline diff-base SHA: <!-- ai-do:field:target-state --> REPLACE_ME
- Source SHA: <!-- ai-do:field:source-sha --> REPLACE_ME
- Checks/CI links and negative scenarios: <!-- ai-do:field:verification --> REPLACE_ME

- [ ] <!-- ai-do:check:merge-result --> Latest diff/merge result reviewed.
- [ ] <!-- ai-do:check:affected-checks --> Affected checks ran on source SHA.

## Core Review

- [ ] <!-- ai-do:check:core-review --> Core owner reviewed protected composition changes.

Remaining risks / intentionally unverified: <!-- ai-do:field:remaining-risks --> REPLACE_ME
