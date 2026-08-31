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
- The external HTTPS proxy connects the dedicated Bento hostname directly to `OPEN_WORK_HUB_BENTO_BIND_HOST:OPEN_WORK_HUB_BENTO_PORT`; use a reachable bind host when the proxy runs outside the host namespace.
- Do not serve Bento below the Hub origin; iframe must not access Hub storage/tokens.

## Data/Auth

- Runtime availability for app `bento` gates the hub, document API, and editor route.
- `bento_documents` stores workspace, owner, visibility, version, archive state, normalized JSON.
- Max document JSON size: 25 MiB.
- Personal docs are owner-only. Workspace docs are member-editable; owner/workspace admin manages name/visibility/archive.
- Save uses version compare to avoid overwriting concurrent edits.
- Delete flow: archive first, permanent delete second.
- Iframe bridge validates exact origin and `window` sender. No Hub auth token enters iframe.
- Import parses only `#bento-doc` JSON; it never executes imported HTML.
- Export uses official runtime `serialize()`.

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

Set `OPEN_WORK_HUB_BENTO_IMAGE_TAG` to previous image tag and recreate service. Source rollback must restore version, revision, and checksums as one set.
