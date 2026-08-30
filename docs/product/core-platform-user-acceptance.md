# Core Platform User Acceptance

These scenarios define product-wide acceptance for app-first workspace context. The owning
architecture and route rules remain in [ADR 0011](../../adr/0011-app-first-workspace-context.md)
and the [App Platform Contract](../domains/app-platform/README.md). App-specific behavior stays
in its app documentation and tests.

Indexed-source authorization is composed by [Source Access](../domains/source-access/README.md),
cross-app byte delivery by [Content Access](../domains/content-access/README.md), global notification
authorization by [Notifications](../domains/notifications/README.md), durable AI state by
[AI Execution](../domains/ai/execution.md), and recording result/publication behavior by the
[Recording App](../apps/recording/README.md). The scenarios below verify those contracts without
becoming a second implementation specification.

## Test Personas

| Persona                       | Required state                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| zero-workspace platform admin | Active company account with platform-admin role and no workspace membership; can manage company scope. |
| zero-workspace member         | Newly registered company account with no workspace membership.                                         |
| multi-workspace member        | Active member of two workspaces; the tested workspace app is enabled in both.                          |
| single-workspace member       | Active member of exactly one eligible workspace for the tested app.                                    |
| app-ineligible member         | Signed-in member whose memberships do not make the tested workspace app eligible.                      |

Use unique disposable records. Revoke membership or app availability only for disposable test
workspaces. Each browser actor uses an isolated named session. A hidden control is not sufficient
evidence: direct routes and the resulting API calls must also fail closed.

## Live Browser Execution Contract

The browser gate is a rendered, public-domain test against the running development stack. It is
not a component test and it is not satisfied by opening `localhost` when a public hostname was
requested.

- Start the documented development Web, API, Worker, PostgreSQL, Redis, and object-storage
  dependencies in one terminal with `./dev.sh --with-worker --restart`. In another terminal, set
  `OPEN_WORK_HUB_UAT_BASE_URL` to the public HTTPS origin and run `pnpm uat:preflight`. Do not open
  a test browser unless this hard gate passes all service-status, local/public health, readiness,
  and login-HTML-shell checks. The first `agent-browser` snapshot is the rendered-login gate. See
  the [repository README](../../README.md) for runtime ownership.
- Record the public `OPEN_WORK_HUB_UAT_BASE_URL` origin with the Git commit and UTC start time. The
  variable is an ephemeral UAT command input, not a persisted runtime setting or product default.
- Use the rendered `/login` UI to create at least two disposable member accounts. Provision the
  platform-admin persona before the measured journey because a non-admin cannot elevate itself.
  Fixture provisioning is setup, not evidence for an admin workflow.
- Give every actor an isolated, named `agent-browser` session. Do not copy cookies, local storage,
  or session state between actors.
- Perform measured reads and mutations through visible browser controls. Do not replace them with
  direct API calls, database writes, `page.route`, service-worker interception, request stubs, or
  synthetic responses. Browser network inspection may confirm the real response status. Resolve
  local upload fixtures to an absolute path before passing them to `agent-browser upload`; a
  relative path is resolved by the browser runner, not by the application workspace.
- Use the development PostgreSQL, Redis, object storage, and workers as configured. Test records
  may remain in the shared development data set, but restore any app-availability override or
  elevated role that could affect other users.
- Keep passwords only in an ephemeral shell variable or secret store. Evidence may contain the
  run ID, disposable login IDs, final URL, visible state, and response status, but never cookies,
  authorization headers, content grants, passwords, raw HAR files, or environment values.
- After each state-changing step, verify both the success surface and the corresponding denial or
  persistence boundary. A toast alone is not acceptance evidence.

Use a UTC run ID such as `YYYYMMDDHHMMSS` in every disposable name:

| Record         | Naming pattern               |
| -------------- | ---------------------------- |
| primary member | `uat-member-a-<run-id>`      |
| second member  | `uat-member-b-<run-id>`      |
| workspace      | `UAT Workspace <run-id>`     |
| app records    | `UAT <record-kind> <run-id>` |

