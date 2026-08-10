import { beforeEach, describe, expect, it } from 'vitest';
import { FileText, Mic, Settings } from 'lucide-react';

import type { AuthUser } from '../auth/auth-api';
import type { NavItem } from '@/src/app/shell/navigation-types';
import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import { docsManifest } from '@/src/app-modules/docs/manifest';
import { configureWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-path-policy';
import {
  buildWorkspaceAppPath,
  clearStoredWorkspaceSelection,
  getWorkspaceAppIdFromPath,
  getToolWorkspaceSlugFromSearch,
  resolveDefaultWorkspaceAppPath,
  resolveBootstrapWorkspaceSlug,
  rewriteWorkspaceApiPath,
  resolveNavItemHref,
  resolveRootEntryPath,
  resolveWorkspaceSwitchPath,
  resolveToolInvocationHref,
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

describe('resolveRootEntryPath', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('prefers the active workspace home when workspace membership exists', () => {
    expect(resolveRootEntryPath(buildUser())).toBe('/w/hq/home');
  });

  it('prefers the user default workspace over the stored last workspace', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');

    expect(
      resolveRootEntryPath(
        buildUser({
          default_workspace_id: 'workspace-demo',
          workspaces: [
            {
              id: 'workspace-hq',
              slug: 'hq',
              name: 'Open Work Hub HQ',
              role: 'admin',
            },
            {
              id: 'workspace-demo',
              slug: 'demo',
              name: 'Open Work Hub Demo',
              role: 'member',
            },
          ],
        }),
      ),
    ).toBe('/w/demo/home');
  });

  it('falls back to admin when the user has no workspace memberships', () => {
    expect(
      resolveRootEntryPath(
        buildUser({
          workspaces: [],
          system_roles: ['platform_admin'],
        }),
      ),
    ).toBe('/admin/general');
  });

  it('falls back to community when no workspace or admin landing is available', () => {
    expect(
      resolveRootEntryPath(
        buildUser({
          workspaces: [],
          system_roles: [],
        }),
      ),
    ).toBe('/community');
  });
});

describe('stored workspace selection', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('clears the last workspace and app together', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');
    window.localStorage.setItem('open-work-hub:last-workspace-app', 'chatbot');

    clearStoredWorkspaceSelection();

    expect(
      window.localStorage.getItem('open-work-hub:last-workspace-slug'),
    ).toBeNull();
    expect(
      window.localStorage.getItem('open-work-hub:last-workspace-app'),
    ).toBeNull();
  });

  it('switches workspaces only with enabled bootstrap app ids', () => {
    const user = buildUser({
      workspaces: [
        {
          id: 'workspace-hq',
          slug: 'hq',
          name: 'Open Work Hub HQ',
          role: 'admin',
        },
        {
          id: 'workspace-demo',
          slug: 'demo',
          name: 'Open Work Hub Demo',
          role: 'member',
        },
      ],
    });

    expect(
      resolveWorkspaceSwitchPath(user, '/w/hq/docs', 'demo', ['docs']),
    ).toBe('/w/demo/docs');

    window.localStorage.setItem('open-work-hub:last-workspace-app', 'typo-app');
    expect(
      resolveWorkspaceSwitchPath(user, '/w/hq/typo-app', 'demo', ['docs']),
    ).toBe('/');

    window.localStorage.setItem('open-work-hub:last-workspace-app', 'docs');
    expect(
      resolveWorkspaceSwitchPath(user, '/w/hq/typo-app', 'demo', ['docs']),
    ).toBe('/w/demo/docs');
  });
});

