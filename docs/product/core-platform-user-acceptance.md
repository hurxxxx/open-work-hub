# Core Platform User Acceptance

These scenarios verify [ADR 0012](../../adr/0012-company-app-access-without-workspaces.md).
Company app admission, directory groups, and app-owned resources replace product workspaces.
Policy owners remain [App Platform](../domains/app-platform/README.md),
[Organization](../domains/organization/README.md), [Source Access](../domains/source-access/README.md),
[Content Access](../domains/content-access/README.md), [Notifications](../domains/notifications/README.md),
[AI Execution](../domains/ai/execution.md), and [Recording](../apps/recording/README.md).

## Personas And Evidence

Use four isolated named browser sessions. Roles below describe the initial fixture state; record each
intentional change before testing it. A must not also own or join the personal resources used to test
administrator access.

| Actor | Initial role and resource relationship                                                                                             | Purpose                                                                                             |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| A     | Active platform administrator, no B/C resource grants or PMS membership.                                                           | Administration; personal-read denial versus company-business read without writes.                   |
| B     | Ordinary user admitted to the tested apps; creator of disposable resources and two PMS spaces.                                     | Personal ownership, explicit publication and explicit space ownership.                              |
| C     | Ordinary admitted user, granted access through a disposable manual/organization group; no direct PMS membership initially.         | Group-derived member/admin roles, preservation and revocation.                                      |
| D     | Ordinary admitted user with no resource grants. Temporarily remove app admission or reset this account only in the named branches. | Unshared-reader denial, company audience, app-ineligible sharing links and temporary-password flow. |

Create disposable groups, organization units, PMS spaces and app records with a UTC run ID through
visible controls. Record their IDs and the original app policies, group memberships, primary organization,
head assignments and account state needed for restoration. Keep at least one active administrator and
one explicit owner per space. Do not reuse existing business records or real mailboxes for fixtures.
For Mail, use only an already configured disposable test mailbox; unavailable credentials/provider or
an unavailable editor/worker dependency makes that branch BLOCKED, not permission to change deployment
configuration.

A hidden button is insufficient evidence of server authorization. A denied UI navigation must include
its actual response status when a request occurs; a hidden action or absence of a request proves only
the UI boundary and must be paired with the named API test. Keep credentials, cookies, authorization
headers, share tokens, content grants, raw HAR files and environment values out of reports. Redact secret
URL path/query/fragment values, including shared-link tokens, before recording routes or screenshots.

Restore app policies and grants before deleting fixture resources and groups. Restore original
organization/head assignments and reactivate any suspended fixture account before final logout. Remove
only this run's disposable resources; record residual objects and failed cleanup rather than reading a
user's personal content through an administrator bypass. Confirm restoration in the UI, then sign out
all actors and check Back/Forward again.

## Live Browser Execution Contract

- For development, start the documented Web/API/Worker and real dependencies with
  `./dev.sh --with-worker --restart`. Run `OPEN_WORK_HUB_UAT_BASE_URL=https://… pnpm uat:preflight`
  before the measured public-domain development gate. Record environment, origin, deployed Git commit,
  UTC run ID, service readiness and first rendered login snapshot. Localhost smoke does not replace it.
  A production journey follows the authorized deployment and uses a separate evidence record; never
  run development startup/reset commands against production or copy development results as production
  results. The full master-disable and fixture-registration journey is the development gate; record
  the exact production branches exercised with the permitted disposable actors.
- Use the rendered login/signup and administration controls. Fixture provisioning may establish
  the initial administrator; it does not prove an administration workflow.
- Never share session state across actors. Measured interactions use visible browser controls,
  real APIs, PostgreSQL, object storage, and workers. Direct API/SQL setup, request interception,
  or synthetic responses cannot substitute for measured UI actions.
- Upload only disposable local fixtures through absolute paths. Confirm both the successful action
  and its denial or persistence boundary. Keep passwords only in ephemeral variables/secret storage.
