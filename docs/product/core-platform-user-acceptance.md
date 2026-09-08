# Core Platform User Acceptance

These scenarios verify [ADR 0012](../../adr/0012-company-app-access-without-workspaces.md).
Company app admission, directory groups, and app-owned resources replace product workspaces.
Policy owners remain [App Platform](../domains/app-platform/README.md),
[Organization](../domains/organization/README.md), [Source Access](../domains/source-access/README.md),
[Content Access](../domains/content-access/README.md), [Notifications](../domains/notifications/README.md),
[AI Execution](../domains/ai/execution.md), and [Recording](../apps/recording/README.md).

## Personas And Evidence

Use an active platform administrator A and two ordinary company users B and C in isolated named
browser sessions. Include an app-ineligible user and a temporary-password user. Create disposable
manual groups, organization units, PMS spaces, and app records with a UTC run ID. App permission
changes must be restored after the journey; existing unrelated records must remain intact.

A hidden button is insufficient evidence. Verify the corresponding server denial, persistence,
and current-access refresh without a manual page reload. Keep credentials, cookies, authorization
headers, content grants, raw HAR files, and environment values out of reports.

## Live Browser Execution Contract

- Start the documented Web/API/Worker and real development dependencies with
  `./dev.sh --with-worker --restart`. Run `OPEN_WORK_HUB_UAT_BASE_URL=https://… pnpm uat:preflight`
  before the measured public-domain browser gate. Record the origin, Git commit, UTC run ID,
  service readiness, and the first rendered login snapshot. Localhost smoke does not replace the
  public-domain gate.
- Use the rendered login/signup and administration controls. Fixture provisioning may establish
  the initial administrator; it does not prove an administration workflow.
- Never share session state across actors. Measured interactions use visible browser controls,
  real APIs, PostgreSQL, object storage, and workers. Direct API/SQL setup, request interception,
  or synthetic responses cannot substitute for measured UI actions.
- Upload only disposable local fixtures through absolute paths. Confirm both the successful action
  and its denial or persistence boundary. Keep passwords only in ephemeral variables/secret storage.
- Report each scenario as PASS, FAIL, or BLOCKED with final URL, visible result, response status,
  and restoration status. Unavailable services or unfinished scenarios are not passes.

## Repeatable Live Journey

| ID      | Rendered action                                                                                                            | Required evidence                                                                                                                                                                                                                                                         |
| ------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LIVE-00 | Start services and run public-origin preflight before opening the browser.                                                 | Web/API/Worker and dependencies ready; public origin renders the application login shell.                                                                                                                                                                                 |
| LIVE-01 | B and C register through signup and open the launcher and a denied direct app URL.                                         | Company policies alone determine available apps; no workspace enrollment, chooser, or default container appears. Denied app data is never requested successfully.                                                                                                         |
| LIVE-02 | C signs out, signs in, and uses Back/Forward.                                                                              | Previous account data disappears synchronously, including drafts, app bootstrap, notifications, and personal caches.                                                                                                                                                      |
| LIVE-03 | A opens administration and Groups; B tries the same routes.                                                                | A can manage company accounts/groups; B receives server denial. PMS role changes cannot grant platform administration.                                                                                                                                                    |
| LIVE-04 | A creates a manual group containing B and selects it as the audience of a disposable test app policy.                      | B gains app entry without reload; C remains denied. Empty selected audiences deny both. Restore the prior app policy afterward.                                                                                                                                           |
| LIVE-05 | While B uses that app, A removes B from the grant group, then restores membership.                                         | App entry, open protected data, direct API calls, and background requests reflect current membership without stale content.                                                                                                                                               |
| LIVE-06 | A assigns B to an organization and to a manual group, then changes B's organization and head assignments.                  | Only the exact current organization group changes. Manual membership persists; head/ancestor status adds no automatic access.                                                                                                                                             |
| LIVE-07 | B creates two PMS spaces, a list and task, and assigns a company group a space role.                                       | Spaces are PMS-local. Owner remains an explicit user; group roles cannot become owner. Read-only admins/viewers cannot write.                                                                                                                                             |
| LIVE-08 | B authors a private Docs document, saves/reloads it, shares it with a group, then explicitly publishes it to company work. | Private ownership survives group sharing. A cannot read before publication. Publication shows administrator-read/irreversibility notice and persists; A can read but cannot edit afterward. Removing public audience or project link does not restore personal ownership. |
| LIVE-09 | B uploads and downloads a small allowed Files fixture.                                                                     | Real bytes match the source checksum. Content grants remain absent from request URLs and evidence. Cross-user/expired/revoked grants are denied by deterministic API coverage.                                                                                            |
| LIVE-10 | B creates a Community post; A comments while B keeps it open, then B reads its notification.                               | One realtime update and one notification, no bot DM duplicate; focus/visibility refresh does not duplicate requests; read state persists.                                                                                                                                 |
| LIVE-11 | B creates, updates, and deletes a Planner event; inspect calendar and dock after each action and reload.                   | Each mutation persists and updates the dock immediately. A cannot read B's personal event by administrator role.                                                                                                                                                          |
| LIVE-12 | B and C exchange DM messages while A is not a participant.                                                                 | Realtime replies and unread state work; A and other nonparticipants cannot read the thread.                                                                                                                                                                               |
| LIVE-13 | A disables the tested app's company master while B is viewing it, then restores it.                                        | The app is denied for everyone, including A. B's open state clears; unrelated apps remain available; restoration follows the saved audience.                                                                                                                              |
| LIVE-14 | A cancels then confirms disposable group grant removal/deactivation.                                                       | Cancel is inert and restores focus. Confirmation explains immediate access loss; records remain while revoked grants stop authorizing reads, writes, search, and notifications.                                                                                           |
| LIVE-15 | A suspends and reactivates a disposable user, then resets that user's password.                                            | Suspension and reset revoke old sessions. Temporary-password login exposes only password change; apps/background requests remain blocked until successful server-confirmed change.                                                                                        |
| LIVE-16 | Repeat launcher/app navigation and confirmations at 390×844 and by keyboard; inspect browser errors and accessibility.     | No workspace selector; PMS spaces remain in PMS. Labels, headings, badge contrast, focus return, and denial/retry are usable; no critical/serious accessibility violation or uncaught error.                                                                              |
| LIVE-17 | After an unmeasured cold login, measure ten warm rendered logins.                                                          | At least 9/10 reach a usable launcher within 3 seconds; none exceeds 5 seconds. Record cold start separately.                                                                                                                                                             |

