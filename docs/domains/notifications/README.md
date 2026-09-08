# Notifications

The global notification panel is a read projection of source-owned events. A notification row records
where an event came from; it never grants access to the source and is not a substitute for direct
messages.

## Contract

- Global APIs are `/api/v1/notifications`, `/unread-count`, `/{notification_id}/read`, and
  `/read-all`. They require the current user and source-specific company app admission.
- Every row belongs to one recipient and carries `origin_app_id`,
  `source_type`, `source_id`, and a generated canonical `action_url` when an
  action exists.
- Listing, total, unread count, single-read, and read-all recheck current owning-app availability and
  source ACL. Revoked, deleted, disabled, or inaccessible sources are omitted; direct access returns
  the same not-found response as a missing notification.
- Pagination and unread counts are computed after visibility filtering. Read-all changes only rows
  currently visible to the user.
- Realtime `notification.*` events use the shared notification response contract and include the
  post-operation unread count. Clients discard malformed or unknown payloads.
- Product notifications do not create bot conversations or duplicate notification delivery through
  DM. DM messages and read state remain owned by the DM domain.
- Producers use generated app routes and persist source identity, not display-only text as an
  authorization key.

## Registered Sources

| Origin app  | Source type      | Context | Final authorization                         |
| ----------- | ---------------- | ------- | ------------------------------------------- |
| `pms`       | `pms_task`       | company | PMS task source ACL                         |
| `community` | `community_post` | company | active channel, secret/admin content policy |

Adding a source requires producer tests, a batched visibility branch or source adapter, app-disable
and source-revocation tests, canonical action-route coverage, and list/count/read parity. Runtime app
availability is owned by the [App Platform Contract](../app-platform/README.md).

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_notifications.py tests/test_notifications_read_service.py tests/test_notification_visibility.py tests/test_community.py -q)
pnpm --dir packages/contracts exec vitest run src/notifications.spec.ts
```