- Report each executed branch as PASS, FAIL or BLOCKED with actor, sanitized route, visible result,
  response status, evidence type and restoration status. Use NOT RUN for an unattempted branch.
  A partially executed scenario cannot receive an aggregate PASS. Bootstrap failure/retry requires
  its own observed browser failure; a successful bootstrap or mocked component test does not prove it.
- Run conflicting policy/organization changes sequentially across actors. During the unrelated-change
  draft check, keep B's unsaved dialog open and perform only the specified A action. Concurrent SQL
  transactions, a revoked response returning from a provider and queued delivery races are automated
  seams; repeated browser clicks do not establish those guarantees.

## Repeatable Live Journey

| ID      | Rendered action                                                                                                                             | Required evidence                                                                                                                                                                                                                                                             |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LIVE-00 | Start services and run public-origin preflight before opening the browser.                                                                  | Web/API/Worker and dependencies ready; public origin renders the application login shell.                                                                                                                                                                                     |
| LIVE-01 | B, C and D register through signup and open the launcher; make D app-ineligible for a named branch.                                         | Company policies determine available apps; no workspace enrollment, chooser or default container appears. D cannot open a denied direct app or shared-link route. Restore D’s admission before testing an unshared but app-admitted reader.                                   |
| LIVE-02 | C signs out, signs in, and uses Back/Forward.                                                                                               | Previous account data disappears synchronously, including drafts, app bootstrap, notifications, and personal caches.                                                                                                                                                          |
| LIVE-03 | A opens administration and Groups; B tries the same routes.                                                                                 | A can manage company accounts/groups; B receives server denial. PMS role changes cannot grant platform administration.                                                                                                                                                        |
| LIVE-04 | A creates a manual group containing B and selects it as the audience of a disposable test app policy.                                       | B gains app entry without reload; C remains denied. Empty selected audiences deny both. Restore the prior app policy afterward.                                                                                                                                               |
| LIVE-05 | While C uses the group-admitted app, A removes C from the grant group, then restores membership; exercise the Mail branch below.            | Current app entry and open protected state clear without reload. Observe actual denied requests separately from hidden UI. Restoring membership restores app entry, not a new resource grant. Mail worker cancellation requires additional automated evidence.                |
| LIVE-06 | A changes C’s exact primary organization and head assignments while preserving C’s manual group; perform the unrelated-change branch below. | Only exact organization membership changes; manual membership persists, head/ancestor metadata grants no access. Unrelated organization edits preserve B’s unsaved dialog. Concurrent cycle prevention is an API/database test, not a browser PASS.                           |
| LIVE-07 | B creates two PMS spaces; C creates a list and folder using only a group member role, then tests group admin and revocation.                | Only a new space’s creator becomes owner. List/folder creation preserves C’s derived role and creates no direct owner membership; group removal still removes C’s access. Non-owner space admin cannot assign admin/owner; A has company read only and a viewer cannot write. |
| LIVE-08 | B shares and publishes disposable Docs, Whiteboard, Bento and Diagrams records using the branches below.                                    | Distinguish personal ownership, company ownership, company audience and project links. A’s personal-read denial and company-read-only success are separate actor checks; D isolates company audience from other grants. Record each app/transition independently.             |
| LIVE-09 | B uploads and downloads a small allowed Files fixture.                                                                                      | Real bytes match the source checksum. Content grants remain absent from request URLs and evidence. Cross-user/expired/revoked grants are denied by deterministic API coverage.                                                                                                |
| LIVE-10 | B creates a Community post; A comments while B keeps it open, then B reads its notification.                                                | One realtime update and one notification, no bot DM duplicate; focus/visibility refresh does not duplicate requests; read state persists.                                                                                                                                     |
| LIVE-11 | B creates, updates and deletes a Planner event; inspect calendar/dock after each action and reload. A separately attempts B’s event route.  | Mutations persist and update the dock immediately. A cannot read B’s personal event by administrator role. A hidden event in A’s calendar alone is insufficient; record the direct-route denial or mark that subcase NOT RUN.                                                 |
| LIVE-12 | B and C exchange DM messages and a disposable image attachment; A and D remain nonparticipants.                                             | Realtime replies and unread state work; authenticated preview/download works for participants. A/D cannot read the thread or attachment. Signed-grant session/expiry and queued-revocation seams remain separate automated evidence.                                          |
| LIVE-13 | In development, A disables the tested app’s company master while B views it, then restores the exact prior policy.                          | Everyone, including A, is denied. B’s open state clears; unrelated apps remain available. Restore both master and original audience/grants. Do not infer this production result from a development run.                                                                       |
| LIVE-14 | A cancels then confirms disposable group grant removal/deactivation.                                                                        | Cancel is inert and restores focus. Confirmation explains immediate access loss; records remain while revoked grants stop authorizing reads, writes, search, and notifications.                                                                                               |
| LIVE-15 | A suspends/reactivates disposable D, resets D’s password, then D logs in with the temporary password and changes it.                        | Old sessions fail after suspension/reset. Temporary-password login exposes only password change; direct app entry stays blocked until the server confirms the change. Restore D’s active/admission state and separately record unexercised background/worker checks.          |
| LIVE-16 | Repeat launcher/app navigation and confirmations at 390×844 and by keyboard; inspect browser errors and accessibility.                      | No workspace selector; PMS spaces remain in PMS. Labels, headings, badge contrast, focus return, and denial/retry are usable; no critical/serious accessibility violation or uncaught error.                                                                                  |
| LIVE-17 | After an unmeasured cold login, measure ten warm rendered logins.                                                                           | At least 9/10 reach a usable launcher within 3 seconds; none exceeds 5 seconds. Record cold start separately.                                                                                                                                                                 |

