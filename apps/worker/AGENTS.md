# Worker Agent Rules

- Start with current worker code/tests and the owning domain/app document for the task.
- Register tasks through the deployed worker bootstrap and existing queue routing; code that is not discoverable at runtime is incomplete.
- Recheck runtime app availability after claim and before provider or app-data mutation.
- Make retryable work idempotent; define retry, timeout, checkpoint, fencing, and cleanup behavior explicitly.
- Persist shared/auditable progress in authoritative storage, not worker memory or `/tmp`.
- Preserve queue-group isolation and Beat ownership; do not add ad hoc process startup paths.
- Run focused worker pytest and registration tests first, then `pnpm nx lint worker` when the surface warrants it.
