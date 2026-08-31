# Content Access

Content Access is the cross-app boundary for authenticated download and preview bytes. Source
apps authorize capability issuance and retain final authority over the object; the shared endpoint
only validates the capability, binds it to the caller, and dispatches to an explicit source adapter.

## Contract

- Source APIs return a short-lived `/api/v1/content#grant=...` URL only after normal app and source
  authorization succeeds.
- The browser accepts exactly that path and one `grant` fragment value. It sends the current access
  token plus `X-Open-Work-Hub-Content-Grant`; the fragment never enters the request target or referrer.
- A grant binds the exact user and session, owning app, execution context, workspace when applicable,
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

| Resource kind | Source owner |
| --- | --- |
| `files.file` | Files file ACL and content metadata |
| `pms.attachment` | PMS task attachment and task ACL |
| `meeting.attachment` | Meeting attachment and meeting ACL |
| `media.file` | Media owner/source resolver |

New kinds require a grant producer, an explicit dispatcher branch, source authorization before issue
and before stream, safe MIME/disposition handling, and cross-user/session/revocation failure tests.
App availability follows the [App Platform Contract](../app-platform/README.md). Indexed source
adapters follow [Source Access](../source-access/README.md); every content kind still invokes its
own source's direct authorization before streaming.

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_content_grants.py tests/test_file_content_access.py tests/test_pms_attachments.py tests/test_media_resource_access.py -q)
pnpm exec vitest run --root apps/web src/platform/browser/browser-download.spec.ts src/platform/media/media-url-resolution-session.spec.ts
pnpm check:api-contract
```