## Changed-Policy Branches

These branches refine existing LIVE IDs; they do not replace the unchanged required journeys.

| Branch                 | Visible actions and acceptance                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LIVE-05.mail           | With B admitted to Mail, verify B’s disposable inbox and a normal sync; A separately attempts that personal mailbox and is denied. Revoke B’s selected user/group admission while Mail is open, observe the app denial, then restore it. UI evidence covers removal/persistence only. Claim cancellation before provider I/O or rejection of an already fetched response only from the automated worker/service checks below.                                                                                                                                                                                                                                                                                                                                                                                          |
| LIVE-06.metadata       | A assigns C to organization X plus a manual group, moves C to Y and changes heads/parents. C keeps the manual grant, belongs only to Y’s exact organization group and gains no head/ancestor authority. With B unrelated to the edited organization, keep a typed unsaved dialog open during A’s create/rename/parent-only or unchanged save; the dialog and text persist. Do not mix this witness window with actual B policy changes, which should invalidate protected state.                                                                                                                                                                                                                                                                                                                                       |
| LIVE-07.creation       | B is the explicit owner of Alpha/Beta. Grant C a group member role without a direct member row; C creates both a folder and a list in Alpha. Check C’s effective role and the direct member list again, then revoke the group and verify access loss without reload. Repeat with group admin: business management remains available, but creation never produces owner and member/viewer rows offer no admin/owner promotion. B still has all four explicit-user role choices; A’s platform role supplies no write or ownership.                                                                                                                                                                                                                                                                                       |
| LIVE-08.docs           | B saves a personal document and grants C’s group read access. The list must no longer claim personal-only/private; A and unshared D are denied. Publish to Alpha with acknowledgment while company visibility remains off: A can read but cannot edit, D is still denied. Enable company visibility and verify D can read; select Beta as the primary connection and verify company visibility remains on and Alpha/C access remains. Turn off company visibility: D loses access, but C’s group/project grant and A’s company read remain. Re-enable company visibility, remove only the primary connection and verify D can still read. No transition implies that other user/group/link/project grants were removed or ownership became personal. Finish with company visibility off and disposable links disabled. |
| LIVE-08.whiteboard     | B creates a personal board and tests group/link sharing; a configured share is never labeled personal-only. Connect it to PMS with company visibility off: the hub says restricted access, and the company-publication action remains available. Test company enable/disable and primary connection removal independently with C/D as above. The menu and section use the actual company audience, while the notice states that other grants and administrator company-read access survive. Exercise read-link downgrade, regeneration and disable against C’s already open tab; old tokens cannot reuse owner/direct rights.                                                                                                                                                                                          |
| LIVE-08.bento-diagrams | In each available editor, B creates personal content; A and D are denied. B explicitly publishes after the company-read/irreversibility acknowledgment, and admitted A/D can read without edit/archive rights. No active menu offers return to personal ownership; the company ownership notice remains visible. For readers, exercise title input, canvas double-click/keyboard/drag, save and AI controls: the official viewer must remain noneditable and issue no mutation. For the owner, create/save and export/import must still work. API rejection of a forged personal transition is separate automated evidence. Unavailable editor runtime blocks that app’s branch rather than passing the entire LIVE-08 row.                                                                                                                                                                                                                                                                                                                         |