## Repeatable Live User Journey

Run the following sequence without clearing the shared development data. `A` is the
platform-admin actor, `B` is a normal member, and `C` is a second normal member used to prove
cross-user behavior. All routes are relative to `OPEN_WORK_HUB_UAT_BASE_URL`.

| ID      | Actor and action                                                                                                                                                                                                                                                                                                                                     | Expected browser evidence                                                                                                                                                                                                                                                                                                                                              |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LIVE-00 | Run `./dev.sh --with-worker --restart`, then `OPEN_WORK_HUB_UAT_BASE_URL=https://… pnpm uat:preflight` in another terminal before opening `agent-browser`.                                                                                                                                                                                           | Web, API, and Worker are running; local and public health/readiness are `ok`; the public origin renders the login shell rather than a service-unavailable page.                                                                                                                                                                                                        |
| LIVE-01 | B and C choose **Sign up** on `/login`, enter unique identities, and submit through the rendered form. From `/`, each also opens a known workspace-app entry URL directly.                                                                                                                                                                           | Each real signup lands on `/` with zero workspace memberships. Company and personal apps remain usable, workspace-app cards are absent, and the direct workspace-app entry fails closed. Signup copy does not imply automatic membership.                                                                                                                              |
| LIVE-02 | C signs out, verifies `/login`, signs in again with the registered credentials, and uses Back/Forward.                                                                                                                                                                                                                                               | Protected content disappears synchronously even if server-side revocation later fails. Sign-in restores only C's company/personal projection; no prior principal or workspace data flashes.                                                                                                                                                                            |
| LIVE-03 | With no workspace membership, A signs in as a platform admin and opens `/admin` and `/admin/workspaces`; B opens the same routes.                                                                                                                                                                                                                    | A can administer company scope without belonging to a workspace. B is denied both routes and APIs; hiding Settings is not the only enforcement.                                                                                                                                                                                                                        |
| LIVE-04 | Keep B's session open on `/`. A creates workspace one, adds B as `member`, and opens its member list. Do not reload B.                                                                                                                                                                                                                               | A's membership mutation persists. B's open session refreshes automatically, exposes eligible workspace apps, and never requires logout or reload.                                                                                                                                                                                                                      |
| LIVE-05 | A promotes B to workspace `admin`; B opens `/admin/workspaces/:workspaceSlug/settings` and `/admin/workspaces`. A then demotes B while B remains on the settings route. Do not reload B before checking denial.                                                                                                                                      | Workspace administration follows the canonical workspace-settings route; platform administration remains denied. Promotion and demotion reach B's open session, and demotion replaces protected content with access denial without stale cached data.                                                                                                                  |
| LIVE-06 | A creates workspace two and explicitly adds B so the chosen workspace app is eligible in both. B opens the app entry, chooses workspace one, then switches to workspace two from that app's submenu.                                                                                                                                                 | No global App Bar workspace selector appears. The chooser is app-local, and route, selector, and data move together at `/apps/:appId/workspaces/:workspaceSlug/...`.                                                                                                                                                                                                   |
| LIVE-07 | In PMS, B creates a space, list, and assigned task. B selects workspace one in PMS, selects workspace two in Docs, then reopens both apps.                                                                                                                                                                                                           | Records persist, and each workspace app retains only its own eligible preference. Neither app inherits the other's workspace.                                                                                                                                                                                                                                          |
| LIVE-08 | In Docs, B creates a workspace-visible document, enters body content, reloads, and reopens it.                                                                                                                                                                                                                                                       | Title, visibility, body, and canonical workspace route persist without content from another workspace.                                                                                                                                                                                                                                                                 |
| LIVE-09 | In Files, B uploads a small allowed file, downloads it through visible controls, and compares its checksum with the source.                                                                                                                                                                                                                          | Real object storage is exercised and bytes match. No content grant appears in a URL, console output, or saved evidence.                                                                                                                                                                                                                                                |
| LIVE-10 | In Community, B creates a company post and keeps its detail open. A opens it and comments. Before reloading or changing focus in B's browser, verify the open detail, then B opens notifications and marks the notification read.                                                                                                                    | Community has no workspace selector. B's open detail updates its comment count and content without reload, and B receives exactly one source-owned notification with the canonical post link; unread state clears immediately and remains clear after reload.                                                                                                          |
| LIVE-11 | In Planner, B creates an event, updates its title/time, and deletes it. Verify the calendar and Today Planner dock badge after each mutation before reload, then reload after create/update and after delete.                                                                                                                                        | Planner has no workspace selector. Create and update appear immediately and persist; the dock count refreshes without a page reload; delete disappears immediately, clears the corresponding dock count, and stays deleted. Deterministic API tests own DST gap/fold boundary coverage.                                                                                |
| LIVE-12 | B starts a DM with A and sends a unique message. A opens the unread conversation and replies while B remains on the thread.                                                                                                                                                                                                                          | A gets one unread indication; B receives the reply in the existing conversation without reload; neither actor sees another conversation.                                                                                                                                                                                                                               |
| LIVE-13 | While B views Files, A selects that workspace on the workspace-app override screen, disables Files, checks B before reload, opens the disabled direct URL, then restores inheritance.                                                                                                                                                                | A's selected workspace is encoded in the override-screen URL and survives every access-projection refresh. B's open session removes the revoked workspace eligibility and protected cache without reload. The direct route denies; unrelated workspace apps and all allowed company/personal apps remain usable. Restoration re-enables only the intended eligibility. |
| LIVE-14 | For each membership-removal surface (workspace preview, single-member drawer, bulk drawer, and Admin People), A starts removal and cancels once. Then confirm using a separate disposable member/workspace pair, or re-add B and verify restored access before testing the next surface. Keep the removed actor's session open and do not reload it. | Cancel performs no mutation and returns keyboard focus to the control that opened confirmation. Confirm text warns about immediate access loss. On confirm, the affected actor is removed in real time, every tested workspace route/API fails closed, and allowed company/personal apps stay usable.                                                                  |
| LIVE-15 | While B remains on a workspace Files route, A archives that workspace, verifies B before reload, then reactivates it.                                                                                                                                                                                                                                | Archiving removes B's access and protected data immediately without deleting membership or stored files. Reactivation restores the same route and data without reload or re-adding B.                                                                                                                                                                                  |
| LIVE-16 | At `390 x 844`, repeat launcher and app switching, operate the mobile app switcher, keyboard-navigate launcher/denial/confirmation states, inspect accessible names/headings/focus and badge contrast, then inspect browser errors for all actors.                                                                                                   | Mobile navigation remains operable, app categories/scopes are explicit, denial uses one page heading, dialogs restore or move focus correctly, badges remain legible, and no critical/serious automated accessibility violation or uncaught browser error is present.                                                                                                  |
| LIVE-17 | After one unmeasured cold login, perform ten warm rendered-UI login journeys against the public origin and measure submit-to-usable-launcher time.                                                                                                                                                                                                   | At least 9 of 10 warm runs reach an interactive launcher within 3 seconds and none exceeds 5 seconds. Report cold-start timing separately; do not average it into the warm gate.                                                                                                                                                                                       |

