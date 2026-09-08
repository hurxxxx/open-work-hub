# Bento Slides

Open Work Hub embeds official `bento/slides` single-HTML runtime in a separate-origin iframe. Hub owns document list/auth/storage; Bento owns editing and `.bento.html` serialization.

## Pinned Runtime

- Source: <https://github.com/nyblnet/bento>
- Release: `v1.0.17`
- Revision: `efc0fab48ed1a9531bb1ae2a652a091832f64254`
- Release SHA-256: `06026f088399a7422696ef122f424f09d4735fd128ae398392af31ce50ebdf9b`
- License: MIT

`ops/bento/Dockerfile` verifies release/license/notice checksums and adds only the Work Hub bridge.
Runtime upgrade updates tag, revision, checksums, and build evidence together. Before promotion,
manually smoke create/save/import/export against the rendered editor; the repository currently has
protocol unit coverage but no dedicated Bento browser harness.

## Runtime

```bash
./scripts/dev-infra.sh up
docker compose --env-file .env.example -f ops/compose/open-work-hub-dev.infra.yml up -d --build bento
```

- Local URL: `http://127.0.0.1:18084/`
- Health: `/healthz`
- Public env: `OPEN_WORK_HUB_BENTO_SERVER_URL`
- The external HTTPS proxy connects the dedicated Bento hostname directly to `OPEN_WORK_HUB_BENTO_BIND_HOST:OPEN_WORK_HUB_BENTO_PORT`. Keep the default loopback binding for a local proxy; otherwise use only the exact private proxy-facing IPv4 address. Wildcard, public-IP, IPv6, and hostname bindings are forbidden in production.
- Do not serve Bento below the Hub origin; iframe must not access Hub storage/tokens.

## Data/Auth

- Runtime availability for app `bento` gates the hub, document API, and editor route.
- `bento_documents` stores owner, personal/company visibility, version, archive state, normalized JSON.
- Max document JSON size: 25 MiB.
- Personal documents are owner-only. Company publication grants admitted users read access; editing,
  metadata and archive management remain owner-only. Publication requires explicit acknowledgment
  and an audit record, and company ownership cannot revert to personal under the
  [App Platform Contract](../../domains/app-platform/README.md).
- Save uses version compare to avoid overwriting concurrent edits.
- Delete flow: archive first, permanent delete second.
- Iframe bridge validates exact origin and `window` sender. No Hub auth token enters iframe.
- Import parses only `#bento-doc` JSON; it never executes imported HTML.
- Writable sessions export through the official runtime `serialize()`. Read-only sessions export the
  official presentation-only copy used by their viewer; the stored source JSON remains unchanged.
- Bridge protocol v2 carries explicit `readOnly` derived from server `can_edit` (missing access is
  read-only). Old protocol envelopes are rejected. Publish the web and rebuilt Bento image together;
  do not reuse a v1 bridge image with the v2 host.
- Bento v1.0.17 selects its official `readonly: true` player only at boot. `loadDoc()` cannot
  switch modes; no public option disables the runtime's IndexedDB recovery/version/asset stores.
  The bridge uses the official serializer's shell and replaces only inert `#bento-doc` JSON. It
  boots every content document in an opaque child iframe **without `allow-same-origin`**. The outer
  Bento frame never loads content into its editor store. The native sandbox denies persistent
  browser storage; the pinned runtime gracefully handles unavailable IndexedDB. No upstream
  function or browser storage API is patched. Remove this boot adapter when an upstream supported
  embedded lifecycle provides both mode selection and storage isolation.
- The Hub validates the outer frame's exact Bento origin and Window. The outer frame validates
  each child reply against its exact owned Window and opaque origin `null`; only token-free
  commands to that Window use `targetOrigin: '*'`. Child receivers require the exact outer Window
  and Bento origin. Arbitrary frames cannot relay writes. Read-only frames never relay mutations.
- The dedicated Bento origin sends `Clear-Site-Data: "storage"` to retire recovery/assets left by
  earlier versions. Hub storage is on a different origin and is unaffected. The opaque content frame
  cannot recreate those persistent records.
- Company-read copies remove collaboration metadata and never enter the storage-capable editor.
  Source JSON in PostgreSQL is unchanged. Blob URLs are released on replacement/exit; principal,
  document or access-mode changes remount the frame. Import consumes JSON only.
- Host save/autosave and AI edits require current edit permission. A reader receives no usable editor,
  save or AI modification action. No document data or Hub credentials enter a runtime URL.

## AI Generation

- Workloads: `bento.plan_presentation`, `bento.generate_presentation`, `bento.edit_presentation`.
- App never selects provider/model. Admin LLM Routing owns runtime/route/provider/model.
- Defaults route local. Generation/edit allow `fixed_bento_pipeline` and `codex_sdk` agent runtime.
- Create/edit requests return `202 Accepted` background work on `ai-graph` worker.
- Edit saves latest iframe state before generation; result writes next version only if start version still matches.
- Stored output must validate `bento/slides` v1 JSON, slide count, editable text/shape/chart/table elements, safe inline HTML, IDs, links, 1280x720 bounds.
- Generated `docId`/`modified` are server-owned. Drop model-created collaboration keys, external assets, executable content.
- Prompt/raw model response are not stored in operations logs or interaction ledger.
- Validation failure gets one automatic correction through same local workload, then full validation again.
- Edit input omits collaboration keys, assets, layout, comments, unknown extensions; unsupported image/SVG/media docs are rejected.

## Codex SDK Runtime

- Requires admin-approved OpenAI provider/model and external route.
- Runs in isolated temp workspace containing `document.json`, user brief, and standalone `bento_tool.py`.
- Allows document read/modify/validate/preview loop and built-in web search.
- Blocks shell network, approval requests, environment inheritance, source tree access, and user session context.
- Input/output pass AI Gateway security, masking, audit, and deletion-on-terminal-state rules.

## Local DMR/Qwen

```bash
docker desktop enable model-runner --tcp=12434
pnpm dev:qwen:pull
pnpm dev:qwen:start
pnpm dev:qwen:status
pnpm dev:qwen:smoke
```

- Base URL: `http://127.0.0.1:12434/engines/v1`
- Default profile: `docker-model-runner`
- Do not hardcode model ID in Bento code. Select model in Admin AI model settings or workload routing.

## Rollback

Record the existing Bento image ID and bridge hash before rollout; the release tag alone does not
identify a bridge revision. Build/recreate the Bento infra service separately from `pnpm app:prod:deploy`.
That app command does not deploy or roll back this service. For a protocol rollback, restore the matching
web image and Bento image together, then smoke their handshake and rendered editor/viewer. Source rollback
also restores the pinned version, revision, checksums and bridge as one set. Do not pair a v1 host with a
v2 bridge or the reverse.