### Additional LIVE-08 Publication Entry Points

Also exercise these publication entry points in LIVE-08: PMS sidebar document creation, task-description
promotion, and Whiteboard creation/selection from PMS and Meeting. Cancel the company transition before
confirming it; cancellation must issue no write and preserve an open picker. Confirmed project publication
must succeed without enabling the company-wide audience. Link a personal Docs item to a task as a reference,
then open space order editing: that reference, read-only documents and documents primarily owned by another
project must not become reorderable publication targets. Record these entry points separately. During a pending selection, closing/reopening the picker must not let an old response close the new session; Meeting/PMS prevent a concurrent slot replacement. Boards without sharing-management permission are not attach candidates. Member roles may create lists/folders/tasks, but project Docs publication requires admin; viewer roles see no creation action.

## Automated Evidence Kept Separate

| Seam                                              | Evidence source and expectation                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PMS creator/roles and live group revocation       | `apps/api/tests/test_pms_creation_permissions.py` and `apps/api/tests/test_company_content_boundaries.py`: group-derived list/folder creation never inserts direct ownership; revocation remains effective. Browser role/menu checks alone do not prove the persisted membership invariant.                                                                                                                                    |
| Docs/Whiteboard ownership and sharing summaries   | `apps/api/tests/test_content_sharing_projection.py` and `apps/api/tests/test_company_content_boundaries.py`: retained grants, inactive-group sharing configuration, irreversible ownership and current source denial. `apps/web/src/app-modules/docs/views/DocsPublicationControls.spec.tsx` verifies rendered independent controls and stale-response rejection with mocked API responses; it is not a public browser result. |
| Mail queued and in-flight revocation              | `apps/api/tests/test_mail_personal_scope.py` and `apps/worker/tests/test_mail_tasks.py`: current account/user/group/app gate after claim and external I/O; revoked work becomes cancelled without retry or message/checkpoint writes. A UI showing a removed Mail icon does not prove these seams.                                                                                                                             |
| Organization concurrency and targeted refresh     | `apps/api/tests/test_organization_concurrency_migrations.py` proves overlapping subtree moves cannot create a cycle; `apps/api/tests/test_company_groups.py` checks exact member/head invalidation recipients. LIVE-06 observes draft preservation and final directory behavior, not transactional race scheduling.                                                                                                            |
| Forged ownership transition and capability replay | Bento/Diagrams API tests and content/realtime security suites prove server denial, exact link/session binding and queued payload checks. Record their command, commit and result separately from visible controls.                                                                                                                                                                                                             |

## Capability Coverage

