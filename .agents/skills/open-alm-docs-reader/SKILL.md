---
name: open-alm-docs-reader
description: Use when asked to read, extract, summarize, or check updates for Open ALM internal Docs URLs such as /w/{workspace}/docs/{doc_id}?page={page_id}. Handles native Open ALM dev/prod PostgreSQL and MinIO containers, including block-format pages where content_text is empty and content is stored in content_blocks.
---

# Open ALM Docs Reader

## Scope

Use this skill for Open ALM internal Docs links and requests to find recently updated Docs content. The only runtime environments are `dev` and `prod`.

Never update the database from this skill. Treat all SQL as read-only.

## Quick Start

Prefer the bundled helper:

```bash
python3 .agents/skills/open-alm-docs-reader/scripts/read_open_alm_doc.py '/w/ai-tft/docs/8ddf3e81-9bfd-4877-a2e6-504b28f4cbc2?page=edd8d579-1216-40c9-b186-8aebe148ff28'
```

Useful variants:

```bash
# Search only one environment.
python3 .agents/skills/open-alm-docs-reader/scripts/read_open_alm_doc.py --env prod '/w/ai-tft/docs/<doc_id>?page=<page_id>'

# List recently updated pages in a workspace.
python3 .agents/skills/open-alm-docs-reader/scripts/read_open_alm_doc.py --updates --workspace ai-tft --env prod --limit 20

# List recently updated pages in one doc since a date/time.
python3 .agents/skills/open-alm-docs-reader/scripts/read_open_alm_doc.py --updates --workspace ai-tft --doc-id <doc_id> --since '2026-05-20'

# Copy embedded media from MinIO for inspection.
python3 .agents/skills/open-alm-docs-reader/scripts/read_open_alm_doc.py --env prod --copy-media /tmp/open-alm-doc-media '/w/ai-tft/docs/<doc_id>?page=<page_id>'
```

## Environment Map

- `dev`: native PostgreSQL on `127.0.0.1:5432`, user/database `open_alm_dev`, MinIO container `open-alm-dev-minio`, bucket `open-alm-dev`.
- `prod`: native PostgreSQL on `127.0.0.1:5432`, user/database `open_alm_prod`, MinIO container `open-alm-prod-minio`, bucket `open-alm-prod`.

Default helper behavior is `--env all`, checking dev then prod.

PostgreSQL must not be accessed through Docker. If native DB access or a required extension is missing, fix the native PostgreSQL environment instead of starting a Postgres container.

## Manual SQL Fallback

If the helper is unavailable, query `docs_native_docs` joined to `docs_native_doc_pages` and `workspaces`.

```bash
psql -h 127.0.0.1 -U open_alm_prod -d open_alm_prod -P pager=off -F $'\t' -Atc "
select
  w.key,
  d.id,
  d.title,
  d.updated_at,
  p.id,
  p.title,
  p.content_format,
  p.updated_at,
  coalesce(length(p.content_text), 0),
  case
    when json_typeof(p.content_blocks) = 'array' then json_array_length(p.content_blocks)
    else 0
  end
from docs_native_docs d
join docs_native_doc_pages p on p.doc_id = d.id
join workspaces w on w.id = d.workspace_id
where w.key = 'ai-tft'
  and d.id = '<doc_id>'
  and p.id = '<page_id>';
"
```

For block-format docs, `content_text` is often empty. Extract text from `content_blocks` instead of assuming the page is blank.

## Reporting

When reporting a document read, include:

- Environment where it was found (`dev` or `prod`).
- Workspace slug, doc title/id, page title/id.
- `doc_updated_at` and `page_updated_at`.
- Extracted content in readable order.
- Embedded media IDs and filenames, and copied file paths if `--copy-media` was used.

When asked about updates, sort by the most recent doc/page update and report concrete timestamps.
