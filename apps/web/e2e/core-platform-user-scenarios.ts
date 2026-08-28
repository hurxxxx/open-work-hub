export type CorePlatformScenarioDomain =
  | 'authentication'
  | 'launcher'
  | 'shell-navigation'
  | 'workspace-context'
  | 'global-personal-apps'
  | 'admin-app-controls'
  | 'responsive-accessibility'
  | 'resilience';

export type CorePlatformScenario = {
  id: string;
  domain: CorePlatformScenarioDomain;
  title: string;
  actor: 'anonymous' | 'administrator';
  viewport: 'desktop' | 'mobile' | 'both';
  preconditions: readonly string[];
  steps: readonly string[];
  expected: readonly string[];
  mutatesServerState?: boolean;
  restore?: readonly string[];
};

/**
 * User-observable acceptance scenarios for the app-first platform shell.
 *
 * These scenarios intentionally describe product behavior rather than browser
 * implementation details so they can be executed with agent-browser, Playwright,
 * or a human test pass. Any scenario that changes shared development data must
 * restore it before the test session ends.
 */
export const CORE_PLATFORM_USER_SCENARIOS = [
  {
    id: 'AUTH-001',
    domain: 'authentication',
    title: 'Anonymous users are contained by the login boundary',
    actor: 'anonymous',
    viewport: 'both',
    preconditions: ['No authenticated browser session exists.'],
    steps: ['Open /.', 'Open /apps/docs.', 'Use browser Back and Forward.'],
    expected: [
      'Every protected URL renders the login experience without protected shell content.',
      'The originally requested URL cannot expose workspace or company data before login.',
      'No uncaught exception or repeated unauthorized-request loop appears.',
    ],
  },
  {
    id: 'AUTH-002',
    domain: 'authentication',
    title: 'Seed administrator login lands on the neutral launcher',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The local seed Administrator account is available.'],
    steps: ['Open /.', 'Activate the Administrator seed-account button.'],
    expected: [
      'Login completes without entering credentials in the test transcript.',
      'The browser remains at / and renders the app launcher.',
      'No workspace is selected in global shell chrome.',
    ],
  },
  {
    id: 'AUTH-003',
    domain: 'authentication',
    title: 'Authenticated refresh preserves the current canonical app URL',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The administrator is authenticated.'],
    steps: ['Open a canonical workspace-app URL.', 'Reload the page.'],
    expected: [
      'The same app and workspace context render after refresh.',
      'The app does not fall back to a global workspace or a different app.',
      'No transient Not Found or render crash remains visible.',
    ],
  },
  {
    id: 'LAUNCH-001',
    domain: 'launcher',
    title: 'The root launcher exposes only executable leaf apps',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: ['Open /.', 'Enumerate every launcher card and destination.'],
    expected: [
      'Exactly 17 executable app cards are rendered for the seeded platform administrator.',
      'AI, Collaboration, and Business are not executable launcher cards.',
      'Every card points to /apps/:appId with no workspace copied into the URL.',
    ],
  },
  {
    id: 'LAUNCH-002',
    domain: 'launcher',
    title: 'Launcher cards communicate application scope',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The administrator is authenticated.'],
    steps: ['Open /.', 'Inspect workspace, company, and personal app cards.'],
    expected: [
      'Workspace apps show a workspace-app label and the eligible-workspace count.',
      'Company apps show a company-app label without a workspace count.',
      'Personal apps show a personal-app label without a workspace count.',
    ],
  },
  {
    id: 'LAUNCH-003',
    domain: 'launcher',
    title: 'App menus never behave as category pseudo-apps',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Open All Apps.',
      'Open favorites and personal-tools menus.',
      'Follow several app links.',
    ],
    expected: [
      'Menus contain executable leaf apps only.',
      'Following an app link resolves that app identity directly.',
      'No generic category shell or arbitrary tool-wrapper route is created.',
    ],
  },
  {
    id: 'SHELL-001',
    domain: 'shell-navigation',
    title: 'Cross-app navigation drops the previous workspace context',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: [
      'A workspace app is open at /apps/docs/workspaces/administrator.',
    ],
    steps: ['Open All Apps.', 'Navigate to PMS.', 'Navigate to Community.'],
    expected: [
      'PMS first opens through /apps/pms and resolves its own workspace preference.',
      'Community opens at /apps/community with no workspace segment or workspace query.',
      'The previous Docs workspace is never copied blindly to another app.',
    ],
  },
  {
    id: 'SHELL-002',
    domain: 'shell-navigation',
    title: 'Browser history preserves app and workspace boundaries',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Navigate from / to Docs in administrator.',
      'Navigate to Community.',
      'Use Back twice and Forward twice.',
    ],
    expected: [
      'Each history entry restores the exact canonical URL and matching shell chrome.',
      'Workspace selectors appear only on workspace-app entries.',
      'No stale app title, submenu, or workspace label survives a history transition.',
    ],
  },
  {
    id: 'SHELL-003',
    domain: 'shell-navigation',
    title: 'Legacy top-level routes remain unsupported',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: ['Open /docs.', 'Open /w/administrator/docs.', 'Open /business.'],
    expected: [
      'Each legacy route renders the product Not Found experience.',
      'No redirect, compatibility parser, or silent fallback rewrites the URL.',
      'The user can return to a valid app through visible shell navigation.',
    ],
  },
  {
    id: 'SHELL-004',
    domain: 'shell-navigation',
    title: 'Global widget dock survives app transitions without changing scope',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Open /.',
      'Open and close each global widget.',
      'Repeat inside a workspace app and a company app.',
    ],
    expected: [
      'Widget controls remain available wherever their platform policy permits.',
      'Opening a widget does not rewrite the current app or workspace URL.',
      'Closing a widget restores focus without a console exception.',
    ],
  },
  {
    id: 'SHELL-005',
    domain: 'shell-navigation',
    title: 'Settings remains shell-owned rather than an executable app',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Open Settings from the shell.',
      'Return to /.',
      'Inspect launcher and All Apps.',
    ],
    expected: [
      'Settings opens through its administrative shell route.',
      'Settings is not counted among the 17 executable app contracts.',
      'Returning to / restores the neutral launcher.',
    ],
  },
  {
    id: 'WORKSPACE-001',
    domain: 'workspace-context',
    title: 'Multiple eligible workspaces require an in-app choice',
    actor: 'administrator',
    viewport: 'both',
    preconditions: [
      'Docs is enabled in both administrator and general.',
      'No valid Docs preference is applied.',
    ],
    steps: ['Open /apps/docs.'],
    expected: [
      'The Docs shell renders with an in-app workspace chooser.',
      'Both eligible workspaces are shown and no arbitrary workspace is auto-selected.',
      'The AppBar contains no global workspace picker.',
    ],
  },
  {
    id: 'WORKSPACE-002',
    domain: 'workspace-context',
    title: 'Choosing a workspace produces the canonical workspace-app URL',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The Docs workspace chooser is visible.'],
    steps: ['Choose administrator.'],
    expected: [
      'The URL becomes /apps/docs/workspaces/administrator.',
      'Docs content and submenu match administrator.',
      'The app-local workspace selector identifies Administrator as current.',
    ],
    mutatesServerState: true,
    restore: [
      'Restore the prior Docs workspace preference or clear the preference through its owning API.',
    ],
  },
  {
    id: 'WORKSPACE-003',
    domain: 'workspace-context',
    title: 'Workspace preference is isolated per user and per app',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: [
      'Docs is preferred in administrator.',
      'PMS is preferred in general.',
    ],
    steps: [
      'Open /apps/docs.',
      'Navigate to /apps/pms.',
      'Return to /apps/docs.',
    ],
    expected: [
      'Docs resolves administrator.',
      'PMS resolves general independently.',
      'Returning to Docs does not inherit the PMS workspace.',
    ],
    mutatesServerState: true,
    restore: ['Restore both prior per-app preferences.'],
  },
  {
    id: 'WORKSPACE-004',
    domain: 'workspace-context',
    title: 'Workspace search filters server-backed eligible choices',
    actor: 'administrator',
    viewport: 'both',
    preconditions: [
      'At least administrator and general are eligible for Docs.',
    ],
    steps: [
      'Open /apps/docs.',
      'Search for General.',
      'Clear the search.',
      'Search for a missing name.',
    ],
    expected: [
      'General is the only matching selectable result.',
      'Clearing restores the full eligible list and correct count.',
      'A missing query shows an explicit empty result without retaining stale rows.',
    ],
  },
  {
    id: 'WORKSPACE-005',
    domain: 'workspace-context',
    title: 'A direct canonical deep link validates app availability',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['Docs is enabled for administrator.'],
    steps: ['Open /apps/docs/workspaces/administrator directly.', 'Reload.'],
    expected: [
      'Docs renders in administrator after both navigation and reload.',
      'The workspace selector lists only workspaces eligible for Docs.',
      'No global bootstrap or unrelated app availability decides access.',
    ],
  },
  {
    id: 'WORKSPACE-006',
    domain: 'workspace-context',
    title: 'An invalid workspace slug fails closed',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: ['Open /apps/docs/workspaces/not-a-workspace.'],
    expected: [
      'The route does not treat the invalid slug as selected or enabled.',
      'No workspace-scoped document request is made with a fallback workspace.',
      'The UI offers a safe recovery path without a render crash.',
    ],
  },
  {
    id: 'WORKSPACE-007',
    domain: 'workspace-context',
    title: 'Unexpected route parameters are rejected',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Open a canonical app route with an unsupported query parameter.',
      'Open a route whose suffix does not exist in the app contract.',
    ],
    expected: [
      'Unsupported contract parameters are not interpreted as app state.',
      'Unknown suffixes render Not Found instead of a fallback app root.',
      'The browser URL is not silently normalized through a legacy alias.',
    ],
  },
  {
    id: 'WORKSPACE-008',
    domain: 'workspace-context',
    title: 'Single eligible workspace auto-entry is deterministic',
    actor: 'administrator',
    viewport: 'both',
    preconditions: [
      'Exactly one workspace is eligible for the target workspace app.',
    ],
    steps: ['Open /apps/:appId.'],
    expected: [
      'The app enters the sole eligible workspace without showing a redundant chooser.',
      'The canonical URL includes that workspace slug.',
      'No other app preference influences the selection.',
    ],
    mutatesServerState: true,
    restore: ['Restore the original workspace app controls.'],
  },
  {
    id: 'WORKSPACE-009',
    domain: 'workspace-context',
    title: 'Zero eligible workspaces do not expose the workspace app',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['No workspace is eligible for the target workspace app.'],
    steps: ['Open /.', 'Open /apps/:appId directly.'],
    expected: [
      'The launcher omits the app.',
      'Direct entry fails closed and does not bootstrap a workspace.',
      'The UI explains unavailability without suggesting a workspace the user cannot access.',
    ],
    mutatesServerState: true,
    restore: ['Restore the original company and workspace app controls.'],
  },
  {
    id: 'WORKSPACE-010',
    domain: 'workspace-context',
    title: 'The selector never invents app navigation items',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: [
      'A workspace app whose manifest has no submenu is enabled.',
    ],
    steps: [
      'Open the app through /apps/:appId.',
      'Choose an eligible workspace if prompted.',
    ],
    expected: [
      'The app renders without a fabricated root submenu item.',
      'The workspace selector remains available in the owned shell surface.',
      'The app registry does not crash on an unknown navigation item.',
    ],
  },
  {
    id: 'GLOBAL-001',
    domain: 'global-personal-apps',
    title: 'Company app entry is independent of workspace context',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['Community is enabled by the company control.'],
    steps: [
      'Open /apps/community from /.',
      'Reload.',
      'Navigate from a workspace app back to Community.',
    ],
    expected: [
      'Community always uses /apps/community and never requests workspace bootstrap.',
      'No workspace selector or workspace label appears.',
      'Reload and cross-app navigation preserve company scope.',
    ],
  },
  {
    id: 'GLOBAL-002',
    domain: 'global-personal-apps',
    title: 'Personal apps never inherit workspace state',
    actor: 'administrator',
    viewport: 'both',
    preconditions: [
      'The administrator may access Mail, Planner, and Codex Terminal.',
    ],
    steps: ['Open each personal app from a workspace app.', 'Reload each app.'],
    expected: [
      'Each app uses /apps/:appId without a workspace segment.',
      'No workspace selector appears.',
      'Workspace query parameters from the prior app are not retained.',
    ],
  },
  {
    id: 'GLOBAL-003',
    domain: 'global-personal-apps',
    title: 'Global shared resource links use app-first routes',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['A shared Docs or Whiteboard resource is visible.'],
    steps: [
      'Open the shared resource link.',
      'Copy and reopen its URL in the same authenticated session.',
    ],
    expected: [
      'The URL is rooted under the owning /apps/:appId route.',
      'The resource opens without inventing a workspace context.',
      'Company app control is enforced before shared content is exposed.',
    ],
  },
  {
    id: 'ADMIN-001',
    domain: 'admin-app-controls',
    title:
      'Company and workspace controls are presented as different policy layers',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator can access platform settings.'],
    steps: [
      'Open the Apps administration section.',
      'Inspect company controls and workspace controls.',
    ],
    expected: [
      'Executable apps are listed individually rather than by legacy visibility group.',
      'Company master controls and workspace defaults/overrides are visually distinct.',
      'Personal/platform restrictions cannot be edited as workspace visibility.',
    ],
  },
  {
    id: 'ADMIN-002',
    domain: 'admin-app-controls',
    title: 'Company master disable wins over workspace enablement',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['A workspace app is currently enabled in administrator.'],
    steps: [
      'Disable the app at company level.',
      'Open /.',
      'Open the prior canonical workspace URL directly.',
    ],
    expected: [
      'The launcher omits the app.',
      'Direct workspace entry fails closed.',
      'Workspace enablement cannot override the disabled company master.',
    ],
    mutatesServerState: true,
    restore: [
      'Restore the original company master control and verify launcher recovery.',
    ],
  },
  {
    id: 'ADMIN-003',
    domain: 'admin-app-controls',
    title: 'Workspace override wins over workspace default only',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The company master for the target app is enabled.'],
    steps: [
      'Set a workspace default.',
      'Set the opposite explicit override for administrator.',
      'Compare administrator and general eligibility.',
    ],
    expected: [
      'Administrator follows its explicit override.',
      'General follows the workspace default in the absence of an override.',
      'Removing an override returns evaluation to the default without stale launcher state.',
    ],
    mutatesServerState: true,
    restore: ['Restore the original default and overrides.'],
  },
  {
    id: 'ADMIN-004',
    domain: 'admin-app-controls',
    title: 'Missing policy values fail closed',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['A target app control can be returned to an unset state.'],
    steps: [
      'Remove the target workspace default and override.',
      'Open launcher and direct app URL.',
    ],
    expected: [
      'The missing value evaluates as disabled.',
      'The UI does not infer enablement from an old visibility group or client cache.',
      'Direct access and background-triggering UI remain unavailable.',
    ],
    mutatesServerState: true,
    restore: ['Restore the original controls.'],
  },
  {
    id: 'ADMIN-005',
    domain: 'admin-app-controls',
    title:
      'Control changes invalidate stale launcher and preference assumptions',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['A workspace app has a saved workspace preference.'],
    steps: [
      'Disable that app in the preferred workspace.',
      'Reopen /apps/:appId.',
    ],
    expected: [
      'The stale preference is not treated as eligible.',
      'The app chooses the sole remaining eligible workspace or shows the current eligible chooser.',
      'The disabled workspace is not shown as current.',
    ],
    mutatesServerState: true,
    restore: ['Restore the original controls and preference.'],
  },
  {
    id: 'RESPONSIVE-001',
    domain: 'responsive-accessibility',
    title: 'Mobile navigation exposes all executable apps',
    actor: 'administrator',
    viewport: 'mobile',
    preconditions: [
      'The administrator is authenticated on an iPhone-sized viewport.',
    ],
    steps: [
      'Open /.',
      'Open the mobile app menu.',
      'Scroll through the complete list.',
    ],
    expected: [
      'All 17 eligible executable apps are reachable, not only the first app per category.',
      'Scope labels remain understandable at mobile width.',
      'No app item is clipped behind the viewport or widget dock.',
    ],
  },
  {
    id: 'RESPONSIVE-002',
    domain: 'responsive-accessibility',
    title: 'Workspace choice remains usable on mobile',
    actor: 'administrator',
    viewport: 'mobile',
    preconditions: ['Two workspaces are eligible for Docs.'],
    steps: [
      'Open /apps/docs.',
      'Search for General.',
      'Choose General.',
      'Open the in-app selector again.',
    ],
    expected: [
      'Search, result selection, and current-workspace label are fully visible and operable.',
      'The selector is inside the Docs-owned mobile shell, not global AppBar chrome.',
      'The canonical workspace URL updates without horizontal overflow.',
    ],
    mutatesServerState: true,
    restore: ['Restore the prior Docs preference.'],
  },
  {
    id: 'RESPONSIVE-003',
    domain: 'responsive-accessibility',
    title: 'Keyboard focus follows menus, chooser, and app transitions',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['The administrator is authenticated.'],
    steps: [
      'Navigate launcher controls using Tab and Enter.',
      'Open and close All Apps.',
      'Operate the workspace chooser by keyboard.',
    ],
    expected: [
      'Every interactive control has a visible focus target and usable accessible name.',
      'Closing a menu returns focus to its trigger.',
      'Navigation does not trap focus in an unmounted menu or selector.',
    ],
  },
  {
    id: 'RESPONSIVE-004',
    domain: 'responsive-accessibility',
    title: 'Core shell passes automated WCAG A/AA checks',
    actor: 'administrator',
    viewport: 'both',
    preconditions: [
      'The launcher, a workspace chooser, a workspace app, and a company app are reachable.',
    ],
    steps: ['Run an axe audit on each representative surface.'],
    expected: [
      'No critical or serious WCAG A/AA violation is introduced by the app-first shell.',
      'Inputs, buttons, dialogs, navigation regions, and scope labels have accessible names.',
    ],
  },
  {
    id: 'RESILIENCE-001',
    domain: 'resilience',
    title: 'API failures do not leak stale app or workspace state',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: [
      'A local development browser may intercept one eligible-workspaces request.',
    ],
    steps: [
      'Fail the eligible-workspaces request.',
      'Open /apps/docs.',
      'Remove interception and retry.',
    ],
    expected: [
      'The failure produces a localized retry state rather than fabricating or falling back to another workspace.',
      'An already-authorized canonical workspace remains current while workspace discovery is unavailable.',
      'Retry recovers without a full browser-session reset.',
    ],
  },
  {
    id: 'RESILIENCE-002',
    domain: 'resilience',
    title: 'Rapid app transitions cannot apply stale async responses',
    actor: 'administrator',
    viewport: 'desktop',
    preconditions: ['Docs and PMS are both eligible in multiple workspaces.'],
    steps: [
      'Open Docs.',
      'Immediately navigate to PMS and then Community.',
      'Wait for all requests to settle.',
    ],
    expected: [
      'The final Community surface contains no Docs or PMS chooser/results.',
      'Late workspace responses cannot rewrite the current URL or shell title.',
      'No aborted-request exception is rendered to the user.',
    ],
  },
  {
    id: 'RESILIENCE-003',
    domain: 'resilience',
    title: 'Core journeys remain free of unexpected console and network errors',
    actor: 'administrator',
    viewport: 'both',
    preconditions: ['The local development API and web server are healthy.'],
    steps: [
      'Execute launcher, workspace-app, company-app, personal-app, and settings journeys.',
      'Inspect page errors, console, and failed API requests after each transition.',
    ],
    expected: [
      'No uncaught JavaScript exception or unhandled rejection occurs.',
      'No unexpected 4xx/5xx request is triggered by a valid user journey.',
      'Expected unavailable optional services are surfaced as bounded feature states, not shell failures.',
    ],
  },
] as const satisfies readonly CorePlatformScenario[];

export function getCorePlatformScenario(id: string): CorePlatformScenario {
  const scenario = CORE_PLATFORM_USER_SCENARIOS.find(
    (candidate) => candidate.id === id,
  );
  if (!scenario) {
    throw new Error(`Unknown core platform scenario: ${id}`);
  }
  return scenario;
}