| IDs       | Scenario                                                                                         | Required result                                                                                                                                                       |
| --------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CAP-01–03 | Launcher, all-apps list, app navigation.                                                         | One account bootstrap; only admitted apps; categories never act as executable apps or authorization.                                                                  |
| CAP-04–09 | PMS spaces, independent app routes, changing user/group grants, old URLs.                        | `/apps/:appId/...` only; PMS selection never becomes a global context. Unsupported workspace URLs have no compatibility redirect or inferred default.                 |
| CAP-10–12 | Identity changes, sharing URLs, failed bootstrap and retry.                                      | Prior principal data is synchronously discarded; sharing requires current app admission; bootstrap failure remains inert until retry succeeds.                        |
| CAP-20–22 | Company master, selected user/group audience, required feature/system role.                      | Every gate applies on the server. Admin audience bypass cannot bypass master/features or personal resource ACLs.                                                      |
| CAP-23–25 | Group/account/organization revocation while open; two users; stale asynchronous responses.       | Current authority applies without reload. No cross-user rows, search results, notifications, or permission-editor responses flash.                                    |
| CAP-30–32 | Byte preview/download; wrong-session, expired, revoked and invalid capability.                   | Exact issuer/app/source/version binding; uniform denial before storage; safe type/disposition; no grants in network request URLs, referrers, model input or evidence. |
| CAP-33–35 | Notifications, counts, mark-one/all, source or app revocation.                                   | Source-authorized list/count/read parity; no duplicate DM delivery; inaccessible notifications disappear.                                                             |
| CAP-40–41 | Interleaved personal/company search and indexed-source revocation.                               | Live source ACL before counts/highlights/reranking/answers; survivor rank order retained; stale index metadata cannot grant access.                                   |
| CAP-42–43 | AI discovery/write approval and queued-job revocation during execution.                          | User/app/source checked at execution seams and before provider/storage mutation; frozen approval cannot widen current authority.                                      |
| CAP-50–53 | Recording result, explicit Docs publication, failed publication, concurrent result supersession. | No automatic standalone Docs publication; explicit publication is idempotent; app/source denial creates no result; stale version cannot publish.                      |
| CAP-60–62 | Mobile, keyboard and WCAG A/AA checks.                                                           | Global launcher and app-owned spaces remain distinct; all dialogs/denials/actions are operable and no critical/serious violation remains.                             |

## Minimum Browser Gate

For this company authorization redesign, run CAP-01–12, CAP-20–25, CAP-33–35, CAP-50–52,
CAP-60–62, and LIVE-00–16 against the rendered public-domain development application. Use all
four isolated actors A/B/C/D, two apps with app-local resources, a company app and a personal app. API/unit tests own cryptographic expiry, DST gaps/folds,
search rank identity, queue/version fencing, and other deterministic seams. State any incomplete
live checks explicitly instead of substituting fixture or component results.

## Run Evidence Template

This document defines acceptance; it records no execution success. Fill one evidence row per executed
branch and environment in the run report. Keep LIVE-00–16 as the 17 mandatory development scenarios;
LIVE-17 is a separate warm-login performance measure. For capability ranges, name the specific missing
subcase rather than assigning PASS to the whole range.

| Environment / deployed commit / UTC run | Scenario or branch / CAP IDs | Actor and initial grants | Evidence type                                                         | Sanitized route, visible result and response status | Result  | Restoration / residual fixture IDs |
| --------------------------------------- | ---------------------------- | ------------------------ | --------------------------------------------------------------------- | --------------------------------------------------- | ------- | ---------------------------------- |
| To fill                                 | To fill                      | To fill                  | Public browser / component mock / API / worker / database concurrency | To fill; “no request” only describes UI behavior    | NOT RUN | To fill                            |

Attach a short inventory of blocked or unattempted branches, actual production coverage, and the
commands/results for automated seams. Do not combine results from different commits or environments
without identifying them. Store only sanitized evidence; temporary credentials are not report data.