Record each run without storing sensitive browser artifacts:

| Field           | Required value                                                                               |
| --------------- | -------------------------------------------------------------------------------------------- |
| run identity    | UTC run ID, Git commit, public `OPEN_WORK_HUB_UAT_BASE_URL`, start/end time                  |
| runtime         | Web/API/Worker health and the real dependencies exercised                                    |
| actors          | disposable login IDs and assigned roles; no passwords or session material                    |
| scenario result | `PASS`, `FAIL`, or `BLOCKED` for every `LIVE-*` ID with final URL and visible-state evidence |
| findings        | stable finding ID, severity, reproduction step, expected state, actual state                 |
| restoration     | app overrides and elevated roles restored; intentionally retained disposable data listed     |

## Shell And App Context

| ID     | Action                                                                               | Expected                                                                                                                                                                                |
| ------ | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-01 | Sign in and open `/`.                                                                | The launcher is neutral: it does not select, display, or persist a global current workspace.                                                                                            |
| CAP-02 | Inspect the launcher as each persona.                                                | A platform app appears when its company/role gates pass. A workspace app appears only when at least one eligible workspace exists. Display categories do not appear as executable apps. |
| CAP-03 | Open a platform/company app after using a workspace app.                             | The app opens on its global route, shows no workspace selector, and does not inherit the prior app's workspace.                                                                         |
| CAP-04 | Open a workspace app with one eligible workspace.                                    | The app selects that workspace and lands on `/apps/:appId/workspaces/:workspaceSlug/...`.                                                                                               |
| CAP-05 | Open a workspace app with multiple eligible workspaces and no preference.            | An app-local chooser appears before workspace data is loaded.                                                                                                                           |
| CAP-06 | Choose a workspace, leave the app, and reopen it.                                    | The app-local preference is reused only while that workspace remains eligible.                                                                                                          |
| CAP-07 | Switch workspace from the current app submenu.                                       | The canonical route and app data change together; the global App Bar remains workspace-neutral.                                                                                         |
| CAP-08 | Select different workspaces in two workspace apps.                                   | Each app preserves its own preference; changing one does not change the other.                                                                                                          |
| CAP-09 | Remove the saved workspace membership or disable the app there, then reopen the app. | The stale preference is ignored. One remaining eligible workspace auto-selects, multiple show the chooser, and zero eligible workspaces deny entry.                                     |
| CAP-10 | Change user identity or sign out while workspace/app bootstrap data is visible.      | Prior-user app and workspace data disappears synchronously and never flashes for the next principal.                                                                                    |
| CAP-11 | Open a canonical global/shared route such as a share link.                           | The route does not request workspace bootstrap and remains independent of app workspace preference.                                                                                     |
| CAP-12 | Open a non-canonical or workspace-less route for a workspace-only surface.           | No legacy redirect or fallback parsing is used; entry resolution or access denial follows the canonical route contract.                                                                 |

