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
  it('keeps the launcher neutral and identifies workspace app entry routes', () => {
    expect(resolveShellState('/', buildUser())).toEqual({
      activeAppId: 'launcher',
      activeNavItemId: '',
    });
    expect(resolveShellState('/apps/docs', buildUser(), ['docs'])).toEqual({
      activeAppId: 'docs',
      activeNavItemId: '',
    });
  });

  it('falls back to the home shell for users without workspace membership', () => {
    const userWithoutPms = buildUser({
      workspaces: [],
    });
    expect(
      resolveShellState('/apps/pms/workspaces/delivery-hub', userWithoutPms),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState(
        '/apps/pms/workspaces/delivery-hub/lists/demo',
        userWithoutPms,
      ),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('keeps PMS shell state for authorized PMS routes', () => {
    expect(
      resolveShellState('/apps/pms/workspaces/delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-inbox',
    });
    expect(
      resolveShellState(
        '/apps/pms/workspaces/delivery-hub/assigned',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-tasks-assigned',
    });
    expect(
      resolveShellState(
        '/apps/pms/workspaces/delivery-hub/lists/demo',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-list-demo',
    });
    expect(
      resolveShellState(
        '/apps/pms/workspaces/delivery-hub/spaces/space-1/docs/doc-1',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'pms',
      activeNavItemId: 'pms-space-space-1-docs-doc-1',
    });
  });

  it('keeps integrated search as its own shell state', () => {
    expect(
      resolveShellState(
        '/apps/retrieval-search/workspaces/delivery-hub',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'retrieval-search',
      activeNavItemId: 'retrieval-search',
    });
  });

  it('routes the new workspace meeting path to the meeting shell', () => {
    expect(
      resolveShellState('/apps/meeting/workspaces/delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'meeting',
      activeNavItemId: 'meeting-upcoming',
    });
    expect(
      resolveShellState(
        '/apps/meeting/workspaces/delivery-hub?scope=mine',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'meeting',
      activeNavItemId: 'meeting-mine',
    });
    expect(
      resolveShellState(
        '/apps/meeting/workspaces/delivery-hub?tab=recordings',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'meeting',
      activeNavItemId: 'meeting-recordings',
    });
    expect(
      resolveShellState('/apps/home/workspaces/delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses whiteboard manifest query views for the active navigation item', () => {
    expect(
      resolveShellState(
        '/apps/whiteboard/workspaces/delivery-hub',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-all',
    });
    expect(
      resolveShellState(
        '/apps/whiteboard/workspaces/delivery-hub?view=mine',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-my',
    });
    expect(
      resolveShellState(
        '/apps/whiteboard/workspaces/delivery-hub?view=favorites',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-favorites',
    });
  });

  it('uses global planner query views for the active planner navigation item', () => {
    expect(
      resolveShellState('/apps/planner', buildUser(), ['planner']),
    ).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-calendar',
    });
    expect(
      resolveShellState('/apps/planner?view=timeline', buildUser(), [
        'planner',
      ]),
    ).toEqual({
      activeAppId: 'planner',
      activeNavItemId: 'planner-timeline',
    });
  });

  it('routes community paths to the company-wide community shell', () => {
    expect(
      resolveShellState('/apps/community', buildUser({ workspaces: [] })),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/apps/community', buildUser({ workspaces: [] }), [
        'community',
      ]),
    ).toEqual({
      activeAppId: 'community',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/apps/community?channel=suggestions', buildUser(), [
        'community',
      ]),
    ).toEqual({
      activeAppId: 'community',
      activeNavItemId: '',
    });
  });

  it('uses docs query views for the active docs navigation item', () => {
    expect(
      resolveShellState('/apps/docs/workspaces/delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=mine',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-my',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=shared',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-shared',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=private',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-private',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=meeting_notes',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-notes',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub/documents/doc-1?view=recent&page=page-1',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-recent',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=archived',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-archived',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub?view=unknown',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
  });

  it('uses manifest global routes for shared docs and whiteboards', () => {
    expect(
      resolveShellState('/apps/docs/shared/share-1', buildUser(), ['docs']),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/apps/docs/shared/share-1/html/page-1', buildUser(), [
        'docs',
      ]),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/apps/whiteboard/shared/share-1', buildUser(), [
        'whiteboard',
      ]),
    ).toEqual({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-all',
    });
  });

  it('uses leaf bootstrap IDs to gate shared routes', () => {
    expect(
      resolveShellState('/apps/docs/shared/share-1', buildUser(), ['docs']),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/apps/docs/shared/share-1', buildUser(), [
        'whiteboard',
      ]),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/apps/whiteboard/shared/share-1', buildUser(), [
        'whiteboard',
      ]),
    ).toEqual({
      activeAppId: 'whiteboard',
      activeNavItemId: 'whiteboard-all',
    });
  });

  it('uses the settings shell resolver for admin routes', () => {
    const adminUser = buildUser({ system_roles: ['platform_admin'] });
    expect(resolveShellState('/admin', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-general',
    });
    expect(resolveShellState('/admin/people', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-people',
    });
    expect(resolveShellState('/admin/workspaces', adminUser)).toEqual({
      activeAppId: 'settings',
      activeNavItemId: 'settings-workspaces',
    });
    expect(resolveShellState('/admin/apps/platform', adminUser)).toEqual({
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
    for (const legacyPath of ['/admin/apps', '/admin/users', '/admin/teams']) {
      expect(resolveShellState(legacyPath, adminUser)).toEqual({
        activeAppId: 'home',
        activeNavItemId: '',
      });
    }
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
        '/apps/unknown-app/workspaces/delivery-hub/unknown-tool',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses recording query filters for the active recording navigation item', () => {
    expect(
      resolveShellState('/apps/recording/workspaces/delivery-hub', buildUser()),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-quick',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=mine',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-mine',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=needs_review',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-mine',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=mine&category=meeting',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-meeting',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=processing',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-processing',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=failed',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-failed',
    });
    expect(
      resolveShellState(
        '/apps/recording/workspaces/delivery-hub?view=archived',
        buildUser(),
      ),
    ).toEqual({
      activeAppId: 'recording',
      activeNavItemId: 'recording-archived',
    });
  });

  it('legacy /meeting path no longer activates the meeting shell', () => {
    expect(resolveShellState('/meeting', buildUser())).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    for (const legacyPath of ['/docs', '/pms', '/apps/planner']) {
      expect(resolveShellState(legacyPath, buildUser())).toEqual({
        activeAppId: 'home',
        activeNavItemId: '',
      });
    }
  });

  it('falls back to home when the workspace bootstrap disables the app', () => {
    expect(
      resolveShellState('/apps/docs/workspaces/delivery-hub', buildUser(), [
        'home',
        'planner',
      ]),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState(
        '/apps/docs/workspaces/delivery-hub/documents/private',
        buildUser(),
        ['home', 'planner'],
      ),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
  });

  it('uses leaf bootstrap IDs without category route ownership', () => {
    expect(
      resolveShellState('/apps/docs/workspaces/delivery-hub', buildUser(), [
        'docs',
      ]),
    ).toEqual({
      activeAppId: 'docs',
      activeNavItemId: 'docs-all',
    });
    expect(
      resolveShellState('/apps/docs/workspaces/delivery-hub', buildUser(), [
        'collaboration',
      ]),
    ).toEqual({
      activeAppId: 'home',
      activeNavItemId: '',
    });
    expect(
      resolveShellState('/apps/collaboration', buildUser(), ['docs']),
    ).toEqual({ activeAppId: 'home', activeNavItemId: '' });
  });
});