describe('buildWorkspaceAppPath', () => {
  it('uses the registered leaf app id as the canonical workspace segment', () => {
    expect(buildWorkspaceAppPath('hq', 'docs')).toBe('/w/hq/docs');
    expect(buildWorkspaceAppPath('hq', 'docs', '?tab=documents')).toBe(
      '/w/hq/docs?tab=documents',
    );
    expect(resolveDefaultWorkspaceAppPath(buildUser(), 'docs')).toBe(
      '/w/hq/docs',
    );
    expect(buildWorkspaceAppPath('hq', 'docs')).toBe('/w/hq/docs');
    expect(buildWorkspaceAppPath('hq', 'retrieval-search')).toBe(
      '/w/hq/retrieval-search',
    );
    expect(buildWorkspaceAppPath('hq', 'customer-invoice-review')).toBe(
      '/w/hq/customer-invoice-review',
    );
  });

  it('rejects app ids that are not safe path segments', () => {
    for (const appId of [
      '',
      '../admin',
      'docs/settings',
      'UPPERCASE',
      '-leading-hyphen',
      'trailing-hyphen-',
    ]) {
      expect(() => buildWorkspaceAppPath('hq', appId)).toThrow(
        `Invalid workspace app id: ${appId}`,
      );
    }

    expect(getWorkspaceAppIdFromPath('/w/hq/docs')).toBe('docs');
    expect(
      getWorkspaceAppIdFromPath('/w/hq/customer-invoice-review/details'),
    ).toBe('customer-invoice-review');
    expect(getWorkspaceAppIdFromPath('/w/hq/docs%2Fsettings')).toBeNull();
  });

  it('does not duplicate the route base when a suffix is already workspace-relative', () => {
    expect(buildWorkspaceAppPath('hq', 'docs', '/docs/cooling-module')).toBe(
      '/w/hq/docs/cooling-module',
    );
    expect(buildWorkspaceAppPath('hq', 'docs', '/docs?view=mine')).toBe(
      '/w/hq/docs?view=mine',
    );
  });
});

