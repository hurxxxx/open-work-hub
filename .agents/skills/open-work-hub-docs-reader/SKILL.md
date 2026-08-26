---
name: open-work-hub-docs-reader
description: Read, extract, summarize, or list updates from Open Work Hub native Docs URLs such as `/w/{workspace}/docs/{doc_id}?page={page_id}` in the current local environment. Use when a user supplies an internal Docs link or asks for recently updated native Docs content. Do not use for repository Markdown files, arbitrary websites, production access, or database writes.
---

# Docs Reader

Read-only helper for local PostgreSQL-backed Docs data.

## Rules

- Loads `OPEN_WORK_HUB_POSTGRES_DSN` and MinIO metadata without printing credentials.
- Normal local DB: `127.0.0.1:55433`.
- Never query production or mutate rows.
- Copy media only when required; report paths/metadata only.

## Commands

```bash
python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py '/w/general/docs/<doc_id>?page=<page_id>'
python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py --updates --workspace general --limit 20
python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py --copy-media /tmp/open-work-hub-doc-media '/w/general/docs/<doc_id>?page=<page_id>'
```

Report env label, workspace, doc/page IDs/titles, timestamps, extracted content, and media metadata.
