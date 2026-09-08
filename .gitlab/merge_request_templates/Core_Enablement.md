<!-- open-work-hub:core-enablement:v1 -->

# Core Enablement

Keep this description below 2,700 characters. Link logs and owning decisions.

## Enablement Contract

- Outcome/non-goals: <!-- open-work-hub:field:outcome --> REPLACE_ME
- Protected surfaces/owners; LLM workload IDs/adapter/external-data policy/output caps or N/A: <!-- open-work-hub:field:protected-surfaces --> REPLACE_ME
- App-owned boundary after merge: <!-- open-work-hub:field:app-boundary --> REPLACE_ME
- Activation owner/MR/condition: <!-- open-work-hub:field:activation --> REPLACE_ME
- Compatibility/rollback: <!-- open-work-hub:field:compatibility --> REPLACE_ME
- Company search (`none - reason` or `company - required evidence`): <!-- open-work-hub:field:company-keyword-search --> REPLACE_ME

- [ ] <!-- open-work-hub:check:independent-deployable --> Scaffold is independently deployable.
- [ ] <!-- open-work-hub:check:hidden-default --> Incomplete app stays hidden/disabled/unscheduled.
- [ ] <!-- open-work-hub:check:extension-contracts --> Registry/API/RBAC/worker/AI contracts tested; independently configurable LLM functions have registered workloads, output caps, audit, common interface, and direct-call guard evidence.
- [ ] <!-- open-work-hub:check:activation-owner --> Activation ownership is explicit.
- [ ] <!-- open-work-hub:check:company-keyword-search --> Backend registry is authoritative; app availability, source ACL, empty/missing-index, backfill, smoke, and rollback evidence are recorded, or `none` has a reason.

## Verification Evidence

- Pipeline diff-base SHA: <!-- open-work-hub:field:target-state --> REPLACE_ME
- Source SHA: <!-- open-work-hub:field:source-sha --> REPLACE_ME
- Checks/CI links and negative scenarios: <!-- open-work-hub:field:verification --> REPLACE_ME

- [ ] <!-- open-work-hub:check:merge-result --> Latest diff/merge result reviewed.
- [ ] <!-- open-work-hub:check:affected-checks --> Affected checks ran on source SHA.

## Core Review

- [ ] <!-- open-work-hub:check:core-review --> Core owner reviewed protected composition changes.

Remaining risks / intentionally unverified: <!-- open-work-hub:field:remaining-risks --> REPLACE_ME