## Capability Coverage

| IDs       | Scenario                                                                                         | Required result                                                                                                                                       |
| --------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-01–03 | Launcher, all-apps list, app navigation.                                                         | One account bootstrap; only admitted apps; categories never act as executable apps or authorization.                                                  |
| CAP-04–09 | PMS spaces, independent app routes, changing user/group grants, old URLs.                        | `/apps/:appId/...` only; PMS selection never becomes a global context. Unsupported workspace URLs have no compatibility redirect or inferred default. |
| CAP-10–12 | Identity changes, sharing URLs, failed bootstrap and retry.                                      | Prior principal data is synchronously discarded; sharing requires current app admission; bootstrap failure remains inert until retry succeeds.        |
| CAP-20–22 | Company master, selected user/group audience, required feature/system role.                      | Every gate applies on the server. Admin audience bypass cannot bypass master/features or personal resource ACLs.                                      |
| CAP-23–25 | Group/account/organization revocation while open; two users; stale asynchronous responses.       | Current authority applies without reload. No cross-user rows, search results, notifications, or permission-editor responses flash.                    |
| CAP-30–32 | Byte preview/download; wrong-session, expired, revoked and invalid capability.                   | Exact issuer/app/source/version binding; uniform denial before storage; safe type/disposition; no grants in URLs/referrers/model input.               |
| CAP-33–35 | Notifications, counts, mark-one/all, source or app revocation.                                   | Source-authorized list/count/read parity; no duplicate DM delivery; inaccessible notifications disappear.                                             |
| CAP-40–41 | Interleaved personal/company search and indexed-source revocation.                               | Live source ACL before counts/highlights/reranking/answers; survivor rank order retained; stale index metadata cannot grant access.                   |
| CAP-42–43 | AI discovery/write approval and queued-job revocation during execution.                          | User/app/source checked at execution seams and before provider/storage mutation; frozen approval cannot widen current authority.                      |
| CAP-50–53 | Recording result, explicit Docs publication, failed publication, concurrent result supersession. | No automatic standalone Docs publication; explicit publication is idempotent; app/source denial creates no result; stale version cannot publish.      |
| CAP-60–62 | Mobile, keyboard and WCAG A/AA checks.                                                           | Global launcher and app-owned spaces remain distinct; all dialogs/denials/actions are operable and no critical/serious violation remains.             |

## Minimum Browser Gate

For this company authorization redesign, run CAP-01–12, CAP-20–25, CAP-33–35, CAP-50–52,
CAP-60–62, and LIVE-00–16 against the rendered public-domain development application. Use at
least two isolated ordinary users plus an administrator, two apps with app-local resources,
a company app, and a personal app. API/unit tests own cryptographic expiry, DST gaps/folds,
search rank identity, queue/version fencing, and other deterministic seams. State any incomplete
live checks explicitly instead of substituting fixture or component results.