## Runtime Availability And Authorization

| ID     | Action                                                                                       | Expected                                                                                                                                                                                                     |
| ------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CAP-20 | Disable a platform app at company level while a user is viewing it, then navigate or reload. | The launcher removes it and server requests fail closed without relying on UI hiding.                                                                                                                        |
| CAP-21 | Disable a workspace app at company level.                                                    | It disappears for every workspace and direct API/route use is denied.                                                                                                                                        |
| CAP-22 | Disable a workspace app only in workspace A while leaving workspace B enabled.               | A is removed from that app's chooser; B remains usable; unrelated apps and company apps are unchanged.                                                                                                       |
| CAP-23 | Remove a user's workspace membership during an active session.                               | The open browser refreshes its access projection without reload, discards protected caches, and denies subsequent reads, writes, search, AI execution, and queued work according to their terminal contract. |
| CAP-24 | Open two browser sessions as different users and switch workspace/app controls in one.       | Neither session exposes the other user's eligible workspaces, preferences, data, or notifications.                                                                                                           |
| CAP-25 | Cause access, app, or workspace bootstrap to fail, then retry.                               | Gated content becomes hidden and inert; an alert explains the error, its focused retry control recovers in canonical user → apps → workspace order, and stale authorized content never renders.              |

## Source-Owned Content And Notifications

