import { describe, expect, it } from 'vitest';

import type { AuthUser, WorkspaceSummary } from './platform/auth/auth-api';
import { resolveShellState } from './app-shell';

function buildWorkspace(
  overrides: Partial<WorkspaceSummary> = {},
): WorkspaceSummary {
  return {
    id: 'workspace-delivery-hub',
    slug: 'delivery-hub',
    name: 'Delivery Hub',
    role: 'member',
    ...overrides,
  };
}

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'member',
    email: 'member@open-work-hub.local',
    full_name: 'Open Work Hub Member',
    display_name: 'Open Work Hub Member',
    status: 'active',
    theme_preference: 'system',
    locale: 'ko-KR',
    workspaces: [buildWorkspace()],
    workspace_roles: [],
    system_roles: [],
    must_change_password: false,
    ...overrides,
  };
}

describe('resolveShellState', () => {
  it('falls back to the home shell for users without workspace membership', () => {
    const userWithoutPms = buildUser({
      workspaces: [],
    });
    expect(resolveShellState('/w/delivery-hub/pms', userWithoutPms)).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/w/delivery-hub/pms/lists/demo', userWithoutPms),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('keeps PMS shell state for authorized PMS routes', () => {
    expect(resolveShellState('/w/delivery-hub/pms', buildUser())).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-inbox',
    });
    expect(
      resolveShellState('/w/delivery-hub/pms/assigned', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-tasks-assigned',
    });
    expect(
      resolveShellState('/w/delivery-hub/pms/lists/demo', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-list-demo',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/pms/spaces/space-1/docs/doc-1',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'pms-space-space-1-docs-doc-1',
    });
  });

  it('keeps integrated search as its own shell state', () => {
    expect(
      resolveShellState('/tool/search?workspace=delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'search',
      activeNavItemId: 'search',
    });
  });

  it('routes the new workspace meeting path to the meeting shell', () => {
    expect(resolveShellState('/w/delivery-hub/meeting', buildUser())).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'meeting-upcoming',
    });
    expect(
      resolveShellState('/w/delivery-hub/meeting?scope=mine', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'meeting-mine',
    });
    expect(
      resolveShellState('/w/delivery-hub/meeting?tab=recordings', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'meeting-recordings',
    });
    expect(resolveShellState('/w/delivery-hub/home', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses whiteboard manifest query views for the active navigation item', () => {
    expect(
      resolveShellState('/w/delivery-hub/whiteboard', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'whiteboard-all',
    });
    expect(
      resolveShellState('/w/delivery-hub/whiteboard?view=mine', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'whiteboard-my',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/whiteboard?view=favorites',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'whiteboard-favorites',
    });
  });

  it('uses global planner query views for the active planner navigation item', () => {
    expect(resolveShellState('/planner', buildUser(), ['planner'])).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-calendar',
    });
    expect(
      resolveShellState('/planner?view=timeline', buildUser(), ['planner']),
    ).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-timeline',
    });
  });

  it('routes community paths to the company-wide community shell', () => {
    expect(
      resolveShellState('/community', buildUser({ workspaces: [] })),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/community', buildUser({ workspaces: [] }), [
        'community',
      ]),
    ).toEqual({
      activeAppId: 'community',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/community?channel=suggestions', buildUser(), [
        'community',
      ]),
    ).toEqual({
      activeAppId: 'community',
      activeNavItemId: '',
    });
  });

  it('uses docs query views for the active docs navigation item', () => {
    expect(resolveShellState('/w/delivery-hub/docs', buildUser())).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=mine', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-my',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=shared', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-shared',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=private', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-private',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=meeting_notes', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-notes',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/docs/doc-1?view=recent&page=page-1',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-recent',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=archived', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-archived',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs?view=unknown', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-all',
    });
  });

  it('uses manifest global routes for shared docs and whiteboards', () => {
    expect(
      resolveShellState('/docs/shared/share-1', buildUser(), ['docs']),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/docs/shared/share-1/html/page-1', buildUser(), [
        'docs',
      ]),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/whiteboard/shared/share-1', buildUser(), [
        'whiteboard',
      ]),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: '',
    });
  });

  it('uses leaf bootstrap IDs to gate aggregate global route chrome', () => {
    expect(
      resolveShellState('/docs/shared/share-1', buildUser(), ['docs']),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/docs/shared/share-1', buildUser(), ['whiteboard']),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/whiteboard/shared/share-1', buildUser(), [
        'whiteboard',
      ]),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: '',
    });
  });

  it('uses the settings shell resolver for admin routes', () => {
    const adminUser = buildUser({ system_roles: ['platform_admin'] });
    expect(resolveShellState('/admin', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-general',
    });
    expect(resolveShellState('/admin/users', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-people',
    });
    expect(resolveShellState('/admin/people', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-people',
    });
    expect(resolveShellState('/admin/teams', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-workspaces',
    });
    expect(resolveShellState('/admin/apps', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-apps-platform',
    });
    expect(resolveShellState('/admin/apps/workspace', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-apps-workspace',
    });
    expect(resolveShellState('/admin/apps/app-bar', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-apps-app-bar',
    });
    expect(resolveShellState('/admin/llm', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-llm',
    });
    expect(resolveShellState('/admin/llm?tab=providers', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-llm',
    });
    expect(resolveShellState('/admin/model-monitoring', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-model-monitoring',
    });
    expect(resolveShellState('/admin/document-processing', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-document-processing',
    });
    expect(resolveShellState('/admin/ai-security', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-ai-security',
    });
    expect(resolveShellState('/admin/community', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-community',
    });
    expect(resolveShellState('/admin/usage', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-usage',
    });
    expect(resolveShellState('/admin/audit', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-audit',
    });
    expect(resolveShellState('/admin', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('falls back to home for unknown workspace app routes', () => {
    expect(
      resolveShellState(
        '/w/delivery-hub/unknown-app/unknown-tool',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses recording query filters for the active recording navigation item', () => {
    expect(resolveShellState('/w/delivery-hub/recording', buildUser())).toEqual(
      {
        activeAppId: 'collaboration',
        activeNavItemId: 'recording-quick',
      },
    );
    expect(
      resolveShellState('/w/delivery-hub/recording?view=mine', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-mine',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/recording?view=needs_review',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-mine',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/recording?view=mine&category=meeting',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-meeting',
    });
    expect(
      resolveShellState(
        '/w/delivery-hub/recording?view=processing',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-processing',
    });
    expect(
      resolveShellState('/w/delivery-hub/recording?view=failed', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-failed',
    });
    expect(
      resolveShellState('/w/delivery-hub/recording?view=archived', buildUser()),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'recording-archived',
    });
  });

  it('legacy /meeting path no longer activates the meeting shell', () => {
    expect(resolveShellState('/meeting', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    for (const legacyPath of ['/docs', '/pms', '/planner']) {
      expect(resolveShellState(legacyPath, buildUser())).toEqual({
        activeAppId: 'home',
        activeNavItemId: '',
      });
    }
  });

  it('falls back to home when the workspace bootstrap disables the app', () => {
    expect(
      resolveShellState('/w/delivery-hub/docs', buildUser(), [
        'home',
        'business',
      ]),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs/private', buildUser(), [
        'home',
        'business',
      ]),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses leaf bootstrap IDs while preserving aggregate shell chrome', () => {
    expect(
      resolveShellState('/w/delivery-hub/docs', buildUser(), ['docs']),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/w/delivery-hub/docs', buildUser(), ['collaboration']),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/tool/docs-all?workspace=delivery-hub', buildUser(), [
        'docs',
      ]),
    ).toEqual({
      activeAppId: 'collaboration',
      activeNavItemId: 'docs-all',
    });
  });
});
