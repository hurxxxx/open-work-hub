import { describe, expect, it } from 'vitest';

import type { ShellAppId } from '@/src/app-shell';

import { resolveShellDocumentTitle } from './document-title-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'apps.chatbot') return 'Chatbot';
  if (key === 'apps.settings') return 'Settings';
  if (key === 'documentTitle.profile') return 'Profile';
  if (key === 'launcher.title') return 'App launcher';
  if (key === 'documentTitle.app')
    return `${String(options?.app)} | Open Work Hub`;
  if (key === 'documentTitle.workspaceApp') {
    return `${String(options?.workspace)} - ${String(options?.app)} | Open Work Hub`;
  }
  return String(options?.defaultValue ?? key);
}

function title(
  overrides: {
    activeAppId?: ShellAppId;
    pathname?: string;
    routeWorkspaceSlug?: string | null;
    workspace?: { name: string } | null;
    workspaceApps?: { app_id: string; title: string }[];
  } = {},
): string {
  const hasRouteWorkspaceSlug = Object.prototype.hasOwnProperty.call(
    overrides,
    'routeWorkspaceSlug',
  );
  const hasWorkspace = Object.prototype.hasOwnProperty.call(
    overrides,
    'workspace',
  );
  return resolveShellDocumentTitle({
    activeAppId: overrides.activeAppId ?? 'chatbot',
    pathname: overrides.pathname ?? '/apps/chatbot/workspaces/hq',
    routeWorkspaceSlug: hasRouteWorkspaceSlug
      ? (overrides.routeWorkspaceSlug ?? null)
      : 'hq',
    t,
    workspace: hasWorkspace ? overrides.workspace : { name: 'HQ' },
    workspaceApps: overrides.workspaceApps ?? [],
  });
}

describe('document title model', () => {
  it('uses a neutral title for the launcher', () => {
    expect(
      title({
        activeAppId: 'launcher',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('App launcher | Open Work Hub');
  });

  it('uses platform app titles without an inferred workspace', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/admin/workspaces/hq/settings',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('Settings | Open Work Hub');
    expect(
      title({
        activeAppId: 'profile',
        pathname: '/profile',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('Profile | Open Work Hub');
  });

  it('uses the settings app title outside workspace settings routes', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/admin/users',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('Settings | Open Work Hub');
  });

  it('falls back from i18n key to workspace bootstrap title and app registry title', () => {
    expect(
      title({
        activeAppId: 'workspace-app',
        workspaceApps: [{ app_id: 'workspace-app', title: 'Workspace app' }],
      }),
    ).toBe('HQ - Workspace app | Open Work Hub');
    expect(title({ activeAppId: 'docs' })).toBe('HQ - docs | Open Work Hub');
  });

  it('includes the workspace name only when the route carries workspace context', () => {
    expect(
      title({ pathname: '/apps/retrieval-search', routeWorkspaceSlug: null }),
    ).toBe('Chatbot | Open Work Hub');
    expect(title()).toBe('HQ - Chatbot | Open Work Hub');
  });
});