| ID     | Action                                                                                                                     | Expected                                                                                                                                                                                                                                                         |
| ------ | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-30 | Download or preview a Files, PMS attachment, Meeting attachment, or linked media item.                                     | The UI receives a short-lived `/api/v1/content#grant=...` capability, removes the fragment, and sends it in `X-Open-Work-Hub-Content-Grant` with the exact issuing session. Request URLs, referrers, service payloads, and AI payloads do not contain the grant. |
| CAP-31 | Reuse a content grant from another browser session/user, after expiry, or after source access/app availability is revoked. | Every attempt returns the same non-enumerating denial; storage is never read.                                                                                                                                                                                    |
| CAP-32 | Request a missing and an unauthorized content object.                                                                      | Responses do not reveal which object exists. Unsafe MIME, magic bytes, URL scheme, or owner/source combinations fail closed.                                                                                                                                     |
| CAP-33 | Comment on another user's Community post.                                                                                  | Exactly one source-owned global notification appears, links to the canonical post route, and no bot DM duplicate is created.                                                                                                                                     |
| CAP-34 | Read one notification and then mark all read.                                                                              | Item state and unread count update consistently in the panel and after reload.                                                                                                                                                                                   |
| CAP-35 | Lose source ACL, membership, or originating app availability after a notification is created.                              | The notification is no longer listed, counted, or readable by direct notification ID.                                                                                                                                                                            |

## Search, AI, And Background Work

| ID     | Action                                                                                              | Expected                                                                                                                      |
| ------ | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| CAP-40 | Search a term that has interleaved company and workspace results.                                   | Authorized results retain backend rank order; inaccessible source/app results are removed without reordering the survivors.   |
| CAP-41 | Disable an owning app or revoke source access after results are indexed, then search/open a result. | Keyword search, retrieval, RAG, and direct result navigation all recheck current authorization and hide the stale result.     |
| CAP-42 | Discover and invoke an AI tool for a disabled or inaccessible app/source.                           | The tool is absent or denied before provider execution; AI output never contains content-grant URLs.                          |
| CAP-43 | Disable an app or revoke membership after queued work is claimed.                                   | The worker rechecks before provider/storage mutation and pauses, cancels, or fails using the job's documented terminal state. |

## Recording Publication

| ID     | Action                                                               | Expected                                                                                                                                             |
| ------ | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-50 | Complete recording transcription and summarization.                  | The durable result appears on the recording detail; no Docs document is created automatically. Collection/list responses omit the large result body. |
| CAP-51 | Publish the completed result to Docs.                                | Publication is explicit, creates one source-linked document, and the detail shows the publication. Repeating the action is idempotent.               |
| CAP-52 | Publish before a result exists or after losing workspace/app access. | The operation fails closed and creates neither a document nor a publication row.                                                                     |
| CAP-53 | Supersede the transcript while an older summary pipeline is running. | Version fencing rejects the stale result and never publishes it.                                                                                     |

## Responsive And Accessibility Checks

| ID     | Action                                                                                                                                 | Expected                                                                                                                                    |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-60 | Repeat CAP-03 through CAP-07 at a mobile viewport.                                                                                     | The hamburger opens the global launcher; workspace choice stays inside the current workspace app menu.                                      |
| CAP-61 | Navigate launcher, chooser, submenu, notification panel, denial state, and publish action by keyboard.                                 | Focus order, names, selected/expanded states, and focus return make every action operable without pointer input.                            |
| CAP-62 | Run WCAG A/AA automated checks on launcher, chooser, a company app, a workspace app, confirmation dialogs, and an access-denied state. | No critical/serious violations are introduced; navigation labels, heading hierarchy, focus, and scope badges meet their explicit contracts. |

## Minimum Browser Gate

Before a workspace-context change is accepted, run CAP-01 through CAP-12, CAP-20 through CAP-25,
CAP-33 through CAP-35, CAP-50 through CAP-52, CAP-60 through CAP-62, and LIVE-00 through LIVE-16
against the rendered public-domain development application. Exercise at least two isolated users,
two workspace apps, one company app, and one personal app with the real development dependencies.
API/unit coverage owns cryptographic grant expiry, search rank identity, queue fencing, and other
deterministic seams that cannot be reliably forced through the UI.
