# Core Platform User Acceptance

These scenarios define product-wide acceptance for app-first workspace context. The owning
architecture and route rules remain in [ADR 0011](../../adr/0011-app-first-workspace-context.md)
and the [App Platform Contract](../domains/app-platform/README.md). App-specific behavior stays
in its app documentation and tests.

## Test Personas

| Persona | Required state |
| --- | --- |
| platform admin | Company controls and workspace defaults/overrides can be changed. |
| multi-workspace member | Active member of two workspaces; the tested workspace app is enabled in both. |
| single-workspace member | Active member of exactly one eligible workspace for the tested app. |
| ineligible member | Signed-in active user with no eligible workspace for the tested app. |

Use unique disposable records. Revoke membership or app availability only for disposable test
workspaces. Each browser actor uses an isolated named session. A hidden control is not sufficient
evidence: direct routes and the resulting API calls must also fail closed.

## Shell And App Context

| ID | Action | Expected |
| --- | --- | --- |
| CAP-01 | Sign in and open `/`. | The launcher is neutral: it does not select, display, or persist a global current workspace. |
| CAP-02 | Inspect the launcher as each persona. | A platform app appears when its company/role gates pass. A workspace app appears only when at least one eligible workspace exists. Display categories do not appear as executable apps. |
| CAP-03 | Open a platform/company app after using a workspace app. | The app opens on its global route, shows no workspace selector, and does not inherit the prior app's workspace. |
| CAP-04 | Open a workspace app with one eligible workspace. | The app selects that workspace and lands on `/apps/:appId/workspaces/:workspaceSlug/...`. |
| CAP-05 | Open a workspace app with multiple eligible workspaces and no preference. | An app-local chooser appears before workspace data is loaded. |
| CAP-06 | Choose a workspace, leave the app, and reopen it. | The app-local preference is reused only while that workspace remains eligible. |
| CAP-07 | Switch workspace from the current app submenu. | The canonical route and app data change together; the global App Bar remains workspace-neutral. |
| CAP-08 | Select different workspaces in two workspace apps. | Each app preserves its own preference; changing one does not change the other. |
| CAP-09 | Remove the saved workspace membership or disable the app there, then reopen the app. | The stale preference is ignored. One remaining eligible workspace auto-selects; multiple show the chooser; none deny entry. |
| CAP-10 | Change user identity or sign out while workspace/app bootstrap data is visible. | Prior-user app and workspace data disappears synchronously and never flashes for the next principal. |
| CAP-11 | Open a canonical global/shared route such as a share link. | The route does not request workspace bootstrap and remains independent of app workspace preference. |
| CAP-12 | Open a non-canonical or workspace-less route for a workspace-only surface. | No legacy redirect or fallback parsing is used; entry resolution or access denial follows the canonical route contract. |

## Runtime Availability And Authorization

| ID | Action | Expected |
| --- | --- | --- |
| CAP-20 | Disable a platform app at company level while a user is viewing it, then navigate or reload. | The launcher removes it and server requests fail closed without relying on UI hiding. |
| CAP-21 | Disable a workspace app at company level. | It disappears for every workspace and direct API/route use is denied. |
| CAP-22 | Disable a workspace app only in workspace A while leaving workspace B enabled. | A is removed from that app's chooser; B remains usable; unrelated apps and company apps are unchanged. |
| CAP-23 | Remove a user's workspace membership during an active session. | Subsequent reads, writes, search, AI execution, and queued work for that workspace are denied or cancelled according to their terminal contract. |
| CAP-24 | Open two browser sessions as different users and switch workspace/app controls in one. | Neither session exposes the other user's eligible workspaces, preferences, data, or notifications. |
| CAP-25 | Cause app bootstrap or workspace bootstrap to fail. | Core shell routes remain usable; gated routes show an explicit error and never render stale authorized content. |

## Source-Owned Content And Notifications

| ID | Action | Expected |
| --- | --- | --- |
| CAP-30 | Download or preview a Files, PMS attachment, Meeting attachment, or linked media item. | The UI receives a short-lived `/api/v1/content#grant=...` capability, removes the fragment, and sends it in `X-Open-Work-Hub-Content-Grant` with the exact issuing session. Request URLs, referrers, service payloads, and AI payloads do not contain the grant. |
| CAP-31 | Reuse a content grant from another browser session/user, after expiry, or after source access/app availability is revoked. | Every attempt returns the same non-enumerating denial; storage is never read. |
| CAP-32 | Request a missing and an unauthorized content object. | Responses do not reveal which object exists. Unsafe MIME, magic bytes, URL scheme, or owner/source combinations fail closed. |
| CAP-33 | Comment on another user's Community post. | Exactly one source-owned global notification appears, links to the canonical post route, and no bot DM duplicate is created. |
| CAP-34 | Read one notification and then mark all read. | Item state and unread count update consistently in the panel and after reload. |
| CAP-35 | Lose source ACL, membership, or originating app availability after a notification is created. | The notification is no longer listed, counted, or readable by direct notification ID. |

## Search, AI, And Background Work

| ID | Action | Expected |
| --- | --- | --- |
| CAP-40 | Search a term that has interleaved company and workspace results. | Authorized results retain backend rank order; inaccessible source/app results are removed without reordering the survivors. |
| CAP-41 | Disable an owning app or revoke source access after results are indexed, then search/open a result. | Keyword search, retrieval, RAG, and direct result navigation all recheck current authorization and hide the stale result. |
| CAP-42 | Discover and invoke an AI tool for a disabled or inaccessible app/source. | The tool is absent or denied before provider execution; AI output never contains content-grant URLs. |
| CAP-43 | Disable an app or revoke membership after queued work is claimed. | The worker rechecks before provider/storage mutation and pauses, cancels, or fails using the job's documented terminal state. |

## Recording Publication

| ID | Action | Expected |
| --- | --- | --- |
| CAP-50 | Complete recording transcription and summarization. | The durable result appears on the recording detail; no Docs document is created automatically. Collection/list responses omit the large result body. |
| CAP-51 | Publish the completed result to Docs. | Publication is explicit, creates one source-linked document, and the detail shows the publication. Repeating the action is idempotent. |
| CAP-52 | Publish before a result exists or after losing workspace/app access. | The operation fails closed and creates neither a document nor a publication row. |
| CAP-53 | Supersede the transcript while an older summary pipeline is running. | Version fencing rejects the stale result and never publishes it. |

## Responsive And Accessibility Checks

| ID | Action | Expected |
| --- | --- | --- |
| CAP-60 | Repeat CAP-03 through CAP-07 at a mobile viewport. | The hamburger opens the global launcher; workspace choice stays inside the current workspace app menu. |
| CAP-61 | Navigate launcher, chooser, submenu, notification panel, denial state, and publish action by keyboard. | Focus order, names, selected/expanded states, and focus return make every action operable without pointer input. |
| CAP-62 | Run WCAG A/AA automated checks on launcher, chooser, a company app, a workspace app, and an access-denied state. | No critical/serious violations are introduced by the shell or workspace-context controls. |

## Minimum Browser Gate

Before a workspace-context change is accepted, run CAP-01 through CAP-12, CAP-20 through CAP-25,
CAP-33 through CAP-35, CAP-50 through CAP-52, and CAP-60 through CAP-62 against the local rendered
application. Exercise at least two isolated users and two workspace apps. API/unit coverage owns
cryptographic grant expiry, search rank identity, queue fencing, and other deterministic seams that
cannot be reliably forced through the UI.
