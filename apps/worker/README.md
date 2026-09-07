# Worker App

Celery background worker.

Tasks:

- AI graph dispatch/execution
- document/RAG sync and search indexing
- OCR/document extraction
- meeting/recording processing
- mail sync
- media and orphaned-storage cleanup

Run:

```bash
./dev.sh --with-worker
```

Use root `.env.example` plus ignored `.env`. Do not commit secrets or operations data.

Beat's production health check measures recent successful task publication, independently of
worker ping and API health. See the [runtime contract](../../docs/domains/release/README.md#production-app-contract).

Executable app-owned user work rechecks runtime availability after claim and before provider or
app-data mutation. Compensating cleanup may continue after disablement when its only effect is
removing orphaned/expired storage; it must not publish new user-visible app state. The
[App Platform Contract](../../docs/domains/app-platform/README.md) owns the shared rule, the
[AI Execution Contract](../../docs/domains/ai/execution.md) owns graph claims/checkpoints, and the
[Recording App](../../docs/apps/recording/README.md) owns recording attempt/version fencing.
