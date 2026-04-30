import { beforeEach, describe, expect, it } from 'vitest';
import { AlertTriangle, FileText, Mic, Search, Settings } from 'lucide-react';

import type { AuthUser } from '../auth/auth-api';
import type { NavItem } from '@/src/app/shell/navigation-types';
import {
  resolveBootstrapWorkspaceSlug,
  rewriteWorkspaceApiPath,
  resolveNavItemHref,
  resolveRootEntryPath,
  resolveToolInvocationHref,
} from './workspace-utils';

function buildUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    email: 'member@aidoo.local',
    full_name: 'AIDOO Member',
    display_name: 'AIDOO Member',
    status: 'active',
    theme_preference: 'system',
    primary_org_unit: null,
    workspaces: [
      {
        id: 'workspace-hq',
        slug: 'hq',
        name: 'Aidoo HQ',
        role: 'admin',
      },
    ],
    workspace_roles: [],
    system_roles: [],
    group_ids: [],
    group_slugs: [],
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

  it('falls back to admin when the user has no workspace memberships', () => {
    expect(resolveRootEntryPath(buildUser({
      workspaces: [],
      system_roles: ['platform_admin'],
    }))).toBe('/admin/general');
  });

  it('returns null when no workspace or admin landing is available', () => {
    expect(resolveRootEntryPath(buildUser({
      workspaces: [],
      system_roles: [],
    }))).toBeNull();
  });
});

describe('resolveNavItemHref', () => {
  function aiItem(overrides: Partial<NavItem> = {}): NavItem {
    return {
      id: 'search',
      title: '아이두 통합검색',
      icon: Search,
      category: 'Core Tools',
      appId: 'ai',
      ...overrides,
    };
  }

  it('routes the AI sidebar search item to the workspace-scoped search tool', () => {
    expect(resolveNavItemHref(aiItem(), 'hq', buildUser())).toBe('/tool/search?workspace=hq');
  });

  it('honors linkAppId to deep-link from AI sidebar into another app', () => {
    // Regression: slash-selecting meeting-minutes used to hit /tool/meeting-minutes
    // instead of the meeting recordings tab.
    const item = aiItem({
      id: 'meeting-minutes',
      title: '회의록',
      icon: Mic,
      linkAppId: 'meeting',
      pathSuffix: '?tab=recordings',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/w/hq/meeting?tab=recordings',
    );
  });

  it('applies pathSuffix as-is when it already starts with a query or hash', () => {
    const item = aiItem({
      id: 'fmea-compare',
      title: 'FMEA 비교',
      icon: AlertTriangle,
      pathSuffix: '?scope=mine',
    });
    expect(resolveNavItemHref(item, 'hq', buildUser())).toBe(
      '/w/hq/ai?scope=mine',
    );
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

  it('falls back to /tool/:id when target app is home or settings', () => {
    const homeItem = aiItem({
      id: 'home-dash',
      title: '홈',
      icon: FileText,
      appId: 'home',
    });
    expect(resolveNavItemHref(homeItem, 'hq', buildUser())).toBe(
      '/tool/home-dash',
    );
  });

  it('resolves a default workspace path when currentWorkspaceSlug is absent', () => {
    const item = aiItem({ id: 'fmea-compare', title: 'FMEA 비교', icon: AlertTriangle });
    expect(resolveNavItemHref(item, null, buildUser())).toBe('/w/hq/ai');
  });

  it('returns "/" when no current slug and user has no workspaces', () => {
    const item = aiItem({ id: 'fmea-compare', title: 'FMEA 비교', icon: AlertTriangle });
    expect(
      resolveNavItemHref(item, null, buildUser({ workspaces: [] })),
    ).toBe('/');
  });
});

describe('resolveToolInvocationHref', () => {
  function aiItem(overrides: Partial<NavItem> = {}): NavItem {
    return {
      id: 'search',
      title: '아이두 통합검색',
      icon: Search,
      category: 'Core Tools',
      appId: 'ai',
      ...overrides,
    };
  }

  it('routes plain AI items to their /tool/:id page', () => {
    // Regression: resolveNavItemHref would have returned /w/hq/ai (the current
    // page) for these, making slash-selection a no-op. Tool invocation must
    // land on the actual tool UI.
    expect(resolveToolInvocationHref(aiItem(), 'hq', buildUser())).toBe(
      '/tool/search?workspace=hq',
    );
    const fmea = aiItem({
      id: 'fmea-compare',
      title: 'FMEA 비교',
      icon: AlertTriangle,
    });
    expect(resolveToolInvocationHref(fmea, 'hq', buildUser())).toBe(
      '/tool/fmea-compare',
    );
  });

  it('honors linkAppId deep-links with pathSuffix', () => {
    const meetingMinutes = aiItem({
      id: 'meeting-minutes',
      title: '회의록',
      icon: Mic,
      linkAppId: 'meeting',
      pathSuffix: '?tab=recordings',
    });
    expect(
      resolveToolInvocationHref(meetingMinutes, 'hq', buildUser()),
    ).toBe('/w/hq/meeting?tab=recordings');
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
    const item = aiItem({ linkAppId: 'ai' });
    expect(resolveToolInvocationHref(item, 'hq', buildUser())).toBe(
      '/tool/search?workspace=hq',
    );
  });
});

describe('resolveBootstrapWorkspaceSlug', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('prefers the query workspace for global tool routes', () => {
    expect(
      resolveBootstrapWorkspaceSlug(buildUser(), '/tool/search', '?workspace=hq', null),
    ).toBe('hq');
  });

  it('falls back to the current shell workspace when no query workspace is provided', () => {
    expect(
      resolveBootstrapWorkspaceSlug(buildUser(), '/tool/search', '', 'hq'),
    ).toBe('hq');
  });

  it('preserves an explicit tool workspace query even when the user is not a member', () => {
    expect(
      resolveBootstrapWorkspaceSlug(buildUser(), '/tool/search', '?workspace=innovation-lab', 'hq'),
    ).toBe('innovation-lab');
  });
});

describe('rewriteWorkspaceApiPath', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, '', '/');
  });

  it('rewrites workspace-scoped rag endpoints with the active workspace slug', () => {
    window.localStorage.setItem('aidoo:last-workspace-slug', 'hq');

    expect(rewriteWorkspaceApiPath('/api/v1/rag/query')).toBe(
      '/api/v1/workspaces/hq/rag/query',
    );
  });

  it('prefers the explicit tool workspace query over the last workspace slug', () => {
    window.localStorage.setItem('aidoo:last-workspace-slug', 'hq');
    window.history.replaceState({}, '', '/tool/pms-list-list-1?workspace=lab&issue=issue-1');

    expect(rewriteWorkspaceApiPath('/api/v1/pms/issues/issue-1')).toBe(
      '/api/v1/workspaces/lab/pms/issues/issue-1',
    );
  });
});
