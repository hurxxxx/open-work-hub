import { describe, expect, it } from 'vitest';

import type { ShellAppId } from '@/src/app-shell';

import { resolveShellDocumentTitle } from './document-title-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (key === 'apps.chatbot') return 'Chatbot';
  if (key === 'apps.settings') return 'Settings';
  if (key === 'workspaceSwitcher.manage') return 'Workspace settings';
  if (key === 'documentTitle.profile') return 'Profile';
  if (key === 'documentTitle.app') return `${String(options?.app)} | Open ALM`;
  if (key === 'documentTitle.workspaceApp') {
    return `${String(options?.workspace)} - ${String(options?.app)} | Open ALM`;
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
    pathname: overrides.pathname ?? '/w/hq/chatbot',
    routeWorkspaceSlug: hasRouteWorkspaceSlug
      ? (overrides.routeWorkspaceSlug ?? null)
      : 'hq',
    t,
    workspace: hasWorkspace ? overrides.workspace : { name: 'HQ' },
    workspaceApps: overrides.workspaceApps ?? [],
  });
}

describe('document title model', () => {
  it('uses special document titles for workspace settings and profile routes', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/w/hq/settings/members',
      }),
    ).toBe('HQ - Workspace settings | Open ALM');
    expect(
      title({
        activeAppId: 'profile',
        pathname: '/profile',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('Profile | Open ALM');
  });

  it('uses the settings app title outside workspace settings routes', () => {
    expect(
      title({
        activeAppId: 'settings',
        pathname: '/admin/users',
        routeWorkspaceSlug: null,
        workspace: null,
      }),
    ).toBe('Settings | Open ALM');
  });

  it('falls back from i18n key to workspace bootstrap title and app registry title', () => {
    expect(
      title({
        activeAppId: 'workspace-app',
        workspaceApps: [{ app_id: 'workspace-app', title: 'Workspace app' }],
      }),
    ).toBe('HQ - Workspace app | Open ALM');
    expect(title({ activeAppId: 'docs' })).toBe('HQ - docs | Open ALM');
  });

  it('includes the workspace name only for workspace-scoped and tool routes', () => {
    expect(title({ pathname: '/tool/search', routeWorkspaceSlug: null })).toBe(
      'HQ - Chatbot | Open ALM',
    );
  });
});
