---
name: owh-docs-reader
description: Use when reading native local Docs links or recent Docs updates. Extracts pages and optional media from verified dev storage; excludes repository Markdown, remote/production access, and database writes.
---

# Docs Reader

Read-only helper for local PostgreSQL-backed Docs data.

## Rules

- Loads `OPEN_WORK_HUB_POSTGRES_DSN` and MinIO metadata without printing credentials.
- Verifies dev profile, loopback DSN/dev database, dev Compose labels, and dev bucket before querying. Normal local DB is `127.0.0.1:55433`; remote/prod identities fail closed.
- Never query production or mutate rows.
- Copy media only when required, into an explicitly selected empty directory; report paths/metadata only. Limits are 20 files, 50 MiB each, and 30 seconds per subprocess. Temporary media and private mc config are cleaned up on success/failure; existing files are never overwritten.

## Commands

```bash
python3 .agents/skills/owh-docs-reader/scripts/read_open_work_hub_doc.py '/apps/docs/<doc_id>?page=<page_id>'
python3 .agents/skills/owh-docs-reader/scripts/read_open_work_hub_doc.py --updates --limit 20
python3 .agents/skills/owh-docs-reader/scripts/read_open_work_hub_doc.py --copy-media /tmp/open-work-hub-doc-media '/apps/docs/<doc_id>?page=<page_id>'
```

Report env label, content owner/ownership, doc/page IDs/titles, timestamps, extracted content, and media metadata.
