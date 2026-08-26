# Worker App

Celery background worker.

Tasks:

- document/RAG sync
- OCR/document extraction
- meeting/recording processing
- mail sync
- search indexing
- draft export

Run:

```bash
./dev.sh --with-worker
```

Use root `.env.example` plus ignored `.env`. Do not commit secrets or operations data.
