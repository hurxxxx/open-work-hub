import { beforeEach, describe, expect, it } from 'vitest';
import { FileText, Settings } from 'lucide-react';

import { docsManifest } from '@/src/app-modules/docs/manifest';
import type { NavItem } from '@/src/app/shell/navigation-types';
import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import type { AuthUser } from '@/src/platform/auth/auth-api';
import { configureWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-path-policy';
import {
  buildWorkspaceAppEntryPath,
  buildWorkspaceAppPath,
  getWorkspaceAppIdFromPath,
  getWorkspaceBySlug,
  getWorkspaceSlugFromPath,
  resolveAppInvocationHref,
  resolveNavItemHref,
  resolveRouteWorkspaceSlug,
  rewriteWorkspaceApiPath,
} from './workspace-utils';

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
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Open Work Hub HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    must_change_password: false,
    ...overrides,
  };
}

function navItem(overrides: Partial<NavItem> = {}): NavItem {
  return {
    id: 'docs-all',
    title: 'Docs',
    icon: FileText,
    category: 'Collaboration',
    appId: 'docs',
    ...overrides,
  };
}

describe('canonical workspace route context', () => {
  it('extracts only registered app-first workspace routes', () => {
    const path = '/apps/docs/workspaces/team%20alpha/documents/doc-1';
    expect(getWorkspaceSlugFromPath(path)).toBe('team alpha');
    expect(getWorkspaceAppIdFromPath(path)).toBe('docs');
    expect(getWorkspaceSlugFromPath('/apps/docs')).toBeNull();
    expect(getWorkspaceAppIdFromPath('/apps/unknown/workspaces/hq')).toBeNull();
    expect(getWorkspaceSlugFromPath('/apps/docs/workspaces')).toBeNull();
  });

  it('resolves route context only for a current membership', () => {
    const user = buildUser();
    expect(getWorkspaceBySlug(user, 'hq')?.id).toBe('workspace-hq');
    expect(resolveRouteWorkspaceSlug(user, '/apps/docs/workspaces/hq')).toBe(
      'hq',
    );
    expect(
      resolveRouteWorkspaceSlug(user, '/apps/docs/workspaces/other'),
    ).toBeNull();
    expect(resolveRouteWorkspaceSlug(user, '/apps/community')).toBeNull();
  });
});

describe('workspace app paths', () => {
  it('builds canonical app entry and explicit workspace paths', () => {
    expect(buildWorkspaceAppEntryPath('docs')).toBe('/apps/docs');
    expect(buildWorkspaceAppPath('team alpha', 'docs')).toBe(
      '/apps/docs/workspaces/team%20alpha',
    );
    expect(buildWorkspaceAppPath('hq', 'retrieval-search')).toBe(
      '/apps/retrieval-search/workspaces/hq',
    );
  });

  it('fails closed for global, unknown, or unsafe app identities', () => {
    for (const appId of ['community', 'customer-app', '../admin', '']) {
      expect(() => buildWorkspaceAppPath('hq', appId)).toThrow(
        `Unknown workspace app: ${appId}`,
      );
    }
  });
});

describe('navigation href resolution', () => {
  it('uses declared root and query routes for workspace apps', () => {
    const docsItems = new Map(
      docsManifest.navItems.map((item) => [item.id, item]),
    );
    const docsAll = docsItems.get('docs-all');
    const docsMy = docsItems.get('docs-my');
    expect(docsAll).toBeDefined();
    expect(docsMy).toBeDefined();
    if (!docsAll || !docsMy) throw new Error('Docs navigation is incomplete');
    expect(resolveNavItemHref(docsAll, 'hq', buildUser())).toBe(
      '/apps/docs/workspaces/hq',
    );
    expect(resolveNavItemHref(docsMy, 'hq', buildUser())).toBe(
      '/apps/docs/workspaces/hq?view=mine',
    );
  });

  it('uses declared cross-app and static suffix routes', () => {
    expect(
      resolveNavItemHref(
        navItem({ linkAppId: 'meeting', pathSuffix: '?tab=recordings' }),
        'hq',
        buildUser(),
      ),
    ).toBe('/apps/meeting/workspaces/hq?tab=recordings');
    expect(
      resolveNavItemHref(
        navItem({ appId: 'files', pathSuffix: '/chat' }),
        'hq',
        buildUser(),
      ),
    ).toBe('/apps/files/workspaces/hq/chat');
  });

  it('uses the app chooser when workspace context is absent', () => {
    expect(resolveNavItemHref(navItem(), null, buildUser())).toBe('/apps/docs');
  });

  it('routes platform apps without a workspace context', () => {
    expect(
      resolveNavItemHref(
        navItem({ appId: 'community', pathSuffix: '?channel=general' }),
        null,
        buildUser(),
      ),
    ).toBe('/apps/community?channel=general');
  });

  it('returns absolute paths verbatim and rejects undeclared targets', () => {
    expect(
      resolveAppInvocationHref(
        navItem({
          appId: 'settings',
          absolutePath: '/admin/general',
          icon: Settings,
        }),
        'hq',
        buildUser(),
      ),
    ).toBe('/admin/general');
    expect(
      resolveNavItemHref(navItem({ appId: 'unknown-app' }), 'hq', buildUser()),
    ).toBe('/');
    expect(
      resolveNavItemHref(
        navItem({ pathSuffix: '/documents/dynamic-id' }),
        'hq',
        buildUser(),
      ),
    ).toBe('/');
  });
});

describe('workspace API path rewriting', () => {
  beforeEach(() => {
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
    window.localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('uses an explicit workspace argument', () => {
    expect(rewriteWorkspaceApiPath('/api/v1/rag/query', 'hq')).toBe(
      '/api/v1/workspaces/hq/rag/query',
    );
  });

  it('uses canonical workspace route context from the browser URL', () => {
    window.history.replaceState({}, '', '/apps/docs/workspaces/demo');
    expect(rewriteWorkspaceApiPath('/api/v1/pms/tasks/issue-1')).toBe(
      '/api/v1/workspaces/demo/pms/tasks/issue-1',
    );
  });

  it('does not infer workspace context from storage or global query params', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');
    window.history.replaceState({}, '', '/apps/community?workspace=demo');
    expect(rewriteWorkspaceApiPath('/api/v1/docs/hub')).toBe(
      '/api/v1/docs/hub',
    );
  });

  it('does not fall back to browser state for an explicit empty context', () => {
    window.history.replaceState({}, '', '/apps/docs/workspaces/hq');
    expect(rewriteWorkspaceApiPath('/api/v1/docs/hub', '')).toBe(
      '/api/v1/docs/hub',
    );
  });
});
