# Content Access

Content Access is the cross-app boundary for authenticated download and preview bytes. Source
apps authorize capability issuance and retain final authority over the object; the shared endpoint
only validates the capability, binds it to the caller, and dispatches to an explicit source adapter.

## Contract

- Source APIs return a short-lived `/api/v1/content#grant=...` URL only after normal app and source
  authorization succeeds.
- The browser accepts exactly that path and one `grant` fragment value. It sends the current access
  token plus `X-Open-Work-Hub-Content-Grant`; the fragment never enters the request target or referrer.
- A grant binds the exact user and session, owning app, personal/company execution context,
  source identity, object identity and version, disposition, and expiry. TTL cannot exceed 15 minutes.
- `/api/v1/content` authenticates the current session, requires an exact issuer match, then rechecks
  current app availability, source ACL, resource version, and object ownership immediately before
  storage is read.
- Missing, malformed, expired, wrong-issuer, authorization-revoked, unauthorized, and nonexistent
  capabilities return the same non-enumerating `403 content.grant_invalid` response. A denied
  request never opens storage. A valid grant is not one-time: the exact issuing session may reuse
  it until expiry, with current app and source authorization rechecked on every request.
- Responses are `private, no-store` with `Referrer-Policy: no-referrer`. Grant values must not appear
  in query strings, logs, analytics, service payloads, persisted state, or AI/LLM input.
- Resource kinds are explicit adapters. Do not add a generic bucket/key proxy or trust client-supplied
  MIME type, source ownership, route ownership, or execution context.

## Registered Resource Kinds

| Resource kind        | Source owner                                                  |
| -------------------- | ------------------------------------------------------------- |
| `files.file`         | Files file ACL and content metadata                           |
| `pms.attachment`     | PMS task attachment and task ACL                              |
| `meeting.attachment` | Meeting attachment and meeting ACL                            |
| `media.file`         | Media owner/source resolver                                   |
| `dm.attachment`      | DM participation, message history and unsent-upload ownership |

New kinds require a grant producer, an explicit dispatcher branch, source authorization before issue
and before stream, safe MIME/disposition handling, and cross-user/session/revocation failure tests.
App availability follows the [App Platform Contract](../app-platform/README.md). Indexed source
adapters follow [Source Access](../source-access/README.md); every content kind still invokes its
own source's direct authorization before streaming.

Embedded PMS task media uses the task source's current read ACL: an active space user/group role,
a supported task grant, or the platform administrator's company read authority. App admission and
source lifecycle checks apply at issuance and every stream. Linking media is a write and requires
an explicit PMS editor role; an administrator's read authority or a meeting read grant is insufficient.
All supported media-link writes use the owning-app gate. Personal content stays owner/explicit-share
restricted even for administrators. Company publication is an explicit audited ownership transition;
removing a project link or public audience does not restore personal ownership.

DM message/upload/realtime projections carry attachment metadata and `is_image`, never download
capabilities. An authenticated caller obtains a session-bound grant from
`/api/v1/dm/attachments/{id}/download` or `/preview`. DM is a core personal communication capability,
with no independent app admission policy. Issuance and streaming require a current active, unblocked
account with a completed password change and current conversation participation. Unsent uploads are visible only to their uploader;
sent attachments follow the message's join-time history boundary. Leaving and rejoining does not
restore access to pre-join messages. The old unauthenticated DM signed-URL endpoint is removed.

All grants use the dedicated typed `OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY`; object-storage
credentials are not signing keys. Preview/production require a cryptographically random secret of at
least 32 characters; API startup and production configuration checks reject short keys and development
or placeholder prefixes. Length validation cannot prove entropy; provision the key through the deployment
secret manager or a cryptographically secure generator. Development
has a local-only default. The former DM signing setting is retired without an alias. Key rotation
invalidates outstanding grants; users obtain fresh grants through their authenticated app APIs.
Production rollout must provision the new key before startup. Updating a host environment file
does not replace the environment of already-created containers. Pair the new setting with the new
application revision when recreating containers; an older revision still requires its matching
environment backup. Environment provisioning does not deploy code or migrate the database.

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_content_grants.py tests/test_file_content_access.py tests/test_pms_attachments.py tests/test_media_resource_access.py -q)
pnpm exec vitest run --root apps/web src/platform/browser/browser-download.spec.ts src/platform/media/media-url-resolution-session.spec.ts
pnpm check:api-contract
```
