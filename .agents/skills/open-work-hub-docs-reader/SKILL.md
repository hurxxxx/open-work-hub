---
name: open-work-hub-docs-reader
description: Read, extract, summarize, or list updates from Open Work Hub native Docs URLs such as `/w/{workspace}/docs/{doc_id}?page={page_id}` in the current local environment. Use when a user supplies an internal Docs link or asks for recently updated native Docs content. Do not use for repository Markdown files, arbitrary websites, production access, or database writes.
---

# Open Work Hub Docs Reader

## Scope and Safety

- This is a read-only helper for the current checkout's local PostgreSQL-backed Docs data.
- It loads `OPEN_WORK_HUB_POSTGRES_DSN` and MinIO metadata from the process environment, then ignored `.env.local`/`.env`, without printing credentials.
- The normal local Docker database is exposed at `127.0.0.1:55433`; do not assume a native database or internal server checkout.
- Never use this skill to query production, mutate rows, or copy media unless the request actually requires inspecting that media.

## Read a Page

```bash
python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py \
  '/w/general/docs/<doc_id>?page=<page_id>'
```

Useful variants:

```bash
python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py \
  --updates --workspace general --limit 20

python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py \
  --updates --workspace general --doc-id <doc_id> --since '2026-08-01'

python3 .agents/skills/open-work-hub-docs-reader/scripts/read_open_work_hub_doc.py \
  --copy-media /tmp/open-work-hub-doc-media \
  '/w/general/docs/<doc_id>?page=<page_id>'
```

The helper understands both plain `content_text` and block-format `content_blocks`. If no target page is supplied, provide `--workspace` and `--doc-id`.

## Reporting

Include the local environment label, workspace slug, doc/page titles and IDs, concrete update timestamps, readable extracted content, and embedded media metadata. If media was copied, report only the destination paths and metadata; never expose storage credentials.