describe('resolveNavItemHref', () => {
  function aiItem(overrides: Partial<NavItem> = {}): NavItem {
    return {
      id: 'custom-agent-tool',
      title: 'Custom Agent Tool',
      icon: FileText,
      category: 'Core Tools',
      appId: 'chatbot',
      ...overrides,
    };
  }

  it('routes workspace-scoped tools to their tool page', () => {
    expect(
      resolveNavItemHref(
        aiItem({ workspaceScopedTool: true }),
        'hq',
        buildUser(),
      ),
    ).toBe('/tool/custom-agent-tool?workspace=hq');
  });

  it('routes another sidebar item to the workspace-scoped tool', () => {
    const item = aiItem({
      id: 'custom-review-tool',
      title: 'Custom Review Tool',
      icon: FileText,
      workspaceScopedTool: true,
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/tool/custom-review-tool?workspace=hq',
    );
  });

  it('routes docs library items to their hub query views', () => {
    const docsItems = new Map(
      docsManifest.navItems.map((item) => [item.id, item]),
    );

    const expectDocsHref = (id: string, expectedHref: string) => {
      const item = docsItems.get(id);
      expect(item).toBeDefined();
      if (!item) {
        return;
      }
      expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(expectedHref);
    };

    expectDocsHref('docs-all', '/w/hq/docs');
    expectDocsHref('docs-my', '/w/hq/docs?view=mine');
    expectDocsHref('docs-shared', '/w/hq/docs?view=shared');
    expectDocsHref('docs-private', '/w/hq/docs?view=private');
    expectDocsHref('docs-notes', '/w/hq/docs?view=meeting_notes');
    expectDocsHref('docs-recent', '/w/hq/docs?view=recent');
    expectDocsHref('docs-archived', '/w/hq/docs?view=archived');
  });

  it('honors linkAppId to deep-link from one app sidebar into another app', () => {
    const item = aiItem({
      id: 'meeting-recordings-link',
      title: 'Meeting recordings',
      icon: Mic,
      linkAppId: 'meeting',
      pathSuffix: '?tab=recordings',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/w/hq/meeting?tab=recordings',
    );
  });

  it('normalizes workspace-relative pathSuffix values for category sidebar links', () => {
    const item = aiItem({
      id: 'docs-cooling-module',
      title: '쿨링모듈',
      icon: FileText,
      appId: 'business',
      linkAppId: 'docs',
      pathSuffix: '/docs/cooling-module',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/w/hq/docs/cooling-module',
    );
  });

  it('applies pathSuffix as-is when it already starts with a query or hash', () => {
    const item = aiItem({
      id: 'chatbot',
      title: 'AI 챗봇',
      icon: FileText,
      pathSuffix: '?scope=mine',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/w/hq/chatbot?scope=mine',
    );
  });

  it('routes global app navigation through its launcher path without a workspace slug', () => {
    const item = aiItem({
      appId: 'community',
      id: 'community-general',
      pathSuffix: '?channel=general',
      title: 'Community',
    });

    expect(
      resolveNavItemHref(
        item,
        null,
        buildUser({ workspaces: [] }),
        new Map([['community', '/community']]),
      ),
    ).toBe('/community?channel=general');
  });

  it('returns absolutePath verbatim when set (admin items)', () => {
    const item = aiItem({
      id: 'settings-general',
      title: 'General',
      icon: Settings,
      appId: 'settings',
      absolutePath: '/admin/general',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe('/admin/general');
  });

  it('routes safe app identities without a central allowlist', () => {
    const homeItem = aiItem({
      id: 'home-dash',
      title: '홈',
      icon: FileText,
      appId: 'home',
    });
    expect(resolveNavItemHref(homeItem, 'hq', buildUser())).toBe('/w/hq/home');

    const customItem = aiItem({
      id: 'customer-invoice-review',
      title: 'Customer invoice review',
      icon: FileText,
      appId: 'customer-invoice-review',
    });
    expect(resolveNavItemHref(customItem, 'hq', buildUser())).toBe(
      '/w/hq/customer-invoice-review',
    );
  });

  it('does not interpolate unsafe nav app ids into workspace paths', () => {
    const unsafeItem = aiItem({
      id: 'unsafe-app',
      title: 'Unsafe app',
      icon: FileText,
      appId: '../admin',
    });
    expect(resolveNavItemHref(unsafeItem, 'hq', buildUser())).toBe(
      '/tool/unsafe-app',
    );
  });

  it('resolves a default workspace path when currentWorkspaceSlug is absent', () => {
    const item = aiItem({ id: 'chatbot', title: 'AI 챗봇', icon: FileText });
    expect(resolveNavItemHref(item, null, buildUser())).toBe('/w/hq/chatbot');
  });

  it('returns "/" when no current slug and user has no workspaces', () => {
    const item = aiItem({ id: 'chatbot', title: 'AI 챗봇', icon: FileText });
    expect(resolveNavItemHref(item, null, buildUser({ workspaces: [] }))).toBe(
      '/',
    );
  });
});

describe('resolveToolInvocationHref', () => {
  function aiItem(overrides: Partial<NavItem> = {}): NavItem {
    return {
      id: 'custom-agent-tool',
      title: 'Custom Agent Tool',
      icon: FileText,
      category: 'Core Tools',
      appId: 'chatbot',
      workspaceScopedTool: true,
      ...overrides,
    };
  }

  it('routes plain in-app items to their /tool/:id page', () => {
    // Regression: resolveNavItemHref would have returned the current app page
    // for these, making slash-selection a no-op. Tool invocation must land on
    // the actual tool UI.
    expect(resolveToolInvocationHref(aiItem(), 'hq', buildUser())).toBe(
      '/tool/custom-agent-tool?workspace=hq',
    );
    const chatbot = aiItem({
      id: 'chatbot',
      title: 'AI 챗봇',
      icon: FileText,
      workspaceScopedTool: false,
    });
    expect(resolveToolInvocationHref(chatbot, 'hq', buildUser())).toBe(
      '/tool/chatbot',
    );
    const reviewTool = aiItem({
      id: 'custom-review-tool',
      title: 'Custom Review Tool',
      icon: FileText,
    });
    expect(resolveToolInvocationHref(reviewTool, 'hq', buildUser())).toBe(
      '/tool/custom-review-tool?workspace=hq',
    );
  });

  it('uses manifest metadata rather than hardcoded ids for workspace-scoped tools', () => {
    const customTool = aiItem({
      id: 'custom-agent-tool',
      title: 'Custom Agent Tool',
      workspaceScopedTool: true,
    });
    const unscopedTool = aiItem({
      id: 'custom-global-tool',
      title: 'Custom Global Tool',
      workspaceScopedTool: false,
    });

    expect(resolveToolInvocationHref(customTool, 'hq', buildUser())).toBe(
      '/tool/custom-agent-tool?workspace=hq',
    );
    expect(resolveToolInvocationHref(unscopedTool, 'hq', buildUser())).toBe(
      '/tool/custom-global-tool',
    );
  });

  it('honors linkAppId deep-links with pathSuffix', () => {
    const meetingRecordings = aiItem({
      id: 'meeting-recordings-link',
      title: 'Meeting recordings',
      icon: Mic,
      linkAppId: 'meeting',
      pathSuffix: '?tab=recordings',
    });
    expect(
      resolveToolInvocationHref(meetingRecordings, 'hq', buildUser()),
    ).toBe('/w/hq/meeting?tab=recordings');
  });

  it('does not interpolate an unsafe linked app id into workspace paths', () => {
    const unsafeLink = aiItem({
      id: 'unsafe-link',
      linkAppId: '../admin',
    });
    expect(resolveToolInvocationHref(unsafeLink, 'hq', buildUser())).toBe(
      '/tool/unsafe-link',
    );
  });

  it('returns absolutePath verbatim when set', () => {
    const admin = aiItem({
      id: 'settings-general',
      title: 'General',
      icon: Settings,
      appId: 'settings',
      absolutePath: '/admin/general',
    });
    expect(resolveToolInvocationHref(admin, 'hq', buildUser())).toBe(
      '/admin/general',
    );
  });

  it('treats a matching linkAppId === appId as plain in-app routing', () => {
    // If someone sets linkAppId === appId (no actual deep-link), still route
    // to /tool/:id rather than the app's landing page.
    const item = aiItem({ linkAppId: 'chatbot' });
    expect(resolveToolInvocationHref(item, 'hq', buildUser())).toBe(
      '/tool/custom-agent-tool?workspace=hq',
    );
  });
});

describe('getToolWorkspaceSlugFromSearch', () => {
  it('returns a requested tool workspace when no user context is available', () => {
    expect(
      getToolWorkspaceSlugFromSearch(null, '/tool/search', '?workspace=demo'),
    ).toBe('demo');
  });

  it('returns the requested tool workspace only when the user is a member', () => {
    expect(
      getToolWorkspaceSlugFromSearch(
        buildUser(),
        '/tool/search',
        '?workspace=hq',
      ),
    ).toBe('hq');
    expect(
      getToolWorkspaceSlugFromSearch(
        buildUser(),
        '/tool/search',
        '?workspace=demo',
      ),
    ).toBeNull();
  });
});

describe('resolveBootstrapWorkspaceSlug', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('prefers the query workspace for global tool routes', () => {
    expect(
      resolveBootstrapWorkspaceSlug(
        buildUser(),
        '/tool/search',
        '?workspace=hq',
        null,
      ),
    ).toBe('hq');
  });

  it('returns null for a route workspace the user cannot access', () => {
    expect(
      resolveBootstrapWorkspaceSlug(
        buildUser(),
        '/w/innovation-lab/chatbot',
        '',
        'hq',
      ),
    ).toBeNull();
  });

  it('falls back to the current shell workspace when no query workspace is provided', () => {
    expect(
      resolveBootstrapWorkspaceSlug(buildUser(), '/tool/search', '', 'hq'),
    ).toBe('hq');
  });

  it('returns null for an explicit tool workspace query when the user is not a member', () => {
    expect(
      resolveBootstrapWorkspaceSlug(
        buildUser(),
        '/tool/search',
        '?workspace=innovation-lab',
        'hq',
      ),
    ).toBeNull();
  });

  it('does not reuse a stale shell workspace when the user has no memberships', () => {
    expect(
      resolveBootstrapWorkspaceSlug(
        buildUser({ workspaces: [] }),
        '/tool/search',
        '',
        'hq',
      ),
    ).toBeNull();
  });
});

describe('rewriteWorkspaceApiPath', () => {
  beforeEach(() => {
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
    window.localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('rewrites workspace-scoped rag endpoints with the active workspace slug', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');

    expect(rewriteWorkspaceApiPath('/api/v1/rag/query')).toBe(
      '/api/v1/workspaces/hq/rag/query',
    );
  });

  it('prefers the explicit tool workspace query over the last workspace slug', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');
    window.history.replaceState(
      {},
      '',
      '/tool/docs-all?workspace=demo&doc=doc-1',
    );

    expect(rewriteWorkspaceApiPath('/api/v1/pms/tasks/issue-1')).toBe(
      '/api/v1/workspaces/demo/pms/tasks/issue-1',
    );
  });

  it('does not fall back to browser state when the explicit workspace slug is empty', () => {
    window.localStorage.setItem('open-work-hub:last-workspace-slug', 'hq');

    expect(rewriteWorkspaceApiPath('/api/v1/docs/hub', '')).toBe(
      '/api/v1/docs/hub',
    );
  });
});
